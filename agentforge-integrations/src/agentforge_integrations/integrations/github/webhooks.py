import logging
from typing import Any

logger = logging.getLogger(__name__)


class GitHubWebhookHandler:
    """GitHub-specific webhook event handling."""

    def __init__(self, github_client):
        self.http_client = github_client

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        """Handle GitHub webhook events."""
        if event_type is None:
            logger.warning("Received GitHub webhook without event type")
            return

        logger.info(f"Processing GitHub event: {event_type}")

        # Route to specific handlers
        if event_type == "push":
            await self._handle_push(payload)
        elif event_type == "pull_request":
            await self._handle_pull_request(payload)
        elif event_type == "issues":
            await self._handle_issue(payload)
        elif event_type == "issue_comment":
            await self._handle_issue_comment(payload)
        else:
            logger.debug(f"Unhandled GitHub event: {event_type}")

    async def _handle_push(self, payload: dict[str, Any]) -> None:
        # Example: Notify agents about new commits
        repo = payload.get("repository", {}).get("full_name")
        ref = payload.get("ref")
        commits = payload.get("commits", [])
        logger.info(f"Push to {repo} ({ref}) with {len(commits)} commits")

    async def _handle_pull_request(self, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        pr = payload.get("pull_request")
        if pr:
            logger.info(f"PR #{pr.get('number')} {action} in {payload.get('repository', {}).get('full_name')}")

    async def _handle_issue(self, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        issue = payload.get("issue")
        if issue:
            logger.info(f"Issue #{issue.get('number')} {action} in {payload.get('repository', {}).get('full_name')}")

    async def _handle_issue_comment(self, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        comment = payload.get("comment")
        issue = payload.get("issue")
        if comment and issue:
            logger.info(f"Comment {action} on issue #{issue.get('number')} in {payload.get('repository', {}).get('full_name')}")