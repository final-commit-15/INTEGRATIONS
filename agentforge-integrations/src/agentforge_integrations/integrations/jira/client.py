from typing import Any

import httpx

from ...core.base import Integration, IntegrationConfig
from ...core.exceptions import AuthenticationError, NotFoundError
from ...utils.logging import get_logger
from ...utils.retry import retry
from .webhooks import JiraWebhookHandler

logger = get_logger(__name__)


class JiraIntegration(Integration):
    """Jira Cloud API wrapper."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.client: httpx.AsyncClient | None = None
        self.base_url: str | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("Jira integration is not initialized")
        return self.client

    async def initialize(self) -> None:
        self.base_url = self.config.credentials.get("base_url")
        api_token = self.config.credentials.get("api_token")
        email = self.config.credentials.get("email")

        if not self.base_url:
            raise AuthenticationError("Jira base URL missing")
        if not api_token or not email:
            raise AuthenticationError("Jira API token or email missing")

        auth = httpx.BasicAuth(username=email, password=api_token)
        self.client = httpx.AsyncClient(
            base_url=self.base_url.rstrip("/"),
            auth=auth,
            timeout=30.0,
        )
        self._initialized = True
        logger.info("Jira integration initialized.")

    async def health_check(self) -> bool:
        try:
            resp = await self.http_client.get("/rest/api/3/myself")
            return resp.status_code == 200
        except Exception:
            return False

    async def execute(self, action: str, **kwargs) -> Any:
        method_map = {
            "get_issue": self.get_issue,
            "create_issue": self.create_issue,
            "update_issue": self.update_issue,
            "add_comment": self.add_comment,
            "transition_issue": self.transition_issue,
            "search_issues": self.search_issues,
            "get_project": self.get_project,
        }
        method = method_map.get(action)
        if not method:
            raise ValueError(f"Unknown action for Jira: {action}")
        return await method(**kwargs)

    @retry(max_attempts=3, backoff=1.0)
    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        resp = await self.http_client.get(f"/rest/api/3/issue/{issue_key}")
        if resp.status_code == 404:
            raise NotFoundError(f"Issue {issue_key} not found")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def create_issue(self, project_key: str, summary: str, description: str, issue_type: str = "Task", **fields) -> dict[str, Any]:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                **fields,
            }
        }
        resp = await self.http_client.post("/rest/api/3/issue", json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def update_issue(self, issue_key: str, **fields) -> dict[str, Any]:
        payload = {"fields": fields}
        resp = await self.http_client.put(f"/rest/api/3/issue/{issue_key}", json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def add_comment(self, issue_key: str, comment: str) -> dict[str, Any]:
        payload = {"body": comment}
        resp = await self.http_client.post(f"/rest/api/3/issue/{issue_key}/comment", json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def transition_issue(self, issue_key: str, transition_id: str) -> None:
        payload = {"transition": {"id": transition_id}}
        resp = await self.http_client.post(f"/rest/api/3/issue/{issue_key}/transitions", json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()

    @retry(max_attempts=3, backoff=1.0)
    async def search_issues(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "jql": jql,
            "maxResults": max_results,
        }
        resp = await self.http_client.get(
            "/rest/api/3/search",
            params=params,
        )
        if resp.status_code >= 400:
            resp.raise_for_status()
        data = resp.json()
        return data.get("issues", [])

    @retry(max_attempts=3, backoff=1.0)
    async def get_project(self, project_key: str) -> dict[str, Any]:
        resp = await self.http_client.get(f"/rest/api/3/project/{project_key}")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        handler = JiraWebhookHandler(self)
        await handler.handle_webhook(event_type, payload)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()