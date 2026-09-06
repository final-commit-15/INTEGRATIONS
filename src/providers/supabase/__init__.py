"""Supabase provider: query, insert, update, delete rows and call RPCs via PostgREST."""

from __future__ import annotations

from typing import Any

from exceptions import IntegrationError
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)


class SupabaseProvider(BaseIntegrationProvider):
    provider_key = "supabase"
    name = "Supabase"
    description = "Query, insert, update, delete rows and call RPCs via the Supabase PostgREST API."
    auth_type = "api_key"
    base_url = "https://supabase.co"
    timeout = 30.0
    supports_webhooks = False

    capabilities = [
        Capability(
            name="query_table",
            description="Select rows from a table with filters.",
            params_schema={
                "required": ["table"],
                "properties": {
                    "table": {"type": "string"},
                    "select": {"type": "string"},
                    "filters": {"type": "object"},
                    "limit": {"type": "integer", "default": 100},
                    "order": {"type": "string"},
                },
            },
        ),
        Capability(
            name="insert_row",
            description="Insert a row into a table.",
            params_schema={"required": ["table", "row"], "properties": {"table": {"type": "string"}, "row": {"type": "object"}}},
        ),
        Capability(
            name="update_row",
            description="Update rows matching a filter.",
            params_schema={
                "required": ["table", "updates", "match"],
                "properties": {"table": {"type": "string"}, "updates": {"type": "object"}, "match": {"type": "object"}},
            },
        ),
        Capability(
            name="delete_row",
            description="Delete rows matching a filter.",
            params_schema={"required": ["table", "match"], "properties": {"table": {"type": "string"}, "match": {"type": "object"}}},
        ),
        Capability(
            name="rpc",
            description="Call a Postgres RPC function.",
            params_schema={"required": ["fn_name"], "properties": {"fn_name": {"type": "string"}, "args": {"type": "object"}}},
        ),
        Capability(
            name="list_tables",
            description="List tables exposed by PostgREST.",
            params_schema={},
        ),
        Capability(
            name="get_row",
            description="Get a single row by primary key.",
            params_schema={
                "required": ["table", "primary_key", "value"],
                "properties": {"table": {"type": "string"}, "primary_key": {"type": "string"}, "value": {"type": "string"}},
            },
        ),
    ]

    async def refresh_token(self) -> bool:
        return False

    @property
    def auth_headers(self) -> dict[str, str]:
        key = self._api_key()
        return {"Authorization": f"Bearer {key}", "apikey": key}

    def _api_key(self) -> str:
        if self.context:
            key = self.context.credentials.get("service_role_key") or self.context.credentials.get("anon_key")
            if key:
                return key
        from config import settings

        if settings.supabase_service_role_key and settings.supabase_service_role_key.get_secret_value():
            return settings.supabase_service_role_key.get_secret_value()
        return ""

    def _url(self) -> str:
        if self.context and self.context.credentials.get("url"):
            url = self.context.credentials["url"]
        else:
            from config import settings

            url = settings.supabase_url
        return url.rstrip("/")

    def _rest(self, path: str) -> str:
        return f"{self._url()}/rest/v1{path}"

    async def validate_connection(self) -> bool:
        try:
            await self._get(self._rest("/"), retry=False)
        except IntegrationError:
            return True
        except Exception:
            return False
        return True

    async def health(self) -> ProviderHealth:
        try:
            await self.validate_connection()
            return ProviderHealth.healthy()
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    def _params_for_filters(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if not filters:
            return params
        for column, value in filters.items():
            if isinstance(value, dict):
                op = value.get("op", "eq")
                val = value.get("value")
                params[f"{column}={op}.{val}"] = ""
            else:
                params[f"{column}=eq.{value}"] = ""
        return params

    @action("query_table")
    async def query_table(
        self,
        table: str,
        select: str = "*",
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        order: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"select": select}
        params.update(self._params_for_filters(filters))
        if limit is not None:
            params["limit"] = limit
        if order:
            params["order"] = order
        resp = await self._get(self._rest(f"/{table}"), params=params)
        return resp.json()

    @action("insert_row")
    async def insert_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post(
            self._rest(f"/{table}"),
            json_data=row,
            headers={"Prefer": "return=representation"},
        )
        return resp.json()

    @action("update_row")
    async def update_row(self, table: str, updates: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
        params = self._params_for_filters(match)
        resp = await self._patch(self._rest(f"/{table}"), json_data=updates, params=params)
        return resp.json()

    @action("delete_row")
    async def delete_row(self, table: str, match: dict[str, Any]) -> dict[str, Any]:
        params = self._params_for_filters(match)
        resp = await self._delete(self._rest(f"/{table}"), params=params)
        return resp.json()

    @action("rpc")
    async def rpc(self, fn_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._post(self._rest(f"/rpc/{fn_name}"), json_data=args or {})
        return resp.json()

    @action("list_tables")
    async def list_tables(self) -> dict[str, Any]:
        try:
            resp = await self._get(self._rest("/"))
            return resp.json()
        except IntegrationError:
            return {"tables": [], "relation": "postgrest_disabled"}

    @action("get_row")
    async def get_row(self, table: str, primary_key: str, value: str, select: str = "*") -> dict[str, Any]:
        params: dict[str, Any] = {"select": select, f"{primary_key}=eq.{value}": ""}
        resp = await self._get(self._rest(f"/{table}"), params=params)
        return resp.json()


ProviderCls = SupabaseProvider
provider = SupabaseProvider()
