"""OAuth authorization, callback, and disconnect endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.database import get_db
from dependencies import PrincipalDep
from exceptions import OAuthFailed
from schemas import ApiResponse, OAuthConnectResult
from services.audit_service import get_audit_service
from services.oauth_service import get_oauth_service

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/providers", response_model=ApiResponse[list[dict]], name="oauth_providers")
def list_oauth_providers() -> ApiResponse[list[dict]]:
    """List OAuth-enabled providers alongside their auth metadata."""
    from providers.registry import get_registry

    registry = get_registry()
    payload = []
    for key, provider_cls in registry.all().items():
        if provider_cls.oauth_authorize_url:
            payload.append(
                {
                    "key": provider_cls.provider_key,
                    "name": provider_cls.name,
                    "description": provider_cls.description,
                    "auth_type": provider_cls.auth_type,
                }
            )
    return ApiResponse(data=payload)


@router.get("/connect/{provider}", response_model=ApiResponse[dict], name="oauth_connect")
async def connect(
    provider: str,
    workspace_id: str = Query(..., description="Target workspace id"),
    session: AsyncSession = Depends(get_db),
    scopes: str | None = Query(default=None),
    redirect_uri: str | None = Query(default=None),
) -> ApiResponse[dict]:
    """Generate the OAuth authorization URL for a provider + workspace.

    ``workspace_id`` is a query parameter because the browser redirect flow
    cannot carry a JWT. Callers are expected to enforce authentication upstream.
    """
    scope_list = [s.strip() for s in scopes.split(",")] if scopes else None
    state, verifier, authorization_url = await get_oauth_service().create_authorization_url(
        provider=provider,
        workspace_id=workspace_id,
        session=session,
        scopes=scope_list,
        redirect_uri=redirect_uri,
    )
    return ApiResponse(data={"authorization_url": authorization_url, "state": state})


@router.get("/callback/{provider}")
async def callback(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Exchange the callback authorization code for tokens and store them."""
    audit = get_audit_service()
    if error:
        log.error("oauth_callback_error", provider=provider, error=error)
        return _redirect_error(request, f"oauth_error={error}")
    if not code or not state:
        raise OAuthFailed("missing code or state in OAuth callback", provider=provider)
    try:
        result = await get_oauth_service().handle_callback(
            provider=provider,
            code=code,
            state=state,
            session=session,
        )
    except OAuthFailed as exc:
        await audit.record(
            session=session,
            workspace_id="unknown",
            action="oauth.callback.failed",
            provider=provider,
            details={"error": exc.message},
            outcome="failure",
        )
        return _redirect_error(request, "oauth_exchange_failed")
    await audit.record(
        session=session,
        workspace_id=result["workspace_id"],
        action="oauth.callback.success",
        provider=provider,
        details={"scopes": result["scopes"]},
    )
    target = f"{settings.frontend_url}/integrations/{provider}?connected=1"
    return RedirectResponse(url=target)


@router.post("/disconnect/{provider}", response_model=ApiResponse[OAuthConnectResult])
async def disconnect(
    provider: str,
    request: Request,
    workspace_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    principal: PrincipalDep = None,
) -> ApiResponse[OAuthConnectResult]:
    """Revoke and disconnect a provider for the current workspace."""

    await get_oauth_service().revoke_token(
        provider=provider, workspace_id=workspace_id, session=session
    )
    await get_audit_service().record(
        session=session,
        workspace_id=workspace_id,
        actor_id=principal.user_id if principal else None,
        action="oauth.disconnect",
        provider=provider,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=OAuthConnectResult(
            provider=provider,
            workspace_id=workspace_id,
            connected=False,
            scopes=[],
        )
    )


def _redirect_error(request: Request, reason: str) -> RedirectResponse:
    url = f"{settings.frontend_url}/integrations?error=1&reason={reason}"
    return RedirectResponse(url=url)
