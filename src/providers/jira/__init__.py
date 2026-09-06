"""Jira provider: issues, projects, sprints, and users via the Atlassian REST API."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class JiraProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "jira"
    name = "Jira"
    description = "Manage issues, projects, sprints, and users on a Jira Cloud site."
    auth_type = "oauth2"
    base_url = ""
    timeout = 30.0
    supports_webhooks = True
    default_scopes = ["read:jira-user", "offline_access"]
    oauth_authorize_url = "https://auth.atlassian.com/authorize"
    oauth_token_url = "https://auth.atlassian.com/oauth/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="create_issue",
            description="Create a new issue on a Jira project.",
            params_schema={
                "required": ["project_key", "summary"],
                "properties": {
                    "project_key": {"type": "string"},
                    "summary": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string"},
                    "assignee": {"type": "string"},
                },
            },
        ),
        Capability(
            name="get_issue",
            description="Fetch a single issue by key.",
            params_schema={
                "required": ["issue_key"],
                "properties": {
                    "issue_key": {"type": "string"},
                    "fields": {"type": "string"},
                },
            },
        ),
        Capability(
            name="update_issue",
            description="Update arbitrary fields of an issue.",
            params_schema={
                "required": ["issue_key"],
                "properties": {"issue_key": {"type": "string"}},
            },
        ),
        Capability(
            name="search_issues",
            description="Search issues with a JQL query.",
            params_schema={
                "required": ["jql"],
                "properties": {
                    "jql": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="get_sprint",
            description="List sprints on a board, filtered by state.",
            params_schema={
                "required": ["board_id"],
                "properties": {
                    "board_id": {"type": "integer"},
                    "state": {"type": "string"},
                },
            },
        ),
        Capability(
            name="list_projects",
            description="List all projects visible to the user.",
            params_schema={},
        ),
        Capability(
            name="add_comment",
            description="Add a comment to an issue.",
            params_schema={
                "required": ["issue_key", "body"],
                "properties": {
                    "issue_key": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        ),
        Capability(
            name="get_user",
            description="Fetch a user by Atlassian account id.",
            params_schema={
                "required": ["account_id"],
                "properties": {"account_id": {"type": "string"}},
            },
        ),
    ]

    # ------------------------------------------------------------------ auth

    def __init__(self, context: Any = None, *, client: Any = None) -> None:
        self.context = context
        site = self._site_url()
        if site:
            self.base_url = f"https://{site}"
        elif not self.base_url:
            self.base_url = "https://auth.atlassian.com"
        super().__init__(context=context, client=client)

    def _site_url(self) -> str:
        creds = self.context.credentials if self.context else {}
        return creds.get("site_url") or creds.get("instance_url") or ""

    def _jira_url(self, path: str) -> str:
        return f"https://{self._site_url()}/rest/api/3/{path}"

    def _agile_url(self, path: str) -> str:
        return f"https://{self._site_url()}/rest/agile/1.0/{path}"

    @property
    def auth_headers(self) -> dict[str, str]:
        creds = self.context.credentials if self.context else {}
        access_token = creds.get("access_token")
        if access_token:
            return {"Authorization": f"Bearer {access_token}"}
        email = creds.get("email")
        api_token = creds.get("api_token")
        if email and api_token:
            encoded = base64.b64encode(f"{email}:{api_token}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    async def validate_connection(self) -> bool:
        resp = await self._get(self._jira_url("myself"))
        data = resp.json()
        return "accountId" in data

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get(self._jira_url("myself"))
            data = resp.json()
            return ProviderHealth.healthy(detail={"account_id": data.get("accountId")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    # ------------------------------------------------------------------ actions

    @action("create_issue")
    async def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description is not None:
            fields["description"] = description
        if priority is not None:
            fields["priority"] = {"name": priority}
        if assignee is not None:
            fields["assignee"] = {"accountId": assignee}
        resp = await self._post(self._jira_url("issue"), json_data={"fields": fields})
        return resp.json()

    @action("get_issue")
    async def get_issue(self, issue_key: str, fields: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if fields is not None:
            params["fields"] = fields
        resp = await self._get(self._jira_url(f"issue/{issue_key}"), params=params)
        return resp.json()

    @action("update_issue")
    async def update_issue(self, issue_key: str, **fields: Any) -> dict[str, Any]:
        resp = await self._put(
            self._jira_url(f"issue/{issue_key}"),
            json_data={"fields": dict(fields)},
        )
        return resp.json()

    @action("search_issues")
    async def search_issues(self, jql: str, max_results: int = 50) -> dict[str, Any]:
        url = self._jira_url(f"search?jql={quote(jql)}&maxResults={max_results}")
        resp = await self._get(url)
        return resp.json()

    @action("get_sprint")
    async def get_sprint(self, board_id: int, state: str = "active") -> dict[str, Any]:
        url = self._agile_url(f"board/{board_id}/sprint?state={state}")
        resp = await self._get(url)
        return resp.json()

    @action("list_projects")
    async def list_projects(self) -> dict[str, Any]:
        resp = await self._get(self._jira_url("project"))
        return resp.json()

    @action("add_comment")
    async def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        resp = await self._post(
            self._jira_url(f"issue/{issue_key}/comment"),
            json_data={"body": body},
        )
        return resp.json()

    @action("get_user")
    async def get_user(self, account_id: str) -> dict[str, Any]:
        resp = await self._get(self._jira_url("user"), params={"accountId": account_id})
        return resp.json()

    # ------------------------------------------------------------------ webhooks

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac
        import json

        from config import settings

        signature = headers.get("X-Hub-Signature", "")
        if not signature:
            return False
        secret = settings.webhook_default_secret.get_secret_value()
        expected = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        provided = signature
        if provided.startswith("sha256="):
            provided = provided[len("sha256="):]
        return hmac.compare_digest(provided, expected)


ProviderCls = JiraProvider
provider = JiraProvider()
