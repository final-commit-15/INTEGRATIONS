import logging
from typing import Any

logger = logging.getLogger(__name__)


class JiraWebhookHandler:
    def __init__(self, jira_client):
        self.http_client = jira_client

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        if not event_type:
            return
        logger.info(f"Processing Jira event: {event_type}")
        if event_type == "jira:issue_created":
            await self._handle_issue_created(payload)
        elif event_type == "jira:issue_updated":
            await self._handle_issue_updated(payload)
        elif event_type == "jira:issue_deleted":
            await self._handle_issue_deleted(payload)
        elif "comment" in event_type:
            await self._handle_comment_event(event_type, payload)
        else:
            logger.debug(f"Unhandled Jira event: {event_type}")

    async def _handle_issue_created(self, payload):
        issue = payload.get("issue", {})
        logger.info(f"Issue {issue.get('key')} created: {issue.get('summary')}")

    async def _handle_issue_updated(self, payload):
        issue = payload.get("issue", {})
        logger.info(f"Issue {issue.get('key')} updated")

    async def _handle_issue_deleted(self, payload):
        issue = payload.get("issue", {})
        logger.info(f"Issue {issue.get('key')} deleted")

    async def _handle_comment_event(self, event_type: str, payload):
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        logger.info(f"Comment {event_type} on issue {issue.get('key')}: {comment.get('body', '')[:50]}")