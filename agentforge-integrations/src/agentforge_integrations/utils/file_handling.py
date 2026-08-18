import base64
from typing import Any

import aiofiles
import httpx


class FileHandler:
    """Utility for uploading/downloading files via integrations."""

    @staticmethod
    async def download(url: str, client: httpx.AsyncClient, dest_path: str | None = None) -> bytes:
        """Download a file from a URL."""
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        content = resp.content
        if dest_path:
            async with aiofiles.open(dest_path, "wb") as f:
                await f.write(content)
        return content

    @staticmethod
    async def upload(
        client: httpx.AsyncClient,
        url: str,
        file_content: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        extra_data: dict | None = None,
    ) -> Any:
        """Upload a file via multipart form."""
        files = {"file": (filename, file_content, content_type)}
        data = extra_data or {}
        resp = await client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def decode_base64(content: str) -> bytes:
        """Decode base64 content (common in GitHub API)."""
        return base64.b64decode(content)

    @staticmethod
    def encode_base64(content: bytes) -> str:
        return base64.b64encode(content).decode()