import base64
from typing import Any

import httpx

from ...core.base import Integration, IntegrationConfig
from ...core.exceptions import AuthenticationError, NotFoundError
from ...utils.logging import get_logger
from ...utils.retry import retry

logger = get_logger(__name__)


class DocumentationIntegration(Integration):
    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.client: httpx.AsyncClient | None = None
        self.repository_url: str | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("Documentation integration is not initialized")
        return self.client

    async def initialize(self) -> None:
        self.repository_url = self.config.credentials.get("repo_url")
        api_token = self.config.credentials.get("api_token")

        if not self.repository_url:
            raise AuthenticationError("Documentation repo URL missing.")

        headers = {}
        if api_token:
            headers["Authorization"] = f"token {api_token}"

        self.client = httpx.AsyncClient(timeout=30.0, headers=headers)
        self._initialized = True
        logger.info("Documentation integration initialized.")

    async def health_check(self) -> bool:
        try:
            resp = await self.http_client.get(f"{self.repository_url}/README.md")
            return resp.status_code < 400
        except Exception:
            return False

    async def execute(self, action: str, **kwargs) -> Any:
        method_map = {
            "read_document": self.read_document,
            "write_document": self.write_document,
            "list_documents": self.list_documents,
            "search_documents": self.search_documents,
            "delete_document": self.delete_document,
        }
        method = method_map.get(action)
        if not method:
            raise ValueError(f"Unknown action for Documentation: {action}")
        return await method(**kwargs)

    @retry(max_attempts=3, backoff=1.0)
    async def read_document(self, path: str) -> dict[str, Any]:
        if self.repository_url is None:
            raise RuntimeError("Documentation integration is not initialized")

        raw_url = f"{self.repository_url.rstrip('/')}/{path.lstrip('/')}"
        resp = await self.http_client.get(raw_url)
        if resp.status_code == 404:
            raise NotFoundError(f"Document {path} not found")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return {
            "path": path,
            "content": resp.text,
            "raw": resp.text,
        }

    @retry(max_attempts=3, backoff=1.0)
    async def write_document(self, path: str, content: str, commit_message: str = "Update docs") -> dict[str, Any]:
        api_url = self._build_api_url(path)
        sha = await self._get_file_sha(path)
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
        }
        if sha:
            payload["sha"] = sha
        # Use PUT for update, POST for create (but GitHub uses PUT for both)
        # We'll use PUT as it's idempotent
        resp = await self.http_client.put(api_url, json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def list_documents(self, path: str = "") -> list[dict[str, Any]]:
        api_url = self._build_api_url(path)
        resp = await self.http_client.get(api_url)
        if resp.status_code == 404:
            return []
        if resp.status_code >= 400:
            resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        else:
            return [data]

    @retry(max_attempts=3, backoff=1.0)
    async def search_documents(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        all_docs = await self.list_documents()
        results = [doc for doc in all_docs if query.lower() in doc.get("name", "").lower()]
        return results[:max_results]

    @retry(max_attempts=3, backoff=1.0)
    async def delete_document(self, path: str, commit_message: str = "Delete doc") -> dict[str, Any]:
        api_url = self._build_api_url(path)
        sha = await self._get_file_sha(path)
        if not sha:
            raise NotFoundError(f"File {path} not found")
        payload = {"message": commit_message, "sha": sha}
        resp = await self.http_client.request("DELETE", api_url, json=payload,)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    async def _get_file_sha(self, path: str) -> str | None:
        api_url = self._build_api_url(path)
        resp = await self.http_client.get(api_url)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            resp.raise_for_status()
        data = resp.json()
        return data.get("sha")

    def _build_api_url(self, path: str) -> str:
        if self.repository_url is None:
            raise RuntimeError("Documentation integration is not initialized")

        if "github.com" in self.repository_url:
            base = self.repository_url.replace(
                "https://github.com/",
                "https://api.github.com/repos/",
            )

            if "/blob/" in base:
                base = base.replace("/blob/", "/contents/")
            elif "/tree/" in base:
                base = base.replace("/tree/", "/contents/")

            return f"{base}/{path.lstrip('/')}"

        return f"{self.repository_url.rstrip('/')}/{path.lstrip('/')}"

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()