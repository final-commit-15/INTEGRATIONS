"""Audit log service for security-sensitive integration events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import IntegrationAuditLog


class AuditService:
    """Writes and queries the immutable integration audit trail."""

    async def record(
        self,
        *,
        session: AsyncSession,
        workspace_id: str,
        action: str,
        actor_id: str | None = None,
        provider: str | None = None,
        resource: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        outcome: str = "success",
    ) -> IntegrationAuditLog:
        entry = IntegrationAuditLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            provider=provider,
            action=action,
            resource=resource,
            details=details or {},
            ip_address=ip_address,
            outcome=outcome,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry

    async def list(
        self,
        *,
        session: AsyncSession,
        workspace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IntegrationAuditLog]:
        query = select(IntegrationAuditLog).order_by(IntegrationAuditLog.created_at.desc())
        if workspace_id:
            query = query.where(IntegrationAuditLog.workspace_id == workspace_id)
        result = await session.execute(query.limit(limit).offset(offset))
        return list(result.scalars().all())


audit_service = AuditService()


def get_audit_service() -> AuditService:
    return audit_service
