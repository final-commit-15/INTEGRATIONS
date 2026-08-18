import pytest

from agentforge_integrations.core.exceptions import RateLimitError
from agentforge_integrations.utils.retry import retry, retry_on_rate_limit


@pytest.mark.asyncio
async def test_retry_success():
    call_count = 0
    @retry(max_attempts=3)
    async def func():
        nonlocal call_count
        call_count += 1
        return "ok"
    result = await func()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_failure_then_success():
    call_count = 0
    @retry(max_attempts=3)
    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("fail")
        return "ok"
    result = await func()
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_rate_limit():
    call_count = 0
    @retry_on_rate_limit(max_attempts=3)
    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RateLimitError("rate limit")
        return "ok"
    result = await func()
    assert result == "ok"
    assert call_count == 3