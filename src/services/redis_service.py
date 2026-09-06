"""Redis client management and shared helpers for cache, locks, and queues."""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from config import settings
from exceptions import ProviderUnavailable

_client: Redis | None = None


async def get_redis() -> Redis:
    """Return a lazily-created async Redis client."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping_redis() -> bool:
    try:
        client = await get_redis()
        result = await client.ping()
        return bool(result)
    except Exception:
        return False


async def cache_get_json(key: str) -> Any | None:
    client = await get_redis()
    raw = await client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def cache_set_json(key: str, value: Any, ttl: int | None = None) -> None:
    client = await get_redis()
    serialized = json.dumps(value, default=str)
    if ttl is None:
        ttl = settings.redis_token_cache_ttl
    await client.set(key, serialized, ex=ttl)


class WebhookDedup:
    """Redis-backed deduplication guard for inbound webhook events."""

    def __init__(self, *, namespace: str = "webhook:dedup") -> None:
        self.namespace = namespace

    async def seen(self, dedup_key: str) -> bool:
        """Return True if the key was already processed, otherwise mark it."""
        client = await get_redis()
        full = f"{self.namespace}:{dedup_key}"
        return bool(await client.set(full, "1", nx=True, ex=settings.redis_webhook_ttl)) is False


class RedisLock:
    """Simple SET-NX-EX distributed lock."""

    def __init__(self, name: str, *, ttl: int = 60) -> None:
        self.name = name
        self.ttl = ttl

    async def acquire(self) -> bool:
        client = await get_redis()
        return bool(await client.set(self.name, "1", nx=True, ex=self.ttl))

    async def release(self) -> None:
        client = await get_redis()
        await client.delete(self.name)


async def enqueue(schedule_key: str, payload: dict[str, Any]) -> None:
    """Push a job into a Redis list for workers."""
    client = await get_redis()
    try:
        await client.rpush(schedule_key, json.dumps(payload, default=str))
    except Exception as exc:
        raise ProviderUnavailable("redis queue unavailable") from exc
