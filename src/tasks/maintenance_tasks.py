"""Celery maintenance tasks: state cleanup, credential rotation, audits."""

from __future__ import annotations

import structlog

from database.database import async_session_factory
from services.token_refresh import cleanup_expired_credentials, cleanup_expired_states
from tasks import async_task

log = structlog.get_logger(__name__)


@async_task(name="agentforge.cleanup_expired_states")
async def cleanup_expired_states_task() -> dict[str, int]:
    async with async_session_factory() as session:
        try:
            removed = await cleanup_expired_states(session=session)
        finally:
            await session.close()
    log.info("oauth_state_cleanup", removed=removed)
    return {"removed": removed}


@async_task(name="agentforge.rotate_expired_credentials")
async def rotate_expired_credentials_task() -> dict[str, int]:
    from services.credential_service import get_credential_service

    async with async_session_factory() as session:
        try:
            rotated = await get_credential_service().rotate_expired(session=session)
        finally:
            await session.close()
    log.info("credential_rotation", affected=len(rotated))
    return {"affected": len(rotated)}


@async_task(name="agentforge.cleanup_expired_credentials")
async def cleanup_expired_credentials_task() -> dict[str, int]:
    async with async_session_factory() as session:
        try:
            removed = await cleanup_expired_credentials(session=session)
        finally:
            await session.close()
    log.info("credential_cleanup", removed=removed)
    return {"removed": removed}
