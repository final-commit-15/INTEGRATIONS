"""Airtable provider: bases, tables, and records via the Airtable API."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.airtable.com/v0"


class AirtableProvider(BaseIntegrationProvider):
    provider_key = "airtable"
    name = "Airtable"
    description = "Read and write Airtable bases, tables, and records."
    auth_type = "api_key"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = False

    capabilities = [
        Capability(
            name="list_bases",
            description="List all bases accessible to the API token.",
            params_schema={},
        ),
        Capability(
            name="list_tables",
            description="List tables in a base.",
            params_schema={
                "properties": {"base_id": {"type": "string"}},
            },
        ),
        Capability(
            name="list_records",
            description="List records from a table.",
            params_schema={
                "required": ["table"],
                "properties": {
                    "table": {"type": "string"},
                    "base_id": {"type": "string"},
                    "view": {"type": "string"},
                    "page_size": {"type": "integer"},
                    "filter_by_formula": {"type": "string"},
                },
            },
        ),
        Capability(
            name="create_record",
            description="Create a new record in a table.",
            params_schema={
                "required": ["table", "fields"],
                "properties": {
                    "table": {"type": "string"},
                    "fields": {"type": "object"},
                    "base_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="get_record",
            description="Fetch a single record by id.",
            params_schema={
                "required": ["table", "record_id"],
                "properties": {
                    "table": {"type": "string"},
                    "record_id": {"type": "string"},
                    "base_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="update_record",
            description="Update an existing record.",
            params_schema={
                "required": ["table", "record_id", "fields"],
                "properties": {
                    "table": {"type": "string"},
                    "record_id": {"type": "string"},
                    "fields": {"type": "object"},
                    "base_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="delete_record",
            description="Delete a record by id.",
            params_schema={
                "required": ["table", "record_id"],
                "properties": {
                    "table": {"type": "string"},
                    "record_id": {"type": "string"},
                    "base_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="batch_create_records",
            description="Create multiple records in one request (max 10).",
            params_schema={
                "required": ["table", "records"],
                "properties": {
                    "table": {"type": "string"},
                    "records": {"type": "array"},
                    "base_id": {"type": "string"},
                },
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        api_key = self.context.credentials.get("api_key", "") if self.context else ""
        return {"Authorization": f"Bearer {api_key}"}

    def _base_id(self, base_id: str | None = None) -> str:
        if base_id:
            return base_id
        return self.context.credentials.get("base_id", "") if self.context else ""

    def _table_url(self, table: str, base_id: str | None = None) -> str:
        return f"{BASE_URL}/{self._base_id(base_id)}/{table}"

    async def validate_connection(self) -> bool:
        resp = await self._get(f"{BASE_URL}/meta/bases")
        data = resp.json()
        return isinstance(data, dict) and "bases" in data

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get(f"{BASE_URL}/meta/bases")
            data = resp.json()
            bases = data.get("bases", []) if isinstance(data, dict) else []
            return ProviderHealth.healthy(detail={"bases": len(bases)})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def refresh_token(self) -> bool:
        return False

    @action("list_bases")
    async def list_bases(self) -> dict[str, Any]:
        resp = await self._get(f"{BASE_URL}/meta/bases")
        return resp.json()

    @action("list_tables")
    async def list_tables(self, base_id: str | None = None) -> dict[str, Any]:
        resp = await self._get(f"{BASE_URL}/meta/bases/{self._base_id(base_id)}/tables")
        return resp.json()

    @action("list_records")
    async def list_records(
        self,
        table: str,
        base_id: str | None = None,
        view: str | None = None,
        page_size: int = 100,
        filter_by_formula: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"pageSize": page_size}
        if view:
            params["view"] = view
        if filter_by_formula:
            params["filterByFormula"] = filter_by_formula
        resp = await self._get(self._table_url(table, base_id), params=params)
        return resp.json()

    @action("create_record")
    async def create_record(
        self,
        table: str,
        fields: dict[str, Any],
        base_id: str | None = None,
    ) -> dict[str, Any]:
        resp = await self._post(
            self._table_url(table, base_id),
            json_data={"fields": fields, "typecast": True},
        )
        return resp.json()

    @action("get_record")
    async def get_record(
        self,
        table: str,
        record_id: str,
        base_id: str | None = None,
    ) -> dict[str, Any]:
        resp = await self._get(f"{self._table_url(table, base_id)}/{record_id}")
        return resp.json()

    @action("update_record")
    async def update_record(
        self,
        table: str,
        record_id: str,
        fields: dict[str, Any],
        base_id: str | None = None,
    ) -> dict[str, Any]:
        resp = await self._patch(
            f"{self._table_url(table, base_id)}/{record_id}",
            json_data={"fields": fields, "typecast": True},
        )
        return resp.json()

    @action("delete_record")
    async def delete_record(
        self,
        table: str,
        record_id: str,
        base_id: str | None = None,
    ) -> dict[str, Any]:
        await self._delete(f"{self._table_url(table, base_id)}/{record_id}")
        return {"deleted": True, "record_id": record_id}

    @action("batch_create_records")
    async def batch_create_records(
        self,
        table: str,
        records: list[dict[str, Any]],
        base_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "records": [{"fields": rec} for rec in records],
            "typecast": True,
        }
        resp = await self._post(self._table_url(table, base_id), json_data=payload)
        return resp.json()


ProviderCls = AirtableProvider
provider = AirtableProvider()
