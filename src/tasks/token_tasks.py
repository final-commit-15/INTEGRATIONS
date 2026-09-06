"""Celery tasks for OAuth token maintenance."""

from __future__ import annotations

import structlog

from database.database import async_session_factory
from services.token_refresh import refresh_ending_tokens
from tasks import async_task

log = structlog.get_logger(__name__)


@async_task(name="agentforge.refresh_ending_tokens")
async def refresh_ending_tokens_task() -> dict[str, int]:
    """Refresh access tokens approaching or past their expiry."""
    async with async_session_factory() as session:
        try:
            refreshed = await refresh_ending_tokens(session=session, limit=200)
        finally:
            await session.close()
    log.info("token_refresh_completed", refreshed=refreshed)
    return {"refreshed": refreshed}


@async_task(name="agentforge.refresh_single_token")
async def refresh_single_token_task(provider: str, workspace_id: str) -> dict[str, str | bool]:
    """Force refresh of a single workspace/provider token."""
    from services.oauth_service import get_oauth_service

    async with async_session_factory() as session:
        try:
            await get_oauth_service().refresh_access_token(
                provider=provider, workspace_id=workspace_id, session=session
            )
            return {"provider": provider, "workspace_id": workspace_id, "success": True}
        except Exception as exc:
            log.error("single_token_refresh_failed", provider=provider, error=str(exc))
            return {"provider": provider, "workspace_id": workspace_id, "success": False}
        finally:
            await session.close()
