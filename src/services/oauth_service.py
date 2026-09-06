"""Universal OAuth2 manager.

Handles the full OAuth2 lifecycle for every provider:
- Authorization URL generation with state + PKCE (if supported).
- Token exchange on callback.
- Access + refresh token storage (encrypted, scoped to a workspace).
- Token refresh with automatic re-encryption.
- Token revocation where the provider supports it.
"""

from __future__ import annotations

import hashlib
import secrets
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from exceptions import OAuthFailed, TokenExpired
from models import Credential, IntegrationConnection, OAuthState, Workspace
from providers.registry import registry
from services.encryption_service import EncryptionService, get_encryption_service


class OAuthService:
    """Per-provider OAuth operations using provider oauth metadata."""

    def __init__(self, encryption: EncryptionService | None = None) -> None:
        self.encryption = encryption or get_encryption_service()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _base64url(data: bytes) -> str:
        import base64

        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    def _generate_pkce_pair(self) -> tuple[str, str]:
        verifier = self._base64url(secrets.token_bytes(48))
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = self._base64url(digest)
        return verifier, challenge

    async def _resolve_workspace(self, session: AsyncSession, workspace_id: str) -> Workspace:
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None:
            from exceptions import WorkspaceNotFound

            raise WorkspaceNotFound(f"workspace {workspace_id} not found")
        return workspace

    # -- authorize -----------------------------------------------------------

    async def create_authorization_url(
        self,
        *,
        provider: str,
        workspace_id: str,
        session: AsyncSession,
        scopes: list[str] | None = None,
        redirect_uri: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Return (state, code_verifier, authorization_url)."""
        provider_cls = registry.get(provider)
        await self._resolve_workspace(session, workspace_id)

        effective_scopes = scopes or provider_cls.oauth_scopes or provider_cls.default_scopes
        state = secrets.token_urlsafe(32)
        verifier: str | None = None
        challenge: str | None = None
        if provider_cls.oauth_pkce:
            verifier, challenge = self._generate_pkce_pair()

        redirect_uri = redirect_uri or self._default_redirect_uri(provider)
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.oauth_state_ttl_seconds)

        state_record = OAuthState(
            workspace_id=workspace_id,
            provider=provider,
            state_token=state,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            scopes=effective_scopes,
            expires_at=expires_at,
        )
        session.add(state_record)
        await session.commit()

        params: dict[str, Any] = {
            "client_id": self._client_id_for(provider),
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(effective_scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        if challenge:
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        params.update(extra_params or {})

        base = provider_cls.oauth_authorize_url or provider_cls.base_url
        separator = "&" if "?" in base else "?"
        authorization_url = f"{base}{separator}{urllib.parse.urlencode(params)}"
        return state, verifier or "", authorization_url

    def _client_id_for(self, provider: str) -> str:
        return settings.provider_config(provider).get("client_id", "")

    def _default_redirect_uri(self, provider: str) -> str:
        base = settings.oauth_redirect_base_url.rstrip("/")
        return f"{base}/oauth/callback/{provider}"

    # -- callback / token exchange --------------------------------------------

    async def handle_callback(
        self,
        *,
        provider: str,
        code: str,
        state: str,
        session: AsyncSession,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """Exchange the authorization code for tokens and persist them.

        Returns a dict describing what was stored.
        """
        provider_cls = registry.get(provider)
        state_record = await self._consume_state(session, provider, state)

        token_response = await self._exchange_code(
            provider_cls=provider_cls,
            code=code,
            redirect_uri=state_record.redirect_uri or self._default_redirect_uri(provider),
            code_verifier=code_verifier or state_record.code_verifier,
        )
        if "access_token" not in token_response:
            raise OAuthFailed(
                "OAuth exchange did not return an access token",
                provider=provider,
                details={"keys": list(token_response.keys())},
            )

        credentials = self._extract_credentials(token_response, provider_cls)
        encrypted = self.encryption.encrypt_credentials(credentials)
        expires_at = self._expiry_from_token(token_response)

        connection = await self._upsert_connection(
            session=session,
            provider=provider,
            workspace_id=state_record.workspace_id,
            encrypted=encrypted,
            scopes=state_record.scopes,
            expires_at=expires_at,
        )
        await self._persist_credential(
            session=session,
            provider=provider,
            workspace_id=state_record.workspace_id,
            encrypted=encrypted,
            expires_at=expires_at,
        )
        await session.commit()

        return {
            "provider": provider,
            "workspace_id": connection.workspace_id,
            "connection_id": connection.id,
            "scopes": state_record.scopes,
            "expires_at": expires_at,
        }

    async def _consume_state(self, session: AsyncSession, provider: str, state: str) -> OAuthState:
        result = await session.execute(
            select(OAuthState).where(
                OAuthState.state_token == state,
                OAuthState.provider == provider,
                OAuthState.consumed.is_(False),
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise OAuthFailed("invalid or already-consumed OAuth state", provider=provider)
        if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            record.consumed = True
            await session.commit()
            raise OAuthFailed("OAuth state has expired", provider=provider)
        record.consumed = True
        return record

    async def _exchange_code(
        self,
        *,
        provider_cls: Any,
        code: str,
        redirect_uri: str,
        code_verifier: str | None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        headers: dict[str, str] = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None
        if provider_cls.oauth_token_header_auth:
            config = settings.provider_config(provider_cls.provider_key)
            client_id = config.get("client_id", "")
            client_secret = config.get("client_secret", "") or ""
            auth = (client_id, client_secret)
        else:
            config = settings.provider_config(provider_cls.provider_key)
            data["client_id"] = config.get("client_id", "")
            data["client_secret"] = config.get("client_secret", "") or ""

        async with self._httpx_client() as client:
            response = await client.post(
                provider_cls.oauth_token_url,
                data=data,
                headers=headers,
                auth=auth,
            )
        if response.status_code >= 400:
            body = _safe_body(response)
            raise OAuthFailed(
                "OAuth token exchange failed",
                provider=provider_cls.provider_key,
                details={"status_code": response.status_code, "body": body},
            )
        return response.json()

    def _extract_credentials(self, token_response: dict[str, Any], provider_cls: Any) -> dict[str, Any]:
        """Normalize provider token responses into a common credential dict.

        Providers may override this to enrich with user/profile info.
        """
        credentials = {
            "access_token": token_response.get("access_token"),
            "token_type": token_response.get("token_type", "Bearer"),
            "expires_in": token_response.get("expires_in"),
            "scope": token_response.get("scope"),
        }
        if token_response.get("refresh_token"):
            credentials["refresh_token"] = token_response["refresh_token"]
        if token_response.get("id_token"):
            credentials["id_token"] = token_response["id_token"]
        credentials.update(provider_cls().oauth_enrich_token(token_response))
        return credentials

    @staticmethod
    def _expiry_from_token(token_response: dict[str, Any]) -> datetime | None:
        expires_in = token_response.get("expires_in")
        if not expires_in:
            return None
        try:
            return datetime.now(UTC) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            return None

    async def _upsert_connection(
        self,
        *,
        session: AsyncSession,
        provider: str,
        workspace_id: str,
        encrypted: str,
        scopes: list[str],
        expires_at: datetime | None,
    ) -> IntegrationConnection:
        if settings.database_url.startswith("postgresql"):
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(IntegrationConnection).values(
                provider=provider,
                workspace_id=workspace_id,
                status="connected",
                encrypted_credentials=encrypted,
                scopes=scopes,
                connected_at=datetime.now(UTC),
                expires_at=expires_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["workspace_id", "provider"],
                set_={
                    "status": "connected",
                    "encrypted_credentials": encrypted,
                    "scopes": scopes,
                    "expires_at": expires_at,
                    "connected_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            ).returning(IntegrationConnection)
            result = await session.execute(stmt)
            return result.scalar_one()

        # Portable path (sqlite/dev/test dbs): select-then-insert-or-update.
        now = datetime.now(UTC)
        result = await session.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.provider == provider,
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            connection = IntegrationConnection(
                provider=provider,
                workspace_id=workspace_id,
                status="connected",
                encrypted_credentials=encrypted,
                scopes=scopes,
                connected_at=now,
                expires_at=expires_at,
            )
            session.add(connection)
        else:
            connection.status = "connected"
            connection.encrypted_credentials = encrypted
            connection.scopes = scopes
            connection.expires_at = expires_at
            connection.connected_at = now
            connection.updated_at = now
        await session.flush()
        return connection

    async def _persist_credential(
        self,
        *,
        session: AsyncSession,
        provider: str,
        workspace_id: str,
        encrypted: str,
        expires_at: datetime | None,
    ) -> None:
        credential = Credential(
            provider=provider,
            workspace_id=workspace_id,
            name="oauth_default",
            encrypted_blob=encrypted,
            expires_at=expires_at,
        )
        session.add(credential)

    @staticmethod
    def _httpx_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0)

    # -- refresh / revocation -------------------------------------------------

    async def refresh_access_token(
        self,
        *,
        provider: str,
        workspace_id: str,
        session: AsyncSession,
    ) -> tuple[dict[str, Any], str]:
        """Refresh an access token using the stored refresh token.

        Returns (new_credentials, encrypted_blob) or raises TokenExpired.
        """
        provider_cls = registry.get(provider)
        connection = await self._get_connection(session, provider, workspace_id)
        try:
            credentials = self.encryption.decrypt_credentials(connection.encrypted_credentials or "")
        except Exception as exc:
            raise TokenExpired("stored credentials cannot be decrypted", provider=provider) from exc

        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise TokenExpired("no refresh token stored", provider=provider)

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None
        config = settings.provider_config(provider)
        if provider_cls.oauth_token_header_auth:
            auth = (config.get("client_id", ""), config.get("client_secret", "") or "")
        else:
            data["client_id"] = config.get("client_id", "")
            data["client_secret"] = config.get("client_secret", "") or ""

        try:
            async with self._httpx_client() as client:
                response = await client.post(provider_cls.oauth_token_url, data=data, headers=headers, auth=auth)
        except httpx.HTTPError as exc:
            raise TokenExpired("token refresh request failed", provider=provider) from exc

        if response.status_code >= 400:
            raise TokenExpired(
                "token refresh rejected by provider",
                provider=provider,
                details={"status_code": response.status_code},
            )

        token_response = response.json()
        if "access_token" not in token_response:
            raise TokenExpired("token refresh returned no access token", provider=provider)

        credentials["access_token"] = token_response["access_token"]
        if token_response.get("expires_in"):
            connection.expires_at = self._expiry_from_token(token_response)
        if token_response.get("refresh_token"):
            credentials["refresh_token"] = token_response["refresh_token"]

        encrypted = self.encryption.encrypt_credentials(credentials)
        connection.encrypted_credentials = encrypted
        connection.expires_at = self._expiry_from_token(token_response) or connection.expires_at
        await session.commit()

        from telemetry import metrics

        metrics.inc_oauth_refresh(provider)
        return credentials, encrypted

    async def revoke_token(
        self,
        *,
        provider: str,
        workspace_id: str,
        session: AsyncSession,
    ) -> None:
        """Revoke a token if the provider exposes a revocation endpoint."""
        provider_cls = registry.get(provider)
        connection = await self._get_connection(session, provider, workspace_id)
        if not provider_cls.oauth_revoke_url:
            # No revoke endpoint: destroy local tokens, that's the best effort.
            connection.status = "revoked"
            connection.is_active = False
            await session.commit()
            return
        try:
            credentials = self.encryption.decrypt_credentials(connection.encrypted_credentials or "")
        except Exception:
            credentials = {}
        token = credentials.get("access_token") or credentials.get("refresh_token")
        if not token:
            return
        config = settings.provider_config(provider)
        data = {
            "token": token,
            **({"token_type_hint": "access_token"}),
        }
        auth: tuple[str, str] | None = None
        headers = {"Accept": "application/json"}
        if provider_cls.oauth_token_header_auth:
            auth = (config.get("client_id", ""), config.get("client_secret", "") or "")
        else:
            data["client_id"] = config.get("client_id", "")
            data["client_secret"] = config.get("client_secret", "") or ""
        try:
            async with self._httpx_client() as client:
                await client.post(provider_cls.oauth_revoke_url, data=data, headers=headers, auth=auth)
        except httpx.HTTPError:
            pass
        connection.status = "revoked"
        connection.is_active = False
        connection.encrypted_credentials = None
        await session.commit()

    async def _get_connection(
        self, session: AsyncSession, provider: str, workspace_id: str
    ) -> IntegrationConnection:
        result = await session.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.provider == provider,
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            from exceptions import ConnectionNotFound

            raise ConnectionNotFound(f"no {provider} connection for workspace")
        return connection


def _safe_body(response: httpx.Response) -> str:
    try:
        return response.text[:200]
    except Exception:
        return "unreadable response body"


oauth_service: OAuthService | None = None


def get_oauth_service() -> OAuthService:
    global oauth_service
    if oauth_service is None:
        oauth_service = OAuthService()
    return oauth_service
