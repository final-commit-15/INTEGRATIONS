"""HubSpot provider: CRM objects such as contacts, deals, companies, and notes."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.hubapi.com"


class HubSpotProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "hubspot"
    name = "HubSpot"
    description = "Manage HubSpot CRM contacts, deals, companies, and notes."
    auth_type = "oauth2"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = True
    default_scopes = [
        "crm.objects.contacts.read",
        "crm.objects.deals.read",
        "crm.objects.companies.read",
        "oauth",
    ]
    oauth_authorize_url = "https://app.hubspot.com/oauth/authorize"
    oauth_token_url = "https://api.hubapi.com/oauth/v1/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = False
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="list_contacts",
            description="List CRM contacts.",
            params_schema={
                "properties": {
                    "limit": {"type": "integer"},
                    "after": {"type": "string"},
                },
            },
        ),
        Capability(
            name="create_contact",
            description="Create a new contact.",
            params_schema={
                "required": ["properties"],
                "properties": {"properties": {"type": "object"}},
            },
        ),
        Capability(
            name="get_contact",
            description="Fetch a contact by id.",
            params_schema={"required": ["contact_id"], "properties": {"contact_id": {"type": "string"}}},
        ),
        Capability(
            name="update_contact",
            description="Update a contact.",
            params_schema={
                "required": ["contact_id", "properties"],
                "properties": {
                    "contact_id": {"type": "string"},
                    "properties": {"type": "object"},
                },
            },
        ),
        Capability(
            name="list_deals",
            description="List CRM deals.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="create_deal",
            description="Create a new deal.",
            params_schema={
                "required": ["properties"],
                "properties": {"properties": {"type": "object"}},
            },
        ),
        Capability(
            name="update_deal",
            description="Update a deal.",
            params_schema={
                "required": ["deal_id", "properties"],
                "properties": {
                    "deal_id": {"type": "string"},
                    "properties": {"type": "object"},
                },
            },
        ),
        Capability(
            name="list_companies",
            description="List CRM companies.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="create_company",
            description="Create a new company.",
            params_schema={
                "required": ["properties"],
                "properties": {"properties": {"type": "object"}},
            },
        ),
        Capability(
            name="create_note",
            description="Create a note on an object.",
            params_schema={
                "required": ["properties"],
                "properties": {
                    "properties": {"type": "object"},
                    "associations": {"type": "array"},
                },
            },
        ),
        Capability(
            name="search_objects",
            description="Search a CRM object type by query.",
            params_schema={
                "required": ["object_type", "query"],
                "properties": {
                    "object_type": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {"Authorization": f"Bearer {token}"}

    async def validate_connection(self) -> bool:
        resp = await self._get("/crm/v3/objects/contacts", params={"limit": 1})
        data = resp.json()
        return ("results" in data) or ("total" in data)

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/crm/v3/objects/contacts", params={"limit": 1})
            data = resp.json()
            return ProviderHealth.healthy(detail={"total": data.get("total")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("list_contacts")
    async def list_contacts(self, limit: int = 50, after: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        resp = await self._get("/crm/v3/objects/contacts", params=params)
        return resp.json()

    @action("create_contact")
    async def create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post("/crm/v3/objects/contacts", json_data={"properties": properties})
        return resp.json()

    @action("get_contact")
    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        resp = await self._get(f"/crm/v3/objects/contacts/{contact_id}")
        return resp.json()

    @action("update_contact")
    async def update_contact(self, contact_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        resp = await self._patch(
            f"/crm/v3/objects/contacts/{contact_id}",
            json_data={"properties": properties},
        )
        return resp.json()

    @action("list_deals")
    async def list_deals(self, limit: int = 50) -> dict[str, Any]:
        resp = await self._get("/crm/v3/objects/deals", params={"limit": limit})
        return resp.json()

    @action("create_deal")
    async def create_deal(self, properties: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post("/crm/v3/objects/deals", json_data={"properties": properties})
        return resp.json()

    @action("update_deal")
    async def update_deal(self, deal_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        resp = await self._patch(
            f"/crm/v3/objects/deals/{deal_id}",
            json_data={"properties": properties},
        )
        return resp.json()

    @action("list_companies")
    async def list_companies(self, limit: int = 50) -> dict[str, Any]:
        resp = await self._get("/crm/v3/objects/companies", params={"limit": limit})
        return resp.json()

    @action("create_company")
    async def create_company(self, properties: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post("/crm/v3/objects/companies", json_data={"properties": properties})
        return resp.json()

    @action("create_note")
    async def create_note(
        self,
        properties: dict[str, Any],
        associations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        json_data: dict[str, Any] = {"properties": properties}
        if associations:
            json_data["associations"] = associations
        resp = await self._post("/crm/v3/objects/notes", json_data=json_data)
        return resp.json()

    @action("search_objects")
    async def search_objects(
        self,
        object_type: str,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        resp = await self._post(
            f"/crm/v3/objects/{object_type}/search",
            json_data={"query": query, "limit": limit},
        )
        return resp.json()

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac
        import json

        from config import settings

        timestamp = headers.get("X-HubSpot-Request-Timestamp", "")
        signature = headers.get("X-HubSpot-Signature", "")
        signature3 = headers.get("X-HubSpot-Signature-3", "")
        client_secret = settings.hubspot_client_secret.get_secret_value()
        body = json.dumps(payload)

        if signature3:
            base_string = f"{client_secret}{timestamp}{body}"
            expected = hmac.new(
                base_string.encode(),
                base_string.encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature3)

        if signature:
            expected = hmac.new(
                client_secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)

        return False


ProviderCls = HubSpotProvider
provider = HubSpotProvider()
