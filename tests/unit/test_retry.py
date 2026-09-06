"""Tests for tenacity-based retry helpers."""

from __future__ import annotations

import pytest

from exceptions import ProviderUnavailable, RateLimitExceeded
from utils.retry import RetryPolicy, is_retryable_status, with_retry


def test_retry_policy_defaults() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.retry_on_status == (429, 500, 502, 503, 504)


def test_is_retryable_status() -> None:
    assert is_retryable_status(429) is True
    assert is_retryable_status(503) is True
    assert is_retryable_status(200) is False
    assert is_retryable_status(401) is False


async def test_with_retry_succeeds_first_try() -> None:
    calls = 0

    async def work() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await with_retry(work, policy=RetryPolicy(min_wait=0.0, max_wait=0.1))
    assert result == "ok"
    assert calls == 1


async def test_with_retry_recovers_after_rate_limit() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RateLimitExceeded("nope", provider="x")
        return "recovered"

    result = await with_retry(
        flaky,
        policy=RetryPolicy(max_attempts=5, min_wait=0.0, max_wait=0.1),
    )
    assert result == "recovered"
    assert calls == 3


async def test_with_retry_recovers_after_provider_unavailable() -> None:
    async def flaky() -> str:
        raise ProviderUnavailable("boom", provider="x")

    # The callable raises a retryable error every time; reraise=True propagates it.
    with pytest.raises(ProviderUnavailable):
        await with_retry(flaky, policy=RetryPolicy(max_attempts=2, min_wait=0.0, max_wait=0.1))


async def test_with_retry_passes_args_and_kwargs() -> None:
    seen: list[int] = []

    async def work(value: int, *, scale: int = 1) -> int:
        seen.append(value)
        return value * scale

    assert await with_retry(work, 21, scale=2, policy=RetryPolicy(min_wait=0.0, max_wait=0.1)) == 42
    assert seen == [21]


async def test_with_retry_non_retryable_exception_propagates_immediately() -> None:
    calls = 0

    async def work() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await with_retry(work, policy=RetryPolicy(max_attempts=4, min_wait=0.0, max_wait=0.1))
    assert calls == 1
