"""Alembic environment for agentforge-integrations.

Async-capable: uses an async engine created from `config.settings`,
runs migrations with asyncio, and supports --autogenerate comparison via
connection.run_sync(compare_metadata).
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure `src` is importable (bare top-level modules live there).
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import models  # noqa: E402,F401  (side-effect import: registers tables on Base.metadata)
from config import settings  # noqa: E402
from database.database import Base  # noqa: E402

# Alembic Config object.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the URL from application settings; allow CLI -x DATABASE_URL=... to override.
override_url = context.get_x_argument(as_dictionary=True).get("DATABASE_URL")
config.set_main_option("sqlalchemy.url", override_url or settings.database_url)

target_metadata = Base.metadata


def _run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Create an async engine and run migrations in 'online' mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode within an event loop."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    _run_migrations_offline()
else:
    run_migrations_online()
