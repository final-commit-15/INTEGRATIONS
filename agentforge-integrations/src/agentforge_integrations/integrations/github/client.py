from typing import Any

import httpx

from ...auth.apikey import APIKeyAuth
from ...core.base import Integration, IntegrationConfig
from ...core.exceptions import AuthenticationError, NotFoundError
from ...utils.logging import get_logger
from ...utils.retry import retry, retry_on_rate_limit
from .webhooks import GitHubWebhookHandler

logger = get_logger(__name__)


class GitHubIntegration(Integration):
    """GitHub API wrapper implementing the Integration interface."""

    BASE_URL = "https://api.github.com"

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.client: httpx.AsyncClient | None = None
        self._auth: APIKeyAuth | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("GitHub integration is not initialized")
        return self.client

    async def initialize(self) -> None:
        token = self.config.credentials.get("api_token")
        if not token:
            raise AuthenticationError("GitHub API token missing.")
        self._auth = APIKeyAuth(token, header_name="Authorization", prefix="token")
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            follow_redirects=True,
            auth=self._auth,
        )
        self._initialized = True
        logger.info("GitHub integration initialized.")

    async def health_check(self) -> bool:
        try:
            resp = await self.http_client.get("/user")
            return resp.status_code == 200
        except Exception:
            return False

    async def execute(self, action: str, **kwargs) -> Any:
        method_map = {
            "get_repository": self.get_repository,
            "get_file": self.get_file,
            "create_branch": self.create_branch,
            "create_issue": self.create_issue,
            "create_pull_request": self.create_pull_request,
            "get_pull_request": self.get_pull_request,
            "list_issues": self.list_issues,
            "update_issue": self.update_issue,
        }
        method = method_map.get(action)
        if not method:
            raise ValueError(f"Unknown action for GitHub: {action}")
        return await method(**kwargs)

    @retry(max_attempts=3, backoff=1.0)
    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        resp = await self.http_client.get(f"/repos/{owner}/{repo}")
        if resp.status_code == 404:
            raise NotFoundError(f"Repository {owner}/{repo} not found")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def get_file(self, owner: str, repo: str, path: str, ref: str | None = None) -> dict[str, Any]:
        params = {"ref": ref} if ref else {}
        resp = await self.http_client.get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        if resp.status_code == 404:
            raise NotFoundError(f"File {path} not found")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def create_branch(self, owner: str, repo: str, branch_name: str, source_sha: str) -> dict[str, Any]:
        data = {"ref": f"refs/heads/{branch_name}", "sha": source_sha}
        resp = await self.http_client.post(f"/repos/{owner}/{repo}/git/refs", json=data)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def create_issue(self, owner: str, repo: str, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        data = {"title": title, "body": body, "labels": labels or []}
        resp = await self.http_client.post(f"/repos/{owner}/{repo}/issues", json=data)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def update_issue(self, owner: str, repo: str, issue_number: int, **fields) -> dict[str, Any]:
        resp = await self.http_client.patch(f"/repos/{owner}/{repo}/issues/{issue_number}", json=fields)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def create_pull_request(self, owner: str, repo: str, title: str, body: str, head: str, base: str) -> dict[str, Any]:
        data = {"title": title, "body": body, "head": head, "base": base}
        resp = await self.http_client.post(f"/repos/{owner}/{repo}/pulls", json=data)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        resp = await self.http_client.get(f"/repos/{owner}/{repo}/pulls/{pull_number}")
        if resp.status_code == 404:
            raise NotFoundError(f"PR #{pull_number} not found")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry_on_rate_limit()
    async def list_issues(self, owner: str, repo: str, state: str = "open") -> list[dict[str, Any]]:
        params = {"state": state}
        resp = await self.http_client.get(f"/repos/{owner}/{repo}/issues", params=params)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        handler = GitHubWebhookHandler(self)
        await handler.handle_webhook(event_type, payload)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()