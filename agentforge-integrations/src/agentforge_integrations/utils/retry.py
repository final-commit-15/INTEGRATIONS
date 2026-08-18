import asyncio
import logging
from collections.abc import Callable
from functools import wraps

from ..core.exceptions import (
    RateLimitError,
    TimeoutError,
)

logger = logging.getLogger(__name__)

# Default retryable exceptions: network, timeouts, server errors, rate limits
DEFAULT_RETRYABLE = (
    TimeoutError,
    RateLimitError,
    ConnectionError,
    # httpx specific
    asyncio.TimeoutError,
    # We'll also catch HTTP status 5xx via response handling
)


def retry(
    max_attempts: int = 3,
    backoff: float = 1.0,
    max_backoff: float = 30.0,
    exceptions: tuple[type[Exception], ...] = DEFAULT_RETRYABLE,
    on_retry: Callable[[Exception, int], None] | None = None,
):
    """Async retry decorator with exponential backoff and jitter.
    Only retries on specified exceptions (default: network/timeout/rate-limit).
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 1
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        raise
                    wait = min(backoff * (2 ** (attempt - 1)), max_backoff)
                    # Jitter
                    wait = wait * (0.8 + 0.4 * (hash(str(e)) % 100) / 100.0)
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {wait:.2f}s: {e}"
                    )
                    if on_retry:
                        on_retry(e, attempt)
                    await asyncio.sleep(wait)
                    attempt += 1
        return wrapper
    return decorator


def retry_on_rate_limit(max_attempts: int = 5):
    """Specialised retry for rate-limit errors."""
    return retry(
        max_attempts=max_attempts,
        backoff=2.0,
        exceptions=(RateLimitError,),
    )