from ...core.registry import IntegrationRegistry
from .client import SlackIntegration
from .models import SlackChannel, SlackMessage, SlackUser

IntegrationRegistry.register("slack", SlackIntegration)

__all__ = ["SlackChannel", "SlackIntegration", "SlackMessage", "SlackUser"]