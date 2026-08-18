from ...core.registry import IntegrationRegistry
from .client import GitHubIntegration
from .models import (
    GitHubBranch,
    GitHubFile,
    GitHubIssue,
    GitHubPullRequest,
    GitHubRepo,
)

# Auto-register
IntegrationRegistry.register("github", GitHubIntegration)

__all__ = [
    "GitHubBranch",
    "GitHubFile",
    "GitHubIntegration",
    "GitHubIssue",
    "GitHubPullRequest",
    "GitHubRepo",
]