import asyncio

import pytest

from agentforge_integrations.utils.rate_limiter import TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_token_bucket_initial():
    limiter = TokenBucketRateLimiter(rate=1.0, capacity=5)
    for _ in range(5):
        await limiter.acquire("key1")
    # Should be able to acquire 5 immediately
    # 6th should block; we'll test time
    start = asyncio.get_event_loop().time()
    await limiter.acquire("key1")
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed >= 0.9  # roughly 1 second


@pytest.mark.asyncio
async def test_multiple_keys():
    limiter = TokenBucketRateLimiter(rate=10, capacity=5)
    await limiter.acquire("a")
    await limiter.acquire("b")
    # Both should get tokens