"""ASGI middleware for correlation IDs, request context, telemetry, and errors."""

from __future__ import annotations

import time
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import settings
from exceptions import IntegrationError
from schemas import ErrorResponse
from telemetry import metrics
from utils.context import (
    new_correlation_id,
    new_request_id,
    workspace_id_var,
)


class ContextMiddleware(BaseHTTPMiddleware):
    """Assign request + correlation IDs and bind them to the log context."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        request_id = new_request_id()
        correlation_id = request.headers.get("x-correlation-id") or new_correlation_id()

        log = structlog.get_logger("middleware.context")
        with structlog.contextvars.bound_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        ):
            request.state.request_id = request_id
            request.state.correlation_id = correlation_id
            response = await call_next(request)
            latency_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-Id"] = request_id
            response.headers["X-Correlation-Id"] = correlation_id
            status = response.status_code
            metrics.record_api_latency(latency_ms, request.url.path, request.method, status)
            if status >= 500:
                log.error("request_failed", status_code=status, latency_ms=round(latency_ms, 2))
            return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Convert exceptions to consistent JSON error responses."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        try:
            return await call_next(request)
        except IntegrationError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(
                    error={
                        "code": exc.code,
                        "message": exc.message,
                        "provider": exc.provider,
                        "details": exc.details,
                    }
                ).model_dump(),
            )
        except Exception as exc:
            structlog.get_logger("middleware.error").exception(
                "unhandled_exception", error=str(exc)
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "internal server error",
                        "details": {} if not settings.debug else {"detail": str(exc)},
                    }
                },
            )


class WorkspaceContextMiddleware(BaseHTTPMiddleware):
    """Expose resolved workspace_id to the context var for task propagation."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        principal = getattr(request.state, "principal", None)
        if principal and getattr(principal, "workspace_id", None):
            workspace_id_var.set(principal.workspace_id)
        return await call_next(request)


_middleware_order = [ContextMiddleware, ErrorHandlingMiddleware, WorkspaceContextMiddleware]


def build_middlewares(app: Any) -> Any:
    """Attach middlewares in a deterministic order."""
    app.add_middleware(WorkspaceContextMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(ContextMiddleware)
    return app
