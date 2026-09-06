"""Shared pytest fixtures and environment wiring.

CRITICAL: environment variables must be set BEFORE importing any application
module because ``config.settings`` is an ``lru_cache``d singleton evaluated at
import time. Everything in this file runs at collection time, before test
modules are imported.
"""

from __future__ import annotations

import os
import tempfile

_TEST_DB = os.path.join(tempfile.gettempdir(), "agentforge_integrations_test.db").replace("\\", "/")

os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB}")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("WEBHOOK_DEFAULT_SECRET", "test-webhook-default-secret")

# Remove any stale DB files left over from a previous run.
for _stale in (_TEST_DB, _TEST_DB + "-journal", _TEST_DB + "-wal", _TEST_DB + "-shm"):
    if os.path.exists(_stale):
        try:
            os.remove(_stale)
        except OSError:
            pass

import pytest
import pytest_asyncio

# Force early import of these modules so the module-level singletons exist and
# the oauth service pick up the sqlite settings (they are lazy, but this makes
# the wiring explicit and catches import-time breakage at collection time).
import services.encryption_service  # noqa: E402
import services.oauth_service  # noqa: E402,F401
from database.database import Base, engine
from models import Workspace
from providers.registry import registry
from security import create_access_token

TEST_DB_URL = os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Session-level setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _registry_loaded():
    """Mirror the app lifespan: auto-discover providers once per session."""
    registry.load()
    yield
    registry._providers.clear()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _reset_database():
    """Drop + recreate all tables before each test, then drop them after.

    ``engine.dispose()`` clears pooled connections between tests so that a
    connection checked out in one asyncio event loop is never reused in
    another (pytest-asyncio uses a function-scoped loop).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker():
    from database.database import async_session_factory

    return async_session_factory


@pytest_asyncio.fixture
async def db_session(session_maker):
    """Yield an async session for a single test."""
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def workspace(db_session) -> Workspace:
    """Create a workspace row that foreign keys can reference."""
    ws = Workspace(id="ws-1", name="Test Workspace", owner_id="user-1")
    db_session.add(ws)
    await db_session.commit()
    await db_session.refresh(ws)
    return ws


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers():
    """Factory returning an Authorization header dict scoped to ws-1."""
    def _token(**claims):
        payload = {"sub": "user-1", "ws": "ws-1", "roles": ["user"]}
        payload.update(claims)
        return {"Authorization": f"Bearer {create_access_token(**payload)}"}

    return _token


@pytest.fixture
def admin_auth_headers(auth_headers):
    def _token(**claims):
        payload = {"roles": ["admin"]}
        payload.update(claims)
        return auth_headers(**payload)

    return _token


# ---------------------------------------------------------------------------
# API client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def api_client():
    """FastAPI TestClient inside its lifespan (registers providers + tables).

    Session-scoped so ``close_db()``/``close_redis()`` only run once at the
    very end; per-test DB isolation is handled by ``_reset_database``.
    """
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        yield client
