"""HTTP retry helpers built on tenacity, tailored for third-party providers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from exceptions import ProviderUnavailable, RateLimitExceeded

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy shared by every provider call."""

    max_attempts: int = 3
    min_wait: float = 0.5
    max_wait: float = 8.0
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitExceeded):
        return True
    if isinstance(exc, ProviderUnavailable):
        return True
    return False


async def with_retry(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> T:
    """Run an async callable with exponential-backoff + jitter retries."""
    policy = policy or RetryPolicy()
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type((RateLimitExceeded, ProviderUnavailable)),
        stop=stop_after_attempt(policy.max_attempts),
        wait=wait_exponential_jitter(policy.min_wait, policy.max_wait),
        reraise=True,
    ):
        with attempt:
            return await func(*args, **kwargs)
    raise RuntimeError("unreachable")  # pragma: no cover


def is_retryable_status(status: int, policy: RetryPolicy | None = None) -> bool:
    return status in (policy or RetryPolicy()).retry_on_status


async def sleep_exponential(attempt: int, *, base: float = 0.5, max_wait: float = 8.0) -> None:
    wait_ms = min(base * (2 ** max(0, attempt - 1)), max_wait)
    await asyncio.sleep(wait_ms)
