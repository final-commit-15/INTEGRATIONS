import json
import logging

from ..core.exceptions import IntegrationError
from ..core.manager import IntegrationManager

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatcher that uses a shared IntegrationManager."""

    def __init__(self, manager: IntegrationManager):
        self.manager = manager

    async def dispatch(self, integration_name: str, raw_body: bytes, headers: dict[str, str]) -> None:
        integration_name = integration_name.lower()
        integration = await self.manager.get_integration(integration_name)

        # Ensure integration has a webhook handler
        if not hasattr(integration, "handle_webhook"):
            logger.warning(f"Integration '{integration_name}' does not implement handle_webhook.")
            return

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            raise IntegrationError("Invalid JSON payload")

        # Extract event type per provider
        event_type = None
        if integration_name == "github":
            event_type = headers.get("X-GitHub-Event")
        elif integration_name == "slack":
            event_type = headers.get("X-Slack-Event-Type") or data.get("type")
        elif integration_name == "jira":
            event_type = data.get("webhookEvent")
        elif integration_name == "teams":
            # Teams webhooks (Microsoft Graph) may have 'eventType' or 'resourceData'
            event_type = data.get("eventType") or data.get("resource", {}).get("eventType")

        await integration.handle_webhook(event_type, data)
        logger.info(f"Webhook dispatched to {integration_name} (event: {event_type})")