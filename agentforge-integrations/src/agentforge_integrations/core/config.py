
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings loaded from environment."""
    LOG_LEVEL: str = "INFO"
    ENCRYPTION_KEY: str | None = None

    # GitHub
    integration_github_api_token: str | None = None
    github_webhook_secret: str | None = None

    # Jira
    integration_jira_base_url: str | None = None
    integration_jira_api_token: str | None = None
    integration_jira_email: str | None = None
    jira_webhook_secret: str | None = None

    # Slack
    integration_slack_bot_token: str | None = None
    integration_slack_signing_secret: str | None = None

    # Teams
    integration_teams_webhook_url: str | None = None
    integration_teams_client_id: str | None = None
    integration_teams_client_secret: str | None = None

    # Documentation
    integration_documentation_repo_url: str | None = None
    integration_documentation_api_token: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


settings = Settings()