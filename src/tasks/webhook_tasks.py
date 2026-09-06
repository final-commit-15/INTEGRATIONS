"""Celery tasks for webhook retry, dead-lettering, and dispatch."""

from __future__ import annotations

import structlog

from database.database import async_session_factory
from services.webhook_dispatcher import get_dispatcher
from tasks import async_task

log = structlog.get_logger(__name__)


@async_task(name="agentforge.retry_webhooks")
async def retry_webhooks_task(limit: int = 100) -> dict[str, int]:
    """Re-dispatch failed webhook events within retry budget."""
    async with async_session_factory() as session:
        try:
            count = await get_dispatcher().retry_failed(session=session, limit=limit)
        finally:
            await session.close()
    log.info("webhook_retry_completed", retried=count)
    return {"retried": count}


@async_task(name="agentforge.dead_letter")
async def dead_letter_task(limit: int = 50) -> dict[str, int]:
    """Dead-letter events that exhausted their retry budget."""
    async with async_session_factory() as session:
        try:
            events = await get_dispatcher().dead_letter_overflow(session=session, limit=limit)
        finally:
            await session.close()
    return {"dead_lettered": len(events)}


@async_task(name="agentforge.dispatch_webhook")
async def dispatch_webhook_task(event_id: str) -> dict[str, str]:
    """Dispatch a single persisted event to its subscribers."""
    from sqlalchemy import select

    from models import WebhookEvent

    async with async_session_factory() as session:
        try:
            result = await session.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
            event = result.scalar_one_or_none()
            if event is None:
                return {"status": "not_found", "event_id": event_id}
            await get_dispatcher().dispatch_event(event=event, session=session)
            return {"status": "dispatched", "event_id": event_id}
        finally:
            await session.close()
