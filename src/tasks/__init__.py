"""/tasks package. Celery app configuration and task decorators."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from celery import Celery
from celery.schedules import crontab

from config import settings

T = TypeVar("T")

celery_app = Celery(
    "agentforge_integrations",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "tasks.token_tasks",
        "tasks.webhook_tasks",
        "tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    "refresh-oauth-tokens-hourly": {
        "task": "tasks.token_tasks.refresh_ending_tokens_task",
        "schedule": crontab(minute=5),
    },
    "retry-failed-webhooks-every-2m": {
        "task": "tasks.webhook_tasks.retry_webhooks_task",
        "schedule": 120.0,
    },
    "dead-letter-overflow-hourly": {
        "task": "tasks.webhook_tasks.dead_letter_task",
        "schedule": crontab(minute=35),
    },
    "cleanup-expired-oauth-states-daily": {
        "task": "tasks.maintenance_tasks.cleanup_expired_states_task",
        "schedule": 3600 * 6,
    },
    "rotate-expired-credentials-daily": {
        "task": "tasks.maintenance_tasks.rotate_expired_credentials_task",
        "schedule": 3600 * 24,
    },
}


def async_task(name: str | None = None) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., T]]:
    """Wrap an async coroutine so it runs as a pure Celery task inside an event loop."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., T]:
        @celery_app.task(name=name or f"agentforge.{func.__name__}", bind=True)
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> T:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                raise RuntimeError("celery worker is running within an event loop; use async execution mode")
            return asyncio.run(func(*args, **kwargs))

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator
