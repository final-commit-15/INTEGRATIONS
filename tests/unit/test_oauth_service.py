"""Tests for the universal OAuth service (PKCE, token exchange, refresh, revoke).

All token-endpoint HTTP calls are mocked with respx — no real network.
"""

from __future__ import annotations

import hashlib
import urllib.parse

import httpx
import pytest
import respx

from config import settings
from models import Credential, IntegrationConnection, OAuthState
from providers.registry import registry
from services.oauth_service import OAuthService


@pytest.fixture
def oauth_service() -> OAuthService:
    return OAuthService()


def test_pkce_pair_generation() -> None:
    service = OAuthService()
    verifier, challenge = service._generate_pkce_pair()
    assert verifier and challenge
    # Verifier is the urlsafe base64 of 48 random bytes.
    assert len(verifier) >= 60
    assert verifier.isalnum() or "_" in verifier or "-" in verifier
    # Challenge is SHA-256(verifier), base64url, unpadded.

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = service._base64url(digest)
    assert challenge == expected
    assert challenge.isalnum() or "-" in challenge or "_" in challenge


async def test_create_authorization_url_pkce_params(db_session, workspace) -> None:
    service = OAuthService()
    state, verifier, url = await service.create_authorization_url(
        provider="dropbox", workspace_id=workspace.id, session=db_session
    )
    assert state and verifier
    assert url.startswith("https://www.dropbox.com/oauth2/authorize?")
    parsed = urllib.parse.urlparse(url)
    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    assert params["response_type"] == "code"
    assert params.get("client_id", "") == ""
    assert params["state"] == state
    assert params["code_challenge"] == service._base64url(
        __import__("hashlib").sha256(verifier.encode("ascii")).digest()
    )
    assert params["code_challenge_method"] == "S256"
    assert "files.content.read" in params["scope"]
    assert params["redirect_uri"] == f"{settings.oauth_redirect_base_url}/oauth/callback/dropbox"
    assert params["access_type"] == "offline"

    # A state row was persisted with the verifier and workspace.
    row = (
        await db_session.execute(
            __import__("sqlalchemy").select(OAuthState).where(OAuthState.state_token == state)
        )
    ).scalar_one()
    assert row.workspace_id == workspace.id
    assert row.code_verifier == verifier
    assert row.provider == "dropbox"


async def test_authorization_url_scopes_respected(db_session, workspace) -> None:
    service = OAuthService()
    _state, _verifier, url = await service.create_authorization_url(
        provider="dropbox",
        workspace_id=workspace.id,
        session=db_session,
        scopes=["files.content.read"],
    )
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert params["scope"] == "files.content.read"


@respx.mock
async def test_handle_callback_stores_connection_and_credential(db_session, workspace) -> None:
    token_url = "https://api.dropboxapi.com/oauth2/token"
    respx.post(token_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "files.content.read",
            },
        )
    )

    service = OAuthService()
    state, verifier, _url = await service.create_authorization_url(
        provider="dropbox", workspace_id=workspace.id, session=db_session
    )
    result = await service.handle_callback(
        provider="dropbox", code="auth-code", state=state, session=db_session, code_verifier=verifier
    )
    assert result["provider"] == "dropbox"
    assert result["workspace_id"] == workspace.id
    assert result["connection_id"]

    # The request actually carried the auth code + PKCE verifier in the form body.
    assert respx.calls.call_count == 1

    connection = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(IntegrationConnection)
            .where(
                IntegrationConnection.workspace_id == workspace.id,
                IntegrationConnection.provider == "dropbox",
            )
        )
    ).scalar_one()
    assert connection.status == "connected"
    creds = service.encryption.decrypt_credentials(connection.encrypted_credentials)
    assert creds["access_token"] == "at-1"
    assert creds["refresh_token"] == "rt-1"
    assert connection.expires_at is not None

    stored = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(Credential)
            .where(
                Credential.workspace_id == workspace.id,
                Credential.provider == "dropbox",
                Credential.name == "oauth_default",
            )
        )
    ).scalar_one()
    assert service.encryption.decrypt_credentials(stored.encrypted_blob)["access_token"] == "at-1"

    # State was consumed.
    consumed = (
        await db_session.execute(
            __import__("sqlalchemy").select(OAuthState).where(OAuthState.state_token == state)
        )
    ).scalar_one()
    assert consumed.consumed is True


@respx.mock
async def test_handle_callback_swallows_bad_grant_conflict(db_session, workspace) -> None:
    token_url = "https://api.dropboxapi.com/oauth2/token"
    respx.post(token_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at-x",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "",
            },
        )
    )
    service = OAuthService()
    state, verifier, _ = await service.create_authorization_url(
        provider="dropbox", workspace_id=workspace.id, session=db_session
    )
    first = await service.handle_callback(
        provider="dropbox", code="code-1", state=state, session=db_session
    )
    # Re-running callback with the same (now-consumed) state must fail cleanly.
    from exceptions import OAuthFailed

    with pytest.raises(OAuthFailed):
        await service.handle_callback(
            provider="dropbox", code="code-2", state=state, session=db_session
        )
    assert first["connection_id"]


@respx.mock
async def test_refresh_access_token_updates_credentials(db_session, workspace) -> None:
    token_url = "https://api.dropboxapi.com/oauth2/token"
    respx.post(token_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )
    service = OAuthService()
    state, verifier, _ = await service.create_authorization_url(
        provider="dropbox", workspace_id=workspace.id, session=db_session
    )
    await service.handle_callback(provider="dropbox", code="c", state=state, session=db_session, code_verifier=verifier)

    # Second exchange returns a new access token.
    respx.post(token_url).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "at-2", "expires_in": 7200, "token_type": "Bearer"},
        )
    )
    creds, encrypted = await service.refresh_access_token(
        provider="dropbox", workspace_id=workspace.id, session=db_session
    )
    assert creds["access_token"] == "at-2"
    # refresh_token is preserved from the original exchange.
    assert creds["refresh_token"] == "rt-1"
    connection = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(IntegrationConnection)
            .where(
                IntegrationConnection.workspace_id == workspace.id,
                IntegrationConnection.provider == "dropbox",
            )
        )
    ).scalar_one()
    assert service.encryption.decrypt_credentials(connection.encrypted_credentials)["access_token"] == "at-2"
    assert encrypted is not None


@respx.mock
async def test_refresh_without_stored_refresh_token_raises(db_session, workspace) -> None:
    token_url = "https://api.dropboxapi.com/oauth2/token"
    respx.post(token_url).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "at-1", "expires_in": 3600, "token_type": "Bearer"},
        )
    )
    service = OAuthService()
    state, verifier, _ = await service.create_authorization_url(
        provider="dropbox", workspace_id=workspace.id, session=db_session
    )
    await service.handle_callback(provider="dropbox", code="c", state=state, session=db_session, code_verifier=verifier)

    from exceptions import TokenExpired

    # Overwrite the stored blob with credentials that have no refresh token.
    connection = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(IntegrationConnection)
            .where(
                IntegrationConnection.workspace_id == workspace.id,
                IntegrationConnection.provider == "dropbox",
            )
        )
    ).scalar_one()
    connection.encrypted_credentials = service.encryption.encrypt_credentials({"access_token": "at-only"})
    await db_session.commit()

    with pytest.raises(TokenExpired):
        await service.refresh_access_token(
            provider="dropbox", workspace_id=workspace.id, session=db_session
        )


async def test_revoke_token_without_revoke_url_marks_revoked(db_session, workspace) -> None:
    service = OAuthService()
    assert registry.get("dropbox").oauth_revoke_url == ""

    connection = IntegrationConnection(
        workspace_id=workspace.id,
        provider="dropbox",
        status="connected",
        encrypted_credentials=service.encryption.encrypt_credentials(
            {"access_token": "at-1", "refresh_token": "rt-1"}
        ),
        scopes=["files.content.read"],
    )
    db_session.add(connection)
    await db_session.commit()

    await service.revoke_token(provider="dropbox", workspace_id=workspace.id, session=db_session)

    connection = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(IntegrationConnection)
            .where(
                IntegrationConnection.workspace_id == workspace.id,
                IntegrationConnection.provider == "dropbox",
            )
        )
    ).scalar_one()
    assert connection.status == "revoked"
    assert connection.is_active is False


@respx.mock
async def test_revoke_token_with_revoke_url_posts(db_session, workspace) -> None:
    revoke_url = "https://oauth2.googleapis.com/revoke"
    respx.post(revoke_url).mock(return_value=httpx.Response(200, json={}))
    service = OAuthService()
    assert registry.get("gmail").oauth_revoke_url == revoke_url

    connection = IntegrationConnection(
        workspace_id=workspace.id,
        provider="gmail",
        status="connected",
        encrypted_credentials=service.encryption.encrypt_credentials(
            {"access_token": "at-1", "refresh_token": "rt-1"}
        ),
        scopes=["gmail.readonly"],
    )
    db_session.add(connection)
    await db_session.commit()

    await service.revoke_token(provider="gmail", workspace_id=workspace.id, session=db_session)
    assert respx.calls.call_count == 1
    connection = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(IntegrationConnection)
            .where(
                IntegrationConnection.workspace_id == workspace.id,
                IntegrationConnection.provider == "gmail",
            )
        )
    ).scalar_one()
    assert connection.status == "revoked"
    assert connection.is_active is False
    assert connection.encrypted_credentials is None
