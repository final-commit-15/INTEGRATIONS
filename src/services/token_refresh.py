"""Token refresh scheduling and cleanup utilities."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Credential, IntegrationConnection, OAuthState
from services.oauth_service import get_oauth_service


async def refresh_ending_tokens(
    *,
    session: AsyncSession,
    within_minutes: int = 30,
    limit: int = 50,
) -> int:
    """Refresh access tokens whose expiry is approaching or passed."""
    from telemetry import metrics

    cutoff = datetime.now(UTC)
    result = await session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.is_active.is_(True),
            IntegrationConnection.encrypted_credentials.is_not(None),
            or_(
                IntegrationConnection.expires_at.is_(None),
                IntegrationConnection.expires_at <= cutoff,
            ),
        ).limit(limit)
    )
    refreshed = 0
    oauth = get_oauth_service()
    for connection in result.scalars().all():
        try:
            await oauth.refresh_access_token(
                provider=connection.provider,
                workspace_id=connection.workspace_id,
                session=session,
            )
            refreshed += 1
            metrics.inc_oauth_refresh(connection.provider)
        except Exception:
            pass
    return refreshed


async def cleanup_expired_states(*, session: AsyncSession) -> int:
    """Delete consumed or expired OAuth state records."""
    result = await session.execute(
        select(OAuthState).where(
            or_(
                OAuthState.consumed.is_(True),
                OAuthState.expires_at < datetime.now(UTC),
            )
        )
    )
    states = list(result.scalars().all())
    for state in states:
        await session.delete(state)
    await session.commit()
    return len(states)


async def cleanup_expired_credentials(*, session: AsyncSession) -> int:
    """Remove credential records that are expired beyond a grace period."""
    result = await session.execute(
        select(Credential).where(
            Credential.expires_at.is_not(None),
            Credential.expires_at < datetime.now(UTC),
        )
    )
    credentials = list(result.scalars().all())
    for credential in credentials:
        await session.delete(credential)
    await session.commit()
    return len(credentials)
