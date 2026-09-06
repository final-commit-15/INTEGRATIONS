"""GitHub provider: repositories, issues, pull requests, branches, and comments."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.github.com"


class GithubProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "github"
    name = "GitHub"
    description = "Manage repositories, issues, pull requests, branches, and comments on GitHub."
    auth_type = "oauth2"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = True
    default_scopes = ["repo", "read:org", "workflow", "user:email"]
    oauth_authorize_url = "https://github.com/login/oauth/authorize"
    oauth_token_url = "https://github.com/login/oauth/access_token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = False
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="list_repositories",
            description="List repositories owned or accessible by the authenticated user.",
            params_schema={
                "properties": {
                    "per_page": {"type": "integer"},
                    "page": {"type": "integer"},
                }
            },
        ),
        Capability(
            name="get_repository",
            description="Fetch a single repository by owner and repo name.",
            params_schema={
                "required": ["owner", "repo"],
                "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}},
            },
        ),
        Capability(
            name="create_issue",
            description="Open a new issue on a repository.",
            params_schema={
                "required": ["owner", "repo", "title"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
        Capability(
            name="list_issues",
            description="List issues for a repository, optionally filtered by state.",
            params_schema={
                "required": ["owner", "repo"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string"},
                    "per_page": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="get_issue",
            description="Fetch a single issue by number.",
            params_schema={
                "required": ["owner", "repo", "issue_number"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="update_issue",
            description="Update arbitrary fields of an issue.",
            params_schema={
                "required": ["owner", "repo", "issue_number"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="create_pull_request",
            description="Open a new pull request.",
            params_schema={
                "required": ["owner", "repo", "title", "head", "base"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "head": {"type": "string"},
                    "base": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        ),
        Capability(
            name="list_pull_requests",
            description="List pull requests for a repository.",
            params_schema={
                "required": ["owner", "repo"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string"},
                    "per_page": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="list_commits",
            description="List commits on the default branch of a repository.",
            params_schema={
                "required": ["owner", "repo"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "per_page": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="list_branches",
            description="List all branches in a repository.",
            params_schema={
                "required": ["owner", "repo"],
                "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}},
            },
        ),
        Capability(
            name="create_branch",
            description="Create a new branch pointing at an existing commit SHA.",
            params_schema={
                "required": ["owner", "repo", "branch", "from_sha"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "branch": {"type": "string"},
                    "from_sha": {"type": "string"},
                },
            },
        ),
        Capability(
            name="get_file_content",
            description="Fetch the content of a file at a given path.",
            params_schema={
                "required": ["owner", "repo", "path"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        ),
        Capability(
            name="create_comment",
            description="Add a comment to an issue or pull request.",
            params_schema={
                "required": ["owner", "repo", "issue_number", "body"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "body": {"type": "string"},
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
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def validate_connection(self) -> bool:
        resp = await self._get("/user")
        data = resp.json()
        return "login" in data

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/user")
            data = resp.json()
            return ProviderHealth.healthy(detail={"login": data.get("login")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    # ------------------------------------------------------------------ actions

    @action("list_repositories")
    async def list_repositories(self, per_page: int = 30, page: int = 1) -> dict[str, Any]:
        resp = await self._get("/user/repos", params={"per_page": per_page, "page": page})
        return resp.json()

    @action("get_repository")
    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        resp = await self._get(f"/repos/{owner}/{repo}")
        return resp.json()

    @action("create_issue")
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        json_data: dict[str, Any] = {"title": title}
        if body is not None:
            json_data["body"] = body
        if labels is not None:
            json_data["labels"] = labels
        resp = await self._post(f"/repos/{owner}/{repo}/issues", json_data=json_data)
        return resp.json()

    @action("list_issues")
    async def list_issues(self, owner: str, repo: str, state: str = "open", per_page: int = 30) -> dict[str, Any]:
        resp = await self._get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": per_page},
        )
        return resp.json()

    @action("get_issue")
    async def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        resp = await self._get(f"/repos/{owner}/{repo}/issues/{issue_number}")
        return resp.json()

    @action("update_issue")
    async def update_issue(self, owner: str, repo: str, issue_number: int, **changes: Any) -> dict[str, Any]:
        resp = await self._patch(
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json_data=dict(changes),
        )
        return resp.json()

    @action("create_pull_request")
    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        json_data: dict[str, Any] = {"title": title, "head": head, "base": base}
        if body is not None:
            json_data["body"] = body
        resp = await self._post(f"/repos/{owner}/{repo}/pulls", json_data=json_data)
        return resp.json()

    @action("list_pull_requests")
    async def list_pull_requests(self, owner: str, repo: str, state: str = "open", per_page: int = 30) -> dict[str, Any]:
        resp = await self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": per_page},
        )
        return resp.json()

    @action("list_commits")
    async def list_commits(self, owner: str, repo: str, per_page: int = 30) -> dict[str, Any]:
        resp = await self._get(f"/repos/{owner}/{repo}/commits", params={"per_page": per_page})
        return resp.json()

    @action("list_branches")
    async def list_branches(self, owner: str, repo: str) -> dict[str, Any]:
        resp = await self._get(f"/repos/{owner}/{repo}/branches")
        return resp.json()

    @action("create_branch")
    async def create_branch(self, owner: str, repo: str, branch: str, from_sha: str) -> dict[str, Any]:
        resp = await self._post(
            f"/repos/{owner}/{repo}/git/refs",
            json_data={"ref": f"refs/heads/{branch}", "sha": from_sha},
        )
        return resp.json()

    @action("get_file_content")
    async def get_file_content(self, owner: str, repo: str, path: str) -> dict[str, Any]:
        resp = await self._get(f"/repos/{owner}/{repo}/contents/{path}")
        return resp.json()

    @action("create_comment")
    async def create_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict[str, Any]:
        resp = await self._post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json_data={"body": body},
        )
        return resp.json()

    # ------------------------------------------------------------------ webhooks

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac
        import json

        from config import settings

        signature = headers.get("X-Hub-Signature-256", "")
        if not signature:
            return False
        secret = settings.github_webhook_secret.get_secret_value()
        expected = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        provided = signature
        if provided.startswith("sha256="):
            provided = provided[len("sha256="):]
        return hmac.compare_digest(provided, expected)


ProviderCls = GithubProvider
provider = GithubProvider()
