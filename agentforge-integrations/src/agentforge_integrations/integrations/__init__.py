# Import integration modules to trigger registration
from . import documentation, github, jira, slack, teams

__all__ = ["documentation", "github", "jira", "slack", "teams"]