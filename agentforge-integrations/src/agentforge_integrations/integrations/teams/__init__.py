from ...core.registry import IntegrationRegistry
from .client import TeamsIntegration
from .models import TeamsChannel, TeamsMessage, TeamsTeam

IntegrationRegistry.register("teams", TeamsIntegration)

__all__ = ["TeamsChannel", "TeamsIntegration", "TeamsMessage", "TeamsTeam"]