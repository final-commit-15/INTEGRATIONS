"""FastAPI application entrypoint for the AgentForge Integrations service."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from api import api_router
from config import settings
from database.database import close_db, init_db
from exceptions import IntegrationError
from logging_config import configure_logging, get_logger
from middleware import build_middlewares
from providers.registry import get_registry
from schemas import ErrorResponse
from services.redis_service import close_redis
from telemetry import configure_telemetry, shutdown_telemetry

log = get_logger("main")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    enabled=settings.rate_limit_enabled,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: configure telemetry, discover providers, warm deps."""
    configure_telemetry()
    configure_logging()

    # Auto-discovery of the provider registry (no hardcoded imports).
    registry = get_registry()
    registry.load()
    app.state.provider_count = len(registry.keys())
    log.info("providers_discovered", count=app.state.provider_count)

    if settings.environment != "production":
        try:
            await init_db()
        except Exception:
            log.warning("database_autocreate_failed", exc_info=True)

    yield

    await close_db()
    await close_redis()
    shutdown_telemetry()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AgentForge Integrations - external service connectors, OAuth, and webhooks.",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
build_middlewares(app)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.middleware("http")
async def add_metrics_headers(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Processed-In-Ms"] = str(round((time.perf_counter() - start) * 1000, 2))
    return response


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "health": f"{settings.api_v1_prefix}/health",
        "docs": "/docs",
    }


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    log.warning("rate_limit_exceeded", path=request.url.path)
    return JSONResponse(
        status_code=429,
        content=ErrorResponse(
            error={
                "code": "rate_limit_exceeded",
                "message": "rate limit exceeded",
                "details": {},
            }
        ).model_dump(),
    )


@app.exception_handler(IntegrationError)
async def integration_error_handler(request: Request, exc: IntegrationError) -> JSONResponse:
    log.warning("integration_error", code=exc.code, provider=exc.provider, message=exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.to_dict()).model_dump(),
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Best-effort dependency shutdown for embedded runtimes (uvicorn: handled by lifespan)."""
    pass
