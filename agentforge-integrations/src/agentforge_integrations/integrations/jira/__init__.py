from ...core.registry import IntegrationRegistry
from .client import JiraIntegration
from .models import JiraComment, JiraIssue, JiraProject

IntegrationRegistry.register("jira", JiraIntegration)

__all__ = ["JiraComment", "JiraIntegration", "JiraIssue", "JiraProject"]