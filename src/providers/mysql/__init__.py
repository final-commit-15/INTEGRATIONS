"""MySQL provider: run SQL queries and manage tables via async SQLAlchemy."""

from __future__ import annotations

from typing import Any

import httpx

from exceptions import IntegrationError
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)


class MySQLProvider(BaseIntegrationProvider):
    provider_key = "mysql"
    name = "MySQL"
    description = "Run SQL queries and manage tables on a MySQL database."
    auth_type = "token"
    base_url = ""
    timeout = 30.0
    supports_webhooks = False

    capabilities = [
        Capability(
            name="execute_query",
            description="Execute a read or write SQL query (blocking destructive DDL unless forced).",
            params_schema={
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "params": {"type": "object"},
                    "limit": {"type": "integer"},
                    "force": {"type": "boolean"},
                },
            },
        ),
        Capability(
            name="list_tables",
            description="List tables in a database.",
            params_schema={},
        ),
        Capability(
            name="get_table_schema",
            description="Describe the columns of a table.",
            params_schema={"required": ["table"], "properties": {"table": {"type": "string"}}},
        ),
        Capability(
            name="insert_row",
            description="Insert a row into a table.",
            params_schema={
                "required": ["table", "row"],
                "properties": {"table": {"type": "string"}, "row": {"type": "object"}},
            },
        ),
        Capability(
            name="update_row",
            description="Update rows matching a where clause.",
            params_schema={
                "required": ["table", "updates", "where"],
                "properties": {
                    "table": {"type": "string"},
                    "updates": {"type": "object"},
                    "where": {"type": "object"},
                },
            },
        ),
        Capability(
            name="delete_row",
            description="Delete rows matching a where clause.",
            params_schema={
                "required": ["table", "where"],
                "properties": {"table": {"type": "string"}, "where": {"type": "object"}},
            },
        ),
        Capability(
            name="count_rows",
            description="Count rows in a table, optionally filtered.",
            params_schema={
                "required": ["table"],
                "properties": {"table": {"type": "string"}, "where": {"type": "object"}},
            },
        ),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._engine_obj: Any = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self.timeout)
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                limits=limits,
                headers=self.base_headers,
            )
        return self._client

    # ------------------------------------------------------------------ helpers

    def _creds(self) -> dict[str, Any]:
        if self.context is None:
            raise IntegrationError("no connection context", provider=self.provider_key)
        return self.context.credentials

    async def _engine(self) -> Any:
        if self._engine_obj is not None:
            return self._engine_obj
        from sqlalchemy.ext.asyncio import create_async_engine

        creds = self._creds()
        host = creds.get("host", "localhost")
        port = int(creds.get("port", 3306))
        database = creds.get("database", "")
        user = creds.get("user", "")
        password = creds.get("password", "")
        url = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
        self._engine_obj = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        return self._engine_obj

    async def _dispose_engine(self) -> None:
        if self._engine_obj is not None:
            await self._engine_obj.dispose()
            self._engine_obj = None

    async def _execute(self, sql: str, params: dict[str, Any] | None = None, fetch: bool = True) -> Any:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = await self._engine()
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(text(sql), params or {})
            if fetch:
                if result.returns_rows:
                    rows = [dict(row._mapping) for row in result.all()]
                    return rows
                return {"rowcount": result.rowcount}
            return result

    @staticmethod
    def _guard(query: Any, force: bool = False) -> str:
        if not isinstance(query, str) or not query.strip():
            raise IntegrationError("query must be a non-empty string", provider="mysql")
        lowered = query.strip().lower()
        if lowered.startswith(("drop", "alter", "truncate", "grant", "revoke", "create")) and not force:
            raise IntegrationError(
                "destructive statement blocked; pass force=True to allow",
                provider="mysql",
            )
        return query

    # ------------------------------------------------------------------ lifecycle

    async def validate_connection(self) -> bool:
        await self._execute("SELECT 1")
        return True

    async def health(self) -> ProviderHealth:
        try:
            await self._execute("SELECT 1")
            return ProviderHealth.healthy(detail={"database": "ok"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def refresh_token(self) -> bool:
        return False

    async def disconnect(self) -> None:
        await self._dispose_engine()

    # ------------------------------------------------------------------ actions

    @action("execute_query")
    async def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        sql = self._guard(query, force=force)
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = await self._engine()
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(text(sql), params or {})
            if result.returns_rows:
                rows = [dict(row._mapping) for row in result.all()]
                if limit is not None:
                    rows = rows[:limit]
                return {"rows": rows, "rowcount": len(rows)}
            return {"rows": [], "rowcount": result.rowcount}

    @action("list_tables")
    async def list_tables(self) -> dict[str, Any]:
        creds = self._creds()
        schema = creds.get("database")
        if schema:
            rows = await self._execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema ORDER BY table_name",
                {"schema": schema},
            )
        else:
            rows = await self._execute("SHOW TABLES")
            rows = [{"table_name": list(r.values())[0]} for r in rows]
        return {"tables": [r.get("table_name") for r in rows if r.get("table_name")]}

    @action("get_table_schema")
    async def get_table_schema(self, table: str) -> dict[str, Any]:
        rows = await self._execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_name = :table ORDER BY ordinal_position",
            {"table": table},
        )
        return {"table": table, "columns": rows}

    @action("insert_row")
    async def insert_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = await self._engine()
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(text(sql), row)
            await session.commit()
            return {"affected": result.rowcount, "lastrowid": getattr(result, "lastrowid", None)}

    @action("update_row")
    async def update_row(
        self,
        table: str,
        updates: dict[str, Any],
        where: dict[str, Any],
    ) -> dict[str, Any]:
        set_clause = ", ".join(f"{k} = :upd_{k}" for k in updates)
        where_clause = " AND ".join(f"{k} = :whr_{k}" for k in where)
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        params: dict[str, Any] = {}
        for k, v in updates.items():
            params[f"upd_{k}"] = v
        for k, v in where.items():
            params[f"whr_{k}"] = v
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = await self._engine()
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(text(sql), params)
            await session.commit()
            return {"affected": result.rowcount}

    @action("delete_row")
    async def delete_row(self, table: str, where: dict[str, Any]) -> dict[str, Any]:
        where_clause = " AND ".join(f"{k} = :whr_{k}" for k in where)
        sql = f"DELETE FROM {table} WHERE {where_clause}"
        params = {f"whr_{k}": v for k, v in where.items()}
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = await self._engine()
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(text(sql), params)
            await session.commit()
            return {"deleted": result.rowcount}

    @action("count_rows")
    async def count_rows(self, table: str, where: dict[str, Any] | None = None) -> dict[str, Any]:
        if where:
            where_clause = " AND ".join(f"{k} = :whr_{k}" for k in where.keys())
            sql = f"SELECT COUNT(*) AS count FROM {table} WHERE {where_clause}"
            params = {f"whr_{k}": v for k, v in where.items()}
        else:
            sql = f"SELECT COUNT(*) AS count FROM {table}"
            params = {}
        rows = await self._execute(sql, params)
        return {"count": int(rows[0]["count"]) if rows else 0}


ProviderCls = MySQLProvider
provider = MySQLProvider()
