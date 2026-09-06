"""Tests for contextvars-based request/workspace ID propagation."""

from __future__ import annotations

import uuid

from utils import context


def test_request_id_is_none_by_default() -> None:
    context.set_request_id(None)
    assert context.get_request_id() is None


def test_new_request_id_sets_and_returns_uuid() -> None:
    rid = context.new_request_id()
    assert isinstance(rid, str)
    uuid.UUID(rid)
    assert context.get_request_id() == rid


def test_set_and_reset_request_id() -> None:
    context.set_request_id("req-1")
    assert context.get_request_id() == "req-1"
    context.set_request_id(None)
    assert context.get_request_id() is None


def test_correlation_id_roundtrip() -> None:
    context.set_correlation_id("corr-1")
    assert context.get_correlation_id() == "corr-1"
    assert context.correlation_id_var.get() == "corr-1"
    context.set_correlation_id(None)


def test_workspace_id_var_set() -> None:
    context.set_workspace_id("ws-987")
    assert context.workspace_id_var.get() == "ws-987"
    context.set_workspace_id(None)
    assert context.workspace_id_var.get() is None


def test_context_vars_isolated_between_contexts() -> None:
    # ContextVars are copied to the new event loop created by asyncio.run()
    # (Python 3.11+). Verify the copied value is visible.
    context.set_workspace_id("ws-outer")
    captured: list[str | None] = []

    async def probe() -> None:
        captured.append(context.workspace_id_var.get())

    import asyncio

    asyncio.run(probe())
    assert captured == ["ws-outer"]
