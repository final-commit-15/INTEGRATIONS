"""Google Drive provider: manage files and folders via the Google Drive API."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class GoogleDriveProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "google_drive"
    name = "Google Drive"
    description = "List, upload, download, and manage files and folders in Google Drive."
    auth_type = "oauth2"
    base_url = "https://www.googleapis.com/drive/v3"
    timeout = 30.0
    supports_webhooks = False
    default_scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ]
    oauth_authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_url = "https://oauth2.googleapis.com/token"
    oauth_revoke_url = "https://oauth2.googleapis.com/revoke"
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="list_files",
            description="List files in Google Drive with optional query filter.",
            params_schema={
                "properties": {
                    "page_size": {"type": "integer", "default": 20},
                    "q": {"type": "string"},
                    "page_token": {"type": "string"},
                },
            },
            examples=["google_drive.list_files page_size=10"],
        ),
        Capability(
            name="get_file",
            description="Get metadata for a single file.",
            params_schema={"required": ["file_id"], "properties": {"file_id": {"type": "string"}}},
        ),
        Capability(
            name="upload_file",
            description="Upload a file to Google Drive.",
            params_schema={
                "required": ["name", "content"],
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "mime_type": {"type": "string", "default": "application/octet-stream"},
                    "parent_id": {"type": "string"},
                },
            },
        ),
        Capability(
            name="download_file",
            description="Download file content by id.",
            params_schema={"required": ["file_id"], "properties": {"file_id": {"type": "string"}}},
        ),
        Capability(
            name="delete_file",
            description="Delete a file by id.",
            params_schema={"required": ["file_id"], "properties": {"file_id": {"type": "string"}}},
        ),
        Capability(
            name="list_folders",
            description="List all folders in Google Drive.",
            params_schema={"properties": {"page_size": {"type": "integer", "default": 50}}},
        ),
        Capability(
            name="create_folder",
            description="Create a new folder in Google Drive.",
            params_schema={
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "parent_id": {"type": "string"},
                },
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {"Authorization": f"Bearer {token}"}

    async def validate_connection(self) -> bool:
        resp = await self._get("/about")
        return bool(resp.json())

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/about")
            return ProviderHealth.healthy()
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("list_files")
    async def list_files(
        self,
        page_size: int = 20,
        q: str | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"pageSize": page_size}
        if q:
            params["q"] = q
        if page_token:
            params["pageToken"] = page_token
        resp = await self._get("/files", params=params)
        return resp.json()

    @action("get_file")
    async def get_file(self, file_id: str) -> dict[str, Any]:
        resp = await self._get(
            f"/files/{file_id}",
            params={"fields": "id,name,mimeType,size,modifiedTime"},
        )
        return resp.json()

    @action("upload_file")
    async def upload_file(
        self,
        name: str,
        content: str,
        mime_type: str = "application/octet-stream",
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if parent_id:
            metadata["parents"] = [parent_id]
        resp = await self._post(
            "/files",
            params={"uploadType": "multipart"},
            data=metadata,
            files={"file": (name, content.encode())},
        )
        return resp.json()

    @action("download_file")
    async def download_file(self, file_id: str) -> dict[str, Any]:
        resp = await self._get(f"/files/{file_id}", params={"alt": "media"}, retry=True)
        return {"file_id": file_id, "content": resp.text}

    @action("delete_file")
    async def delete_file(self, file_id: str) -> dict[str, Any]:
        await self._delete(f"/files/{file_id}")
        return {"deleted": True, "file_id": file_id}

    @action("list_folders")
    async def list_folders(self, page_size: int = 50) -> dict[str, Any]:
        resp = await self._get(
            "/files",
            params={"pageSize": page_size, "q": "mimeType='application/vnd.google-apps.folder'"},
        )
        return resp.json()

    @action("create_folder")
    async def create_folder(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        resp = await self._post("/files", json_data=metadata)
        return resp.json()


ProviderCls = GoogleDriveProvider
provider = GoogleDriveProvider()
