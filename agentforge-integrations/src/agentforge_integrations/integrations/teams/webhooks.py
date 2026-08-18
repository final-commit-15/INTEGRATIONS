import logging
from typing import Any

logger = logging.getLogger(__name__)


class TeamsWebhookHandler:
    def __init__(self, teams_client):
        self.http_client = teams_client

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        # Microsoft Graph webhook events
        if event_type is None:
            return
        logger.info(f"Processing Teams event: {event_type}")
        # Example: "subscriptionValidation" or "notification"
        if event_type == "subscriptionValidation":
            await self._handle_validation(payload)
        elif event_type == "notification":
            await self._handle_notification(payload)
        else:
            logger.debug(f"Unhandled Teams event: {event_type}")

    async def _handle_validation(self, payload):
        # Graph validation request
        token = payload.get("validationToken")
        if token:
            # Return token in response; handled by receiver
            logger.info("Teams validation token received")
        return token

    async def _handle_notification(self, payload):
        # Process change notifications
        for item in payload.get("value", []):
            resource_data = item.get("resourceData", {})
            event_type = item.get("changeType")
            logger.info(f"Teams notification: {event_type} on {resource_data.get('id')}")