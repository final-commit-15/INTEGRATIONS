"""Context variables for request and correlation ID propagation."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
workspace_id_var: ContextVar[str | None] = ContextVar("workspace_id", default=None)


def new_request_id() -> str:
    value = str(uuid.uuid4())
    request_id_var.set(value)
    return value


def new_correlation_id() -> str:
    value = str(uuid.uuid4())
    correlation_id_var.set(value)
    return value


def set_request_id(value: str | None) -> None:
    request_id_var.set(value)


def set_correlation_id(value: str | None) -> None:
    correlation_id_var.set(value)


def set_workspace_id(value: str | None) -> None:
    workspace_id_var.set(value)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_correlation_id() -> str | None:
    return correlation_id_var.get()
