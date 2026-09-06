"""Lightweight circuit breaker used per-provider to avoid hammering degraded APIs."""

from __future__ import annotations

import threading
import time
from enum import Enum

from exceptions import CircuitBreakerOpen


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider circuit breaker with failure thresholds and half-open probe."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold_half_open: int = 2,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold_half_open
        self._lock = threading.Lock()
        self._failures = 0
        self._successes_half_open = 0
        self._last_failure_time = 0.0
        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state is CircuitState.OPEN and time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._successes_half_open = 0
            return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state is CircuitState.OPEN:
            raise CircuitBreakerOpen(
                "provider circuit breaker is open",
                details={"recovery_ms": int(self.recovery_timeout * 1000)},
            )
        return True

    def record_success(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._successes_half_open += 1
                if self._successes_half_open >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
                    self._successes_half_open = 0
            else:
                self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()
            if self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._successes_half_open = 0


class CircuitBreakerRegistry:
    """Registry of per-provider circuit breakers with default factory."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, provider: str) -> CircuitBreaker:
        with self._lock:
            if provider not in self._breakers:
                self._breakers[provider] = CircuitBreaker()
            return self._breakers[provider]

    def reset_all(self) -> None:
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


breaker_registry = CircuitBreakerRegistry()


def breaker_for(provider: str) -> CircuitBreaker:
    return breaker_registry.get(provider)
