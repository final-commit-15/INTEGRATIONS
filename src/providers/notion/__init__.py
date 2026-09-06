"""Notion provider: pages, databases, and blocks via the Notion API."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "notion"
    name = "Notion"
    description = "Read and write pages, databases, and blocks in a Notion workspace."
    auth_type = "oauth2"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = False
    default_scopes = ["read_content", "write_content"]
    oauth_authorize_url = "https://api.notion.com/v1/oauth/authorize"
    oauth_token_url = "https://api.notion.com/v1/oauth/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = False
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="search",
            description="Search pages and databases in the workspace.",
            params_schema={
                "properties": {
                    "query": {"type": "string"},
                    "filter_object": {"type": "object"},
                }
            },
        ),
        Capability(
            name="get_page",
            description="Fetch a single page by id.",
            params_schema={"required": ["page_id"], "properties": {"page_id": {"type": "string"}}},
        ),
        Capability(
            name="get_block_children",
            description="Fetch the child blocks of a block or page.",
            params_schema={"required": ["block_id"], "properties": {"block_id": {"type": "string"}}},
        ),
        Capability(
            name="create_page",
            description="Create a new page inside a parent page or database.",
            params_schema={
                "required": ["parent_id", "properties"],
                "properties": {
                    "parent_id": {"type": "string"},
                    "parent_type": {"type": "string"},
                    "properties": {"type": "object"},
                    "children": {"type": "array"},
                },
            },
        ),
        Capability(
            name="update_page",
            description="Update page properties or archive a page.",
            params_schema={
                "required": ["page_id"],
                "properties": {
                    "page_id": {"type": "string"},
                    "properties": {"type": "object"},
                    "archived": {"type": "boolean"},
                },
            },
        ),
        Capability(
            name="append_block_children",
            description="Append child blocks to an existing block.",
            params_schema={
                "required": ["block_id", "children"],
                "properties": {
                    "block_id": {"type": "string"},
                    "children": {"type": "array"},
                },
            },
        ),
        Capability(
            name="create_database",
            description="Create a new database under a parent page.",
            params_schema={
                "required": ["parent_page_id", "title", "properties"],
                "properties": {
                    "parent_page_id": {"type": "string"},
                    "title": {"type": "string"},
                    "properties": {"type": "object"},
                },
            },
        ),
        Capability(
            name="query_database",
            description="Query entries in an existing database.",
            params_schema={
                "required": ["database_id"],
                "properties": {
                    "database_id": {"type": "string"},
                    "filter": {"type": "object"},
                    "sorts": {"type": "array"},
                    "page_size": {"type": "integer"},
                },
            },
        ),
    ]

    # ------------------------------------------------------------------ auth

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
        }

    async def validate_connection(self) -> bool:
        resp = await self._get("/users/me")
        data = resp.json()
        return "id" in data

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/users/me")
            data = resp.json()
            return ProviderHealth.healthy(detail={"user_id": data.get("id")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    # ------------------------------------------------------------------ actions

    @action("search")
    async def search(self, query: str | None = None, filter_object: dict[str, Any] | None = None) -> dict[str, Any]:
        json_data: dict[str, Any] = {}
        if query is not None:
            json_data["query"] = query
        if filter_object is not None:
            json_data["filter"] = filter_object
        resp = await self._post("/search", json_data=json_data)
        return resp.json()

    @action("get_page")
    async def get_page(self, page_id: str) -> dict[str, Any]:
        resp = await self._get(f"/pages/{page_id}")
        return resp.json()

    @action("get_block_children")
    async def get_block_children(self, block_id: str) -> dict[str, Any]:
        resp = await self._get(f"/blocks/{block_id}/children")
        return resp.json()

    @action("create_page")
    async def create_page(
        self,
        parent_id: str,
        parent_type: str = "page",
        properties: dict[str, Any] | None = None,
        children: list[Any] | None = None,
    ) -> dict[str, Any]:
        if parent_type == "database":
            parent: dict[str, Any] = {"database_id": parent_id}
        else:
            parent = {"page_id": parent_id}
        json_data: dict[str, Any] = {"parent": parent, "properties": properties or {}}
        if children:
            json_data["children"] = children
        resp = await self._post("/pages", json_data=json_data)
        return resp.json()

    @action("update_page")
    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any] | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        json_data: dict[str, Any] = {}
        if properties is not None:
            json_data["properties"] = properties
        if archived is not None:
            json_data["archived"] = archived
        resp = await self._patch(f"/pages/{page_id}", json_data=json_data)
        return resp.json()

    @action("append_block_children")
    async def append_block_children(self, block_id: str, children: list[Any]) -> dict[str, Any]:
        resp = await self._patch(f"/blocks/{block_id}/children", json_data={"children": children})
        return resp.json()

    @action("create_database")
    async def create_database(self, parent_page_id: str, title: str, properties: dict[str, Any]) -> dict[str, Any]:
        json_data: dict[str, Any] = {
            "parent": {"page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        resp = await self._post("/databases", json_data=json_data)
        return resp.json()

    @action("query_database")
    async def query_database(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[Any] | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        json_data: dict[str, Any] = {"page_size": page_size}
        if filter is not None:
            json_data["filter"] = filter
        if sorts is not None:
            json_data["sorts"] = sorts
        resp = await self._post(f"/databases/{database_id}/query", json_data=json_data)
        return resp.json()


ProviderCls = NotionProvider
provider = NotionProvider()
