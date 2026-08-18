import logging
from typing import Any

logger = logging.getLogger(__name__)


class SlackWebhookHandler:
    def __init__(self, slack_client):
        self.http_client = slack_client

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        if event_type == "url_verification":
            # Slack challenge
            return await self._handle_url_verification(payload)

        if event_type != "event_callback":
            return

        event = payload.get("event", {})
        event_type = event.get("type")
        if event_type == "message":
            await self._handle_message(event)
        elif event_type == "app_mention":
            await self._handle_app_mention(event)
        elif event_type == "reaction_added" or event_type == "reaction_removed":
            await self._handle_reaction(event_type, event)
        else:
            logger.debug(f"Unhandled Slack event: {event_type}")

    async def _handle_url_verification(self, payload):
        # Slack expects a challenge response
        # Return the challenge value (handled in receiver or directly)
        challenge = payload.get("challenge")
        if challenge:
            # This will be handled by the receiver; we can return the challenge
            # But we need to return it as a response; we'll let the dispatcher handle it
            # So we just log
            logger.info("Slack URL verification challenge received")
        return challenge

    async def _handle_message(self, event):
        user = event.get("user")
        text = event.get("text")
        channel = event.get("channel")
        logger.info(f"Slack message from {user} in {channel}: {text[:100]}")

    async def _handle_app_mention(self, event):
        user = event.get("user")
        text = event.get("text")
        channel = event.get("channel")
        logger.info(f"Slack app mention from {user} in {channel}: {text[:100]}")

    async def _handle_reaction(self, event_type: str, event):
        user = event.get("user")
        reaction = event.get("reaction")
        item = event.get("item", {})
        logger.info(f"Slack reaction {reaction} {event_type} by {user} on {item}")