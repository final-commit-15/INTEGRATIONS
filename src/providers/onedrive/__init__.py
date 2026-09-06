"""OneDrive provider: list, upload, download, delete, and search files via Microsoft Graph."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class OneDriveProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "onedrive"
    name = "OneDrive"
    description = "List, upload, download, delete, and search files in OneDrive via Microsoft Graph."
    auth_type = "oauth2"
    base_url = "https://graph.microsoft.com/v1.0"
    timeout = 30.0
    supports_webhooks = False
    default_scopes = ["files.readwrite.all"]
    oauth_authorize_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    oauth_token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="list_drive_root",
            description="List the root children of the drive.",
            params_schema={},
        ),
        Capability(
            name="list_folder",
            description="List the children of a folder path.",
            params_schema={"properties": {"folder_path": {"type": "string"}}},
        ),
        Capability(
            name="upload_file",
            description="Upload a string of content as a file.",
            params_schema={
                "required": ["name", "content"],
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "folder_path": {"type": "string"},
                },
            },
        ),
        Capability(
            name="download_file",
            description="Download the contents of a file by path.",
            params_schema={"required": ["path"], "properties": {"path": {"type": "string"}}},
        ),
        Capability(
            name="delete_file",
            description="Delete a drive item by id.",
            params_schema={"required": ["item_id"], "properties": {"item_id": {"type": "string"}}},
        ),
        Capability(
            name="search_files",
            description="Search files in the drive.",
            params_schema={"required": ["query"], "properties": {"query": {"type": "string"}}},
        ),
        Capability(
            name="get_metadata",
            description="Get metadata for a drive item by id.",
            params_schema={"required": ["item_id"], "properties": {"item_id": {"type": "string"}}},
        ),
        Capability(
            name="create_folder",
            description="Create a folder under a parent path.",
            params_schema={"required": ["name"], "properties": {"name": {"type": "string"}, "parent_path": {"type": "string"}}},
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {"Authorization": f"Bearer {token}"}

    async def validate_connection(self) -> bool:
        resp = await self._get("/me/drive", retry=False)
        return resp.status_code == 200

    async def health(self) -> ProviderHealth:
        try:
            valid = await self.validate_connection()
            if valid:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "GET /me/drive failed"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("list_drive_root")
    async def list_drive_root(self) -> dict[str, Any]:
        resp = await self._get("/me/drive/root/children")
        return resp.json()

    @action("list_folder")
    async def list_folder(self, folder_path: str = "/") -> dict[str, Any]:
        resp = await self._get(f"/me/drive/root:/{folder_path}:/children")
        return resp.json()

    @action("upload_file")
    async def upload_file(self, name: str, content: str, folder_path: str = "") -> dict[str, Any]:
        base = folder_path.rstrip("/")
        path = f"/{name}" if not base else f"/{base}/{name}"
        url = f"/me/drive/root:{path}:/content"
        resp = await self._put(
            url,
            data=content.encode(),
            headers={"Content-Type": "text/plain"},
        )
        return resp.json()

    @action("download_file")
    async def download_file(self, path: str) -> dict[str, Any]:
        resp = await self._get(f"/me/drive/root:/{path}:/content")
        return {"path": path, "content": resp.text}

    @action("delete_file")
    async def delete_file(self, item_id: str) -> dict[str, Any]:
        await self._delete(f"/me/drive/items/{item_id}")
        return {"deleted": True}

    @action("search_files")
    async def search_files(self, query: str) -> dict[str, Any]:
        resp = await self._get(f"/me/drive/root/search(q='{query}')")
        return resp.json()

    @action("get_metadata")
    async def get_metadata(self, item_id: str) -> dict[str, Any]:
        resp = await self._get(f"/me/drive/items/{item_id}")
        return resp.json()

    @action("create_folder")
    async def create_folder(self, name: str, parent_path: str = "") -> dict[str, Any]:
        base = parent_path.rstrip("/")
        path = f":/{base}" if base else ""
        url = f"/me/drive/root{path}:/children"
        resp = await self._post(
            url,
            json_data={
                "name": name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            },
        )
        return resp.json()


ProviderCls = OneDriveProvider
provider = OneDriveProvider()
