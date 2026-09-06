"""Tests for the per-provider circuit breaker."""

from __future__ import annotations

import time

import pytest

from exceptions import CircuitBreakerOpen
from utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    breaker_for,
)


def test_initial_state_closed() -> None:
    breaker = CircuitBreaker()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_opens_after_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    for _ in range(2):
        breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpen):
        breaker.allow_request()


def test_success_resets_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=5)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    # Failures were reset, so we need 5 fresh failures to open.
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state is CircuitState.OPEN


def test_half_open_probe_after_recovery_timeout() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, success_threshold_half_open=2)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN

    time.sleep(0.06)
    # Reading state transitions OPEN -> HALF_OPEN after the timeout.
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.allow_request() is True


def test_half_open_recovers_with_successes() -> None:
    breaker = CircuitBreaker(
        failure_threshold=2, recovery_timeout=0.0, success_threshold_half_open=2
    )
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN or breaker.state is CircuitState.HALF_OPEN

    breaker.record_success()
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


def test_reset_returns_to_closed() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    breaker.reset()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_registry_returns_singleton_per_provider() -> None:
    registry = CircuitBreakerRegistry()
    first = registry.get("github")
    second = registry.get("github")
    assert first is second
    assert registry.get("slack") is not first


def test_registry_reset_all_resets_breakers() -> None:
    registry = CircuitBreakerRegistry()
    breaker = registry.get("stripe")
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    registry.reset_all()
    assert breaker.state is CircuitState.CLOSED


def test_breaker_for_returns_shared_instance() -> None:
    assert breaker_for("github") is breaker_for("github")
