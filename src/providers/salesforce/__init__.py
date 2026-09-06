"""Salesforce provider: CRM sobjects, queries, and search via the Salesforce REST API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from config import settings
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)

LOGIN_URL = "https://login.salesforce.com"


class SalesforceProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "salesforce"
    name = "Salesforce"
    description = "Query and manage Salesforce objects, accounts, contacts, and opportunities."
    auth_type = "oauth2"
    base_url = LOGIN_URL
    timeout = 30.0
    supports_webhooks = False
    default_scopes = ["api", "refresh_token"]
    oauth_authorize_url = "https://login.salesforce.com/services/oauth2/authorize"
    oauth_token_url = "https://login.salesforce.com/services/oauth2/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="whoami",
            description="Get the current Salesforce user and instance info.",
            params_schema={},
        ),
        Capability(
            name="list_objects",
            description="List available Salesforce standard and custom objects.",
            params_schema={},
        ),
        Capability(
            name="describe_object",
            description="Describe a Salesforce object.",
            params_schema={"required": ["sobject"], "properties": {"sobject": {"type": "string"}}},
        ),
        Capability(
            name="create_record",
            description="Create a Salesforce record.",
            params_schema={
                "required": ["sobject", "fields"],
                "properties": {
                    "sobject": {"type": "string"},
                    "fields": {"type": "object"},
                },
            },
        ),
        Capability(
            name="get_record",
            description="Fetch a Salesforce record by id.",
            params_schema={
                "required": ["sobject", "record_id"],
                "properties": {
                    "sobject": {"type": "string"},
                    "record_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="update_record",
            description="Update a Salesforce record.",
            params_schema={
                "required": ["sobject", "record_id", "fields"],
                "properties": {
                    "sobject": {"type": "string"},
                    "record_id": {"type": "string"},
                    "fields": {"type": "object"},
                },
            },
        ),
        Capability(
            name="delete_record",
            description="Delete a Salesforce record.",
            params_schema={
                "required": ["sobject", "record_id"],
                "properties": {
                    "sobject": {"type": "string"},
                    "record_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="query",
            description="Run a SOQL query.",
            params_schema={"required": ["soql"], "properties": {"soql": {"type": "string"}}},
        ),
        Capability(
            name="search",
            description="Run a Salesforce SOSL search.",
            params_schema={"required": ["q"], "properties": {"q": {"type": "string"}}},
        ),
        Capability(
            name="list_accounts",
            description="List Account records.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="list_contacts",
            description="List Contact records.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="list_opportunities",
            description="List Opportunity records.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _instance_url(self) -> str:
        if self.context:
            instance = self.context.credentials.get("instance_url")
            if instance:
                return instance.rstrip("/")
        return settings.salesforce_instance_url.rstrip("/") if settings.salesforce_instance_url else LOGIN_URL

    def _api_url(self, path: str) -> str:
        version = settings.salesforce_api_version
        return f"{self._instance_url()}/services/data/{version}{path}"

    async def validate_connection(self) -> bool:
        resp = await self._get(self._api_url("/sobjects"))
        data = resp.json()
        return "sobjects" in data

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get(self._api_url("/sobjects"))
            data = resp.json()
            return ProviderHealth.healthy(detail={"object_count": len(data.get("sobjects", []))})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("whoami")
    async def whoami(self) -> dict[str, Any]:
        resp = await self._get(self._api_url("/sobjects"))
        data = resp.json()
        return {"sobjects": data.get("sobjects", [])}

    @action("list_objects")
    async def list_objects(self) -> dict[str, Any]:
        resp = await self._get(self._api_url("/sobjects"))
        return resp.json()

    @action("describe_object")
    async def describe_object(self, sobject: str) -> dict[str, Any]:
        resp = await self._get(self._api_url(f"/sobjects/{sobject}/describe"))
        return resp.json()

    @action("create_record")
    async def create_record(self, sobject: str, fields: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post(self._api_url(f"/sobjects/{sobject}"), json_data=fields, allowed_status=(201,))
        data = resp.json()
        return {"id": data.get("id")}

    @action("get_record")
    async def get_record(self, sobject: str, record_id: str) -> dict[str, Any]:
        resp = await self._get(self._api_url(f"/sobjects/{sobject}/{record_id}"))
        return resp.json()

    @action("update_record")
    async def update_record(self, sobject: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        resp = await self._patch(self._api_url(f"/sobjects/{sobject}/{record_id}"), json_data=fields)
        return resp.json()

    @action("delete_record")
    async def delete_record(self, sobject: str, record_id: str) -> dict[str, Any]:
        await self._delete(self._api_url(f"/sobjects/{sobject}/{record_id}"))
        return {"deleted": True}

    @action("query")
    async def query(self, soql: str) -> dict[str, Any]:
        resp = await self._get(f"{self._api_url('/query')}?q={quote(soql)}")
        return resp.json()

    @action("search")
    async def search(self, q: str) -> dict[str, Any]:
        resp = await self._get(f"{self._api_url('/search')}?q={quote(q)}")
        return resp.json()

    @action("list_accounts")
    async def list_accounts(self, limit: int = 100) -> dict[str, Any]:
        soql = f"SELECT Id, Name FROM Account LIMIT {int(limit)}"
        return await self.query(soql)

    @action("list_contacts")
    async def list_contacts(self, limit: int = 100) -> dict[str, Any]:
        soql = f"SELECT Id, FirstName, LastName, Email FROM Contact LIMIT {int(limit)}"
        return await self.query(soql)

    @action("list_opportunities")
    async def list_opportunities(self, limit: int = 100) -> dict[str, Any]:
        soql = f"SELECT Id, Name, StageName, Amount FROM Opportunity LIMIT {int(limit)}"
        return await self.query(soql)


ProviderCls = SalesforceProvider
provider = SalesforceProvider()
