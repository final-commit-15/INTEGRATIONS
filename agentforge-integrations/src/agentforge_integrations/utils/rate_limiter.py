import asyncio
import time


class RateLimiter:
    """Abstract rate limiter interface."""

    async def acquire(self, key: str = "default") -> None:
        raise NotImplementedError


class TokenBucketRateLimiter(RateLimiter):
    """Token bucket algorithm with safe async locking."""

    def __init__(self, rate: float, capacity: int, initial_tokens: int | None = None):
        self.rate = rate
        self.capacity = capacity
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str = "default") -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                if key not in self._tokens:
                    self._tokens[key] = float(self.capacity)
                    self._last_refill[key] = now

                elapsed = now - self._last_refill[key]
                new_tokens = elapsed * self.rate
                if new_tokens > 0:
                    self._tokens[key] = min(self.capacity, self._tokens[key] + new_tokens)
                    self._last_refill[key] = now

                if self._tokens[key] >= 1.0:
                    self._tokens[key] -= 1.0
                    return

                # Need to wait
                wait_time = (1.0 - self._tokens[key]) / self.rate
            # Release lock before sleeping
            await asyncio.sleep(wait_time)
            # Loop re-acquires lock and re-calculates