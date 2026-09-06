"""Integration manager: resolves connections, credentials, and executes actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import (
    ConnectionNotFound,
    CredentialNotFound,
    TokenExpired,
    ValidationError,
)
from models import IntegrationConnection
from providers import BaseIntegrationProvider, ProviderContext
from providers.registry import get_registry
from schemas import CapabilityOut
from services.credential_service import CredentialService, get_credential_service
from services.encryption_service import get_encryption_service
from services.oauth_service import OAuthService, get_oauth_service


class IntegrationManager:
    """Coordinates providers, connections, and the execution engine."""

    def __init__(
        self,
        *,
        credential_service: CredentialService | None = None,
        oauth_service: OAuthService | None = None,
    ) -> None:
        self.credentials = credential_service or get_credential_service()
        self.oauth = oauth_service or get_oauth_service()

    # -- discovery ------------------------------------------------------------

    def list_providers(self) -> list[dict[str, Any]]:
        registry = get_registry()
        payload: list[dict[str, Any]] = []
        for key, provider_cls in registry.all().items():
            payload.append(
                {
                    "key": provider_cls.provider_key,
                    "name": provider_cls.name,
                    "description": provider_cls.description,
                    "auth_type": provider_cls.auth_type,
                    "oauth_supported": bool(provider_cls.oauth_authorize_url),
                    "webhook_supported": provider_cls.supports_webhooks,
                    "capabilities": [cap.name for cap in provider_cls.capabilities],
                }
            )
        return payload

    def get_provider_info(self, provider: str) -> dict[str, Any]:
        provider_cls = get_registry().get(provider)
        return {
            "key": provider_cls.provider_key,
            "name": provider_cls.name,
            "description": provider_cls.description,
            "auth_type": provider_cls.auth_type,
            "oauth_supported": bool(provider_cls.oauth_authorize_url),
            "webhook_supported": provider_cls.supports_webhooks,
        }

    def list_capabilities(self, provider: str) -> list[CapabilityOut]:
        provider_cls = get_registry().get(provider)
        return [
            CapabilityOut(
                name=cap.name,
                description=cap.description,
                params_schema=cap.params_schema,
            )
            for cap in provider_cls.capabilities
        ]

    # -- connections ------------------------------------------------------------

    async def list_connections(
        self, *, workspace_id: str, session: AsyncSession
    ) -> list[IntegrationConnection]:
        result = await session.execute(
            select(IntegrationConnection)
            .where(IntegrationConnection.workspace_id == workspace_id)
            .order_by(IntegrationConnection.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_connection(
        self, *, workspace_id: str, provider: str, session: AsyncSession
    ) -> IntegrationConnection:
        result = await session.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.provider == provider,
                IntegrationConnection.is_active.is_(True),
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            raise ConnectionNotFound(
                f"no active {provider} connection for this workspace",
            )
        return connection

    async def disconnect(
        self, *, workspace_id: str, provider: str, session: AsyncSession
    ) -> None:
        connection = await self.get_connection(workspace_id=workspace_id, provider=provider, session=session)
        connection.is_active = False
        connection.status = "disconnected"
        await session.commit()

    # -- execution --------------------------------------------------------------

    async def validate_connection(
        self, *, workspace_id: str, provider: str, session: AsyncSession
    ) -> dict[str, Any]:
        connection = await self.get_connection(workspace_id=workspace_id, provider=provider, session=session)
        provider_instance, credentials = await self._build_provider(
            connection, session=session
        )
        try:
            valid = await provider_instance.validate_connection()
            health = await provider_instance.health()
        finally:
            await provider_instance.disconnect()
        return {
            "provider": provider,
            "valid": valid,
            "checks": {
                "validate_connection": valid,
                "health": health.status,
                "credential_masked": _mask(credentials),
            },
        }

    async def execute_action(
        self,
        *,
        workspace_id: str,
        provider: str,
        action: str,
        payload: dict[str, Any],
        session: AsyncSession,
        connection: IntegrationConnection | None = None,
    ) -> tuple[Any, float]:
        """Execute an action. Returns (result, latency_ms)."""
        import time

        start = time.perf_counter()
        connection = connection or await self.get_connection(
            workspace_id=workspace_id, provider=provider, session=session
        )
        provider_instance, credentials = await self._build_provider(connection, session=session)
        try:
            result = await provider_instance.execute_action(action, payload or {})
        except TokenExpired:
            await self._try_refresh(connection, session)
            provider_instance, _ = await self._build_provider(connection, session=session)
            result = await provider_instance.execute_action(action, payload or {})
        finally:
            await provider_instance.disconnect()
        latency_ms = (time.perf_counter() - start) * 1000
        return result, latency_ms

    async def _try_refresh(
        self, connection: IntegrationConnection, session: AsyncSession
    ) -> None:
        try:
            await self.oauth.refresh_access_token(
                provider=connection.provider,
                workspace_id=connection.workspace_id,
                session=session,
            )
        except TokenExpired:
            raise TokenExpired(
                "integration token expired and refresh failed",
                provider=connection.provider,
            )
        await session.refresh(connection)

    async def _build_provider(
        self,
        connection: IntegrationConnection,
        *,
        session: AsyncSession,
    ) -> tuple[BaseIntegrationProvider, dict[str, Any]]:
        encrypted = connection.encrypted_credentials
        if not encrypted:
            raise CredentialNotFound(
                f"{connection.provider} connection has stored no credentials"
            )
        credentials = get_encryption_service().decrypt_credentials(encrypted)
        # Optionally prefer the credential store record.
        if not credentials:
            fallback = await self.credentials.decrypt_for(
                workspace_id=connection.workspace_id,
                provider=connection.provider,
                session=session,
            )
            if fallback:
                credentials = fallback
        if not credentials:
            raise CredentialNotFound("no usable credentials for connection")

        instance = get_registry().build(
            connection.provider,
            context=ProviderContext(
                provider=connection.provider,
                workspace_id=connection.workspace_id,
                credentials=credentials,
                metadata=connection.metadata_json or {},
            ),
        )
        return instance, credentials

    def validate_payload(self, provider: str, action: str, payload: dict[str, Any]) -> None:
        """Validates an action payload against the capability params schema."""
        provider_cls = get_registry().get(provider)
        capability = provider_cls.get_capability(action)
        if capability is None:
            return
        schema = capability.params_schema
        required = schema.get("required", [])
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValidationError(
                f"missing required payload fields: {', '.join(missing)}",
                provider=provider,
                details={"missing": missing, "schema": schema},
            )


def _mask(credentials: dict[str, Any]) -> dict[str, str]:
    return get_encryption_service().mask_credentials(credentials)


integration_manager: IntegrationManager | None = None


def get_integration_manager() -> IntegrationManager:
    global integration_manager
    if integration_manager is None:
        integration_manager = IntegrationManager()
    return integration_manager
