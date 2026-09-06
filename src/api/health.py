"""Health and readiness endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.database import get_db
from schemas import ComponentHealth, HealthResponse
from services.redis_service import ping_redis

router = APIRouter()

_STARTED_AT = time.monotonic()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health(session: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Liveness + dependency readiness (DB and Redis)."""
    components: list[ComponentHealth] = []

    db_start = time.perf_counter()
    try:
        result = await session.execute(text("SELECT 1"))
        await result.scalar_one()
        components.append(
            ComponentHealth(
                name="database",
                status="ok",
                latency_ms=(time.perf_counter() - db_start) * 1000,
            )
        )
    except Exception:
        components.append(ComponentHealth(name="database", status="down"))

    redis_start = time.perf_counter()
    redis_ok = await ping_redis()
    components.append(
        ComponentHealth(
            name="redis",
            status="ok" if redis_ok else "down",
            latency_ms=(time.perf_counter() - redis_start) * 1000,
        )
    )

    status = "ok" if all(c.status == "ok" for c in components) else "degraded"
    down = [c for c in components if c.status != "ok"]
    if down and settings.is_production:
        status = "down"
    return HealthResponse(
        status=status,
        version=settings.app_version,
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 2),
        components=components,
    )


@router.get("/health/live", response_model=dict[str, Any])
async def live() -> dict[str, Any]:
    """Kubernetes liveness probe (process is up)."""
    return {"status": "ok", "uptime_seconds": round(time.monotonic() - _STARTED_AT, 2)}


@router.get("/health/ready", response_model=dict[str, Any])
async def ready(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Kubernetes readiness probe (dependencies reachable)."""
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    redis_ok = await ping_redis()
    status = "ok" if db_ok and redis_ok else "down"
    return {"status": status, "database": db_ok, "redis": redis_ok}
