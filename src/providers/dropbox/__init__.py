"""Dropbox provider: upload, download, list, search, and share files via the Dropbox API."""

from __future__ import annotations

import json
from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class DropboxProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "dropbox"
    name = "Dropbox"
    description = "Upload, download, list, search, and share files with the Dropbox API."
    auth_type = "oauth2"
    base_url = "https://api.dropboxapi.com/2"
    timeout = 30.0
    supports_webhooks = False
    default_scopes = [
        "files.content.write",
        "files.content.read",
        "sharing.write",
        "sharing.read",
    ]
    oauth_authorize_url = "https://www.dropbox.com/oauth2/authorize"
    oauth_token_url = "https://api.dropboxapi.com/oauth2/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="upload_file",
            description="Upload a string of content to a Dropbox path.",
            params_schema={
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "default": "add"},
                    "autorename": {"type": "boolean", "default": True},
                },
            },
        ),
        Capability(
            name="download_file",
            description="Download the contents of a Dropbox file.",
            params_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        Capability(
            name="list_folder",
            description="List the contents of a Dropbox folder.",
            params_schema={"properties": {"path": {"type": "string"}, "recursive": {"type": "boolean"}}},
        ),
        Capability(
            name="get_metadata",
            description="Get metadata for a path.",
            params_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        Capability(
            name="create_folder",
            description="Create a folder at a path.",
            params_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        Capability(
            name="create_shared_link",
            description="Create a shared link for a path.",
            params_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        Capability(
            name="delete",
            description="Delete a file or folder at a path.",
            params_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        Capability(
            name="search",
            description="Search files within a path.",
            params_schema={"required": ["query"], "properties": {"query": {"type": "string"}, "path": {"type": "string"}}},
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        token = ""
        if self.context:
            token = self.context.credentials.get("access_token", "")
        elif _settings_access_token():
            token = _settings_access_token()
        return {"Authorization": f"Bearer {token}"}

    async def validate_connection(self) -> bool:
        resp = await self._post("/users/get_current_account", json_data={}, retry=False)
        return resp.status_code == 200

    async def health(self) -> ProviderHealth:
        try:
            valid = await self.validate_connection()
            if valid:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "get_current_account failed"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("upload_file")
    async def upload_file(
        self,
        path: str,
        content: str,
        mode: str = "add",
        autorename: bool = True,
    ) -> dict[str, Any]:
        args = {"path": path, "mode": mode, "autorename": autorename}
        resp = await self._request(
            "POST",
            "/files/upload",
            data=content.encode(),
            headers={"Dropbox-API-Arg": json.dumps(args)},
        )
        return resp.json()

    @action("download_file")
    async def download_file(self, path: str) -> dict[str, Any]:
        resp = await self._request(
            "POST",
            "/files/download",
            data=b"",
            headers={"Dropbox-API-Arg": json.dumps({"path": path})},
        )
        return {"path": path, "content": resp.text}

    @action("list_folder")
    async def list_folder(self, path: str = "", recursive: bool = False) -> dict[str, Any]:
        resp = await self._post("/files/list_folder", json_data={"path": path, "recursive": recursive})
        return resp.json()

    @action("get_metadata")
    async def get_metadata(self, path: str) -> dict[str, Any]:
        resp = await self._post("/files/get_metadata", json_data={"path": path})
        return resp.json()

    @action("create_folder")
    async def create_folder(self, path: str) -> dict[str, Any]:
        resp = await self._post("/files/create_folder_v2", json_data={"path": path})
        return resp.json()

    @action("create_shared_link")
    async def create_shared_link(self, path: str) -> dict[str, Any]:
        resp = await self._post("/sharing/create_shared_link_with_settings", json_data={"path": path})
        return resp.json()

    @action("delete")
    async def delete(self, path: str) -> dict[str, Any]:
        resp = await self._post("/files/delete_v2", json_data={"path": path})
        return resp.json()

    @action("search")
    async def search(self, query: str, path: str = "") -> dict[str, Any]:
        resp = await self._post("/files/search_v2", json_data={"query": query, "path": path})
        return resp.json()


def _settings_access_token() -> str:
    from config import settings

    return settings.dropbox_refresh_token.get_secret_value() if settings.dropbox_refresh_token else ""


ProviderCls = DropboxProvider
provider = DropboxProvider()
