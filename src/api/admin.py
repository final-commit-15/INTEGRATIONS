"""Admin endpoints: global integration, webhook, and audit views."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from dependencies import AdminDep
from models import IntegrationAuditLog, IntegrationConnection, WebhookEvent, WebhookSubscription
from schemas import (
    AdminAuditRow,
    AdminIntegrationRow,
    AdminWebhookRow,
    ApiResponse,
    PaginatedResult,
)
from services.audit_service import get_audit_service

router = APIRouter()


@router.get("/integrations", response_model=ApiResponse[PaginatedResult[AdminIntegrationRow]])
async def admin_integrations(
    principal: AdminDep,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    provider: str | None = None,
) -> ApiResponse[PaginatedResult[AdminIntegrationRow]]:
    """List integration connections across all workspaces."""
    query = select(IntegrationConnection).order_by(IntegrationConnection.created_at.desc())
    if provider:
        query = query.where(IntegrationConnection.provider == provider)
    count = await session.execute(select(func.count()).select_from(query.subquery()))
    result = await session.execute(query.offset(offset).limit(limit))
    rows = [AdminIntegrationRow.model_validate(c) for c in result.scalars().all()]
    return ApiResponse(data=PaginatedResult(items=rows, total=count.scalar_one()))


@router.get("/webhooks", response_model=ApiResponse[PaginatedResult[AdminWebhookRow]])
async def admin_webhooks(
    principal: AdminDep,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedResult[AdminWebhookRow]]:
    """List webhook subscriptions across all workspaces."""
    query = select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
    count = await session.execute(select(func.count()).select_from(query.subquery()))
    result = await session.execute(query.offset(offset).limit(limit))
    rows = [AdminWebhookRow.model_validate(s) for s in result.scalars().all()]
    return ApiResponse(data=PaginatedResult(items=rows, total=count.scalar_one()))


@router.get("/logs", response_model=ApiResponse[PaginatedResult[AdminAuditRow]])
async def admin_logs(
    principal: AdminDep,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    provider: str | None = None,
    workspace_id: str | None = None,
) -> ApiResponse[PaginatedResult[AdminAuditRow]]:
    """List audit log entries across all workspaces."""
    rows = await get_audit_service().list(
        session=session,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )
    filtered = [r for r in rows if not provider or r.provider == provider]
    return ApiResponse(
        data=PaginatedResult(
            items=[AdminAuditRow.model_validate(r) for r in filtered],
            total=len(filtered),
        )
    )


@router.get("/stats", response_model=ApiResponse[dict])
async def admin_stats(
    principal: AdminDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Operational aggregate counters (no PII)."""
    connections = (await session.execute(select(func.count()).select_from(IntegrationConnection))).scalar_one()
    subscriptions = (await session.execute(select(func.count()).select_from(WebhookSubscription))).scalar_one()
    events = (await session.execute(select(func.count()).select_from(WebhookEvent))).scalar_one()
    audit = (await session.execute(select(func.count()).select_from(IntegrationAuditLog))).scalar_one()
    return ApiResponse(
        data={
            "connections": connections,
            "webhook_subscriptions": subscriptions,
            "webhook_events": events,
            "audit_logs": audit,
        }
    )
