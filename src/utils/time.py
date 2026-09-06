"""Time and formatting helpers."""

from __future__ import annotations

import time
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(UTC)


def utc_isoformat(dt: datetime) -> str:
    """ISO-8601 string with Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def unix_timestamp_ms() -> int:
    return int(time.time() * 1000)


def parse_query_params(params: dict[str, object]) -> dict[str, object]:
    """Drop None values from a query parameter dict before signing/serializing."""
    return {k: v for k, v in params.items() if v is not None}
