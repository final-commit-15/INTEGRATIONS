"""Integration management and action execution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from dependencies import PrincipalDep
from exceptions import IntegrationError
from schemas import (
    ApiResponse,
    CapabilityOut,
    ExecuteActionRequest,
    ExecuteActionResult,
    IntegrationConnectionOut,
    Principal,
    ValidateConnectionResult,
)
from services.audit_service import get_audit_service
from services.integration_manager import get_integration_manager

router = APIRouter()


@router.get("", response_model=ApiResponse[list[dict]], name="list_providers")
def list_providers() -> ApiResponse[list[dict]]:
    """List all registered providers with capability summaries."""
    return ApiResponse(data=get_integration_manager().list_providers())


@router.get("/{provider}", response_model=ApiResponse[dict], name="provider_info")
def provider_info(provider: str) -> ApiResponse[dict]:
    """Get metadata for a single provider."""
    return ApiResponse(data=get_integration_manager().get_provider_info(provider))


@router.get("/{provider}/capabilities", response_model=ApiResponse[list[CapabilityOut]])
def provider_capabilities(provider: str) -> ApiResponse[list[CapabilityOut]]:
    """List executable capabilities for a provider."""
    return ApiResponse(data=get_integration_manager().list_capabilities(provider))


def _ws_id(principal: Principal, workspace_id: str | None) -> str:
    """Resolve workspace: explicit query param, else auth principal claim."""
    if workspace_id:
        return workspace_id
    if principal and principal.workspace_id:
        return principal.workspace_id
    raise IntegrationError("workspace_id is required")


@router.get("/connections", response_model=ApiResponse[list[IntegrationConnectionOut]])
async def list_connections(
    principal: PrincipalDep,
    workspace_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[IntegrationConnectionOut]]:
    """List integration connections for the resolved workspace."""
    ws_id = _ws_id(principal, workspace_id)
    connections = await get_integration_manager().list_connections(workspace_id=ws_id, session=session)
    return ApiResponse(data=[IntegrationConnectionOut.model_validate(c) for c in connections])


@router.post("/{provider}/execute", response_model=ApiResponse[ExecuteActionResult])
async def execute_action(
    provider: str,
    payload_request: ExecuteActionRequest,
    request: Request,
    principal: PrincipalDep,
    workspace_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ExecuteActionResult]:
    """Execute an action against a connected provider."""
    ws_id = _ws_id(principal, workspace_id)
    manager = get_integration_manager()
    manager.validate_payload(provider, payload_request.action, payload_request.payload)
    result, latency_ms = await manager.execute_action(
        workspace_id=ws_id,
        provider=provider,
        action=payload_request.action,
        payload=payload_request.payload,
        session=session,
    )
    await get_audit_service().record(
        session=session,
        workspace_id=ws_id,
        actor_id=principal.user_id,
        action=f"{provider}.{payload_request.action}",
        provider=provider,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=ExecuteActionResult(
            provider=provider,
            action=payload_request.action,
            success=True,
            data=result,
            latency_ms=latency_ms,
        )
    )


@router.post("/{provider}/validate", response_model=ApiResponse[ValidateConnectionResult])
async def validate(
    provider: str,
    principal: PrincipalDep,
    workspace_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ValidateConnectionResult]:
    """Validate that a stored connection still works."""
    ws_id = _ws_id(principal, workspace_id)
    checks = await get_integration_manager().validate_connection(
        workspace_id=ws_id, provider=provider, session=session
    )
    return ApiResponse(
        data=ValidateConnectionResult(provider=provider, valid=checks["valid"], checks=checks)
    )


@router.post("/{provider}/disconnect", response_model=ApiResponse[dict])
async def disconnect_provider(
    provider: str,
    principal: PrincipalDep,
    workspace_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Deactivate a connection without revoking the provider token."""
    ws_id = _ws_id(principal, workspace_id)
    await get_integration_manager().disconnect(workspace_id=ws_id, provider=provider, session=session)
    return ApiResponse(data={"provider": provider, "disconnected": True})
