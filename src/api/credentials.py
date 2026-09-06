"""Credential management endpoints (API-key style credentials)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from dependencies import PrincipalDep
from exceptions import IntegrationError
from schemas import ApiResponse, CredentialCreate, CredentialOut, CredentialUpdate
from services.audit_service import get_audit_service
from services.credential_service import get_credential_service
from services.encryption_service import get_encryption_service

router = APIRouter()


@router.post("", response_model=ApiResponse[CredentialOut])
async def create_credential(
    payload: CredentialCreate,
    request: Request,
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[CredentialOut]:
    """Store provider credentials (encrypted at rest)."""
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise IntegrationError("workspace required")
    record = await get_credential_service().create(
        workspace_id=workspace_id,
        provider=payload.provider,
        data=payload,
        session=session,
    )
    masked = get_encryption_service().mask_credentials(payload.credentials)
    await get_audit_service().record(
        session=session,
        workspace_id=workspace_id,
        actor_id=principal.user_id,
        action="credential.create",
        provider=payload.provider,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=CredentialOut(
            provider=record.provider,
            name=record.name,
            created_at=record.created_at,
            updated_at=record.updated_at,
            expires_at=record.expires_at,
            masked_fields=masked,
        )
    )


@router.patch("/{provider}", response_model=ApiResponse[CredentialOut])
async def update_credential(
    provider: str,
    payload: CredentialUpdate,
    request: Request,
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[CredentialOut]:
    """Update stored credentials for a provider."""
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise IntegrationError("workspace required")
    record = await get_credential_service().update(
        workspace_id=workspace_id,
        provider=provider,
        data=payload,
        session=session,
    )
    masked = get_encryption_service().mask_credentials(payload.credentials)
    await get_audit_service().record(
        session=session,
        workspace_id=workspace_id,
        actor_id=principal.user_id,
        action="credential.update",
        provider=provider,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(
        data=CredentialOut(
            provider=record.provider,
            name=record.name,
            created_at=record.created_at,
            updated_at=record.updated_at,
            expires_at=record.expires_at,
            masked_fields=masked,
        )
    )


@router.get("", response_model=ApiResponse[list[CredentialOut]])
async def list_credentials(
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CredentialOut]]:
    """List masked credential summaries for the workspace."""
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise IntegrationError("workspace required")
    records = await get_credential_service().list(workspace_id=workspace_id, session=session)
    out = []
    for record in records:
        out.append(
            CredentialOut(
                provider=record.provider,
                name=record.name,
                created_at=record.created_at,
                updated_at=record.updated_at,
                expires_at=record.expires_at,
            )
        )
    return ApiResponse(data=out)


@router.delete("/{provider}", response_model=ApiResponse[dict])
async def delete_credential(
    provider: str,
    request: Request,
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Delete stored credentials for a provider."""
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise IntegrationError("workspace required")
    await get_credential_service().delete(
        workspace_id=workspace_id, provider=provider, session=session
    )
    await get_audit_service().record(
        session=session,
        workspace_id=workspace_id,
        actor_id=principal.user_id,
        action="credential.delete",
        provider=provider,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data={"provider": provider, "deleted": True})
