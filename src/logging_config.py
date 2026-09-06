"""Structured logging configuration using structlog.

Provides JSON output in production, colorful console rendering in development,
request/correlation ID propagation, and secret masking.

Note: this module is named ``logging_config`` (not ``logging``) to avoid
shadowing Python's stdlib ``logging`` for structlog, httpx, and uvicorn.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from config import settings

SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "authorization",
    "api_key",
    "session_id",
    "cookie",
}


def _mask_secrets(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Mask known-sensitive field names in the log event."""
    for key in event_dict:
        lowered = str(key).lower()
        if lowered in SENSITIVE_KEYS or any(s in lowered for s in ("secret", "token", "password")):
            event_dict[key] = "[REDACTED]"
    return event_dict


def _add_request_meta(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Attach correlation and request IDs from the context vars."""
    from utils.context import correlation_id_var, request_id_var

    request_id = request_id_var.get()
    correlation_id = correlation_id_var.get()
    if request_id:
        event_dict["request_id"] = request_id
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def configure_logging(*, debug: bool | None = None) -> None:
    """Configure root and structlog logging."""
    debug = settings.debug if debug is None else debug
    level = logging.DEBUG if debug else settings.log_level.upper()

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_request_meta,
    ]
    if not debug:
        processors.append(_mask_secrets)

    renderer: Any
    if debug:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        processors.append(structlog.stdlib.ProcessorFormatter.wrap_for_formatter)
        renderer = None

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    if debug:
        formatter: logging.Formatter = structlog.dev.ConsoleRenderer()
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _mask_secrets,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ]
        )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers in production.
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING if not debug else logging.DEBUG)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name or __name__)
