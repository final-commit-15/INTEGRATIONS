"""Application configuration.

Central, validated, environment-driven settings for the AgentForge Integrations
service. Uses Pydantic Settings so every value is typed, validated and
documented via the generated JSON schema.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Service ---
    app_name: str = Field(default="agentforge-integrations")
    app_version: str = Field(default="1.0.0")
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
    )

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentforge"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    redis_token_cache_ttl: int = 300
    redis_webhook_ttl: int = 86400

    # --- Crypto ---
    encryption_key: SecretStr = Field(default="")
    encryption_key_previous: list[str] = Field(default_factory=list)
    credential_hash_salt: SecretStr = Field(default="")

    # --- JWT ---
    jwt_secret: SecretStr = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # --- Rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"
    rate_limit_webhook: str = "120/minute"
    rate_limit_oauth: str = "10/minute"

    # --- Observability ---
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agentforge-integrations"
    otel_traces_sample_ratio: float = 0.1

    # --- OAuth ---
    oauth_redirect_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    oauth_state_ttl_seconds: int = 600

    # --- Google ---
    google_client_id: str = ""
    google_client_secret: SecretStr = Field(default="")
    google_api_key: str = ""
    google_scopes: str = (
        "openid,email,profile,gmail.readonly,gmail.send,gmail.modify,"
        "drive,drive.file,calendar,calendar.events,documents,spreadsheets"
    )

    # --- Slack ---
    slack_client_id: str = ""
    slack_client_secret: SecretStr = Field(default="")
    slack_signing_secret: SecretStr = Field(default="")
    slack_scopes: str = (
        "channels:read,channels:manage,chat:write,users:read,"
        "reactions:write,files:write,im:history,mpim:read,groups:read"
    )

    # --- GitHub ---
    github_client_id: str = ""
    github_client_secret: SecretStr = Field(default="")
    github_webhook_secret: SecretStr = Field(default="")
    github_scopes: str = "repo,read:org,workflow,user:email"

    # --- Notion ---
    notion_client_id: str = ""
    notion_client_secret: SecretStr = Field(default="")
    notion_scopes: str = "read_content,write_content"

    # --- Discord ---
    discord_client_id: str = ""
    discord_client_secret: SecretStr = Field(default="")
    discord_bot_token: SecretStr = Field(default="")
    discord_scopes: str = "bot,identify,guilds,guilds.join"

    # --- Atlassian (Jira) ---
    jira_client_id: str = ""
    jira_client_secret: SecretStr = Field(default="")
    jira_api_token: SecretStr = Field(default="")
    jira_site_url: str = ""
    jira_scopes: str = "read:jira-user,offline_access"

    # --- Trello ---
    trello_api_key: str = ""
    trello_api_token: SecretStr = Field(default="")

    # --- Airtable ---
    airtable_api_key: SecretStr = Field(default="")
    airtable_base_id: str = ""

    # --- HubSpot ---
    hubspot_client_id: str = ""
    hubspot_client_secret: SecretStr = Field(default="")
    hubspot_scopes: str = (
        "oauth,crm.objects.contacts.read,crm.objects.deals.read,"
        "crm.objects.companies.read,crm.schemas.contacts.read"
    )

    # --- Salesforce ---
    salesforce_client_id: str = ""
    salesforce_client_secret: SecretStr = Field(default="")
    salesforce_instance_url: str = ""
    salesforce_api_version: str = "v62.0"

    # --- Stripe ---
    stripe_secret_key: SecretStr = Field(default="")
    stripe_publishable_key: str = ""
    stripe_webhook_secret: SecretStr = Field(default="")

    # --- Twilio ---
    twilio_account_sid: str = ""
    twilio_auth_token: SecretStr = Field(default="")
    twilio_api_key: str = ""
    twilio_api_secret: SecretStr = Field(default="")
    twilio_phone_number: str = ""
    twilio_messaging_service_sid: str = ""
    twilio_verify_service_sid: str = ""
    twilio_webhook_secret: SecretStr = Field(default="")

    # --- SendGrid ---
    sendgrid_api_key: SecretStr = Field(default="")
    sendgrid_from_email: str = "noreply@agentforge.ai"
    sendgrid_from_name: str = "AgentForge"

    # --- Supabase ---
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = Field(default="")

    # --- AWS ---
    aws_access_key_id: str = ""
    aws_secret_access_key: SecretStr = Field(default="")
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = ""

    # --- Dropbox ---
    dropbox_client_id: str = ""
    dropbox_client_secret: SecretStr = Field(default="")
    dropbox_refresh_token: SecretStr = Field(default="")

    # --- OneDrive ---
    onedrive_client_id: str = ""
    onedrive_client_secret: SecretStr = Field(default="")
    onedrive_tenant_id: str = "common"
    onedrive_scopes: str = "files.readwrite.all"

    # --- MongoDB ---
    mongodb_uri: str = ""
    mongodb_db_name: str = "agentforge"

    # --- Webhooks ---
    webhook_default_secret: SecretStr = Field(default="")
    webhook_retry_max: int = 5
    webhook_retry_backoff_base: int = 2
    webhook_poll_interval_seconds: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.strip("[]").split(",") if origin.strip()]
        return value

    @field_validator("encryption_key_previous", mode="before")
    @classmethod
    def _parse_previous_keys(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [k.strip() for k in value.split(",") if k.strip()]
        return value or []

    @property
    def encryption_key_bytes(self) -> bytes:
        """Return a Fernet-compatible key (url-safe base64 of 32 bytes)."""
        key = self.encryption_key.get_secret_value().strip()
        if not key:
            if self.is_production:
                raise RuntimeError("ENCRYPTION_KEY is not configured")
            # Deterministic dev-only key so local/dev instances and the test
            # suite work out of the box. Production mandates an explicit key.
            import base64

            return base64.urlsafe_b64encode(hashlib.sha256(b"agentforge-integrations-dev-key-v1").digest())
        salt = self.credential_hash_salt.get_secret_value().strip() or "agentforge"
        import base64

        derived = _derive_key(key, salt, 32)
        return base64.urlsafe_b64encode(derived)

    @property
    def google_scopes_list(self) -> list[str]:
        return [s.strip() for s in self.google_scopes.split(",") if s.strip()]

    @property
    def slack_scopes_list(self) -> list[str]:
        return [s.strip() for s in self.slack_scopes.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def provider_config(self, provider_key: str) -> dict[str, Any]:
        """Return provider-specific configuration as a plain dict."""
        if provider_key.startswith("gmail") or provider_key in (
            "google_drive",
            "google_calendar",
            "google_docs",
            "google_sheets",
        ):
            return {
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret.get_secret_value(),
                "scopes": self.google_scopes_list,
                "api_key": self.google_api_key,
            }
        if provider_key == "slack":
            return {
                "client_id": self.slack_client_id,
                "client_secret": self.slack_client_secret.get_secret_value(),
                "scopes": self.slack_scopes_list,
                "signing_secret": self.slack_signing_secret.get_secret_value(),
            }
        if provider_key == "github":
            return {
                "client_id": self.github_client_id,
                "client_secret": self.github_client_secret.get_secret_value(),
                "scopes": self.github_scopes.split(","),
                "webhook_secret": self.github_webhook_secret.get_secret_value(),
            }
        if provider_key == "notion":
            return {
                "client_id": self.notion_client_id,
                "client_secret": self.notion_client_secret.get_secret_value(),
                "scopes": self.notion_scopes.split(","),
            }
        if provider_key == "discord":
            return {
                "client_id": self.discord_client_id,
                "client_secret": self.discord_client_secret.get_secret_value(),
                "bot_token": self.discord_bot_token.get_secret_value(),
                "scopes": self.discord_scopes.split(","),
            }
        if provider_key == "jira":
            return {
                "client_id": self.jira_client_id,
                "client_secret": self.jira_client_secret.get_secret_value(),
                "api_token": self.jira_api_token.get_secret_value(),
                "site_url": self.jira_site_url,
                "scopes": self.jira_scopes.split(","),
            }
        if provider_key == "trello":
            return {
                "api_key": self.trello_api_key,
                "api_token": self.trello_api_token.get_secret_value(),
            }
        if provider_key == "airtable":
            return {
                "api_key": self.airtable_api_key.get_secret_value(),
                "base_id": self.airtable_base_id,
            }
        if provider_key == "hubspot":
            return {
                "client_id": self.hubspot_client_id,
                "client_secret": self.hubspot_client_secret.get_secret_value(),
                "scopes": self.hubspot_scopes.split(","),
            }
        if provider_key == "salesforce":
            return {
                "client_id": self.salesforce_client_id,
                "client_secret": self.salesforce_client_secret.get_secret_value(),
                "instance_url": self.salesforce_instance_url,
                "api_version": self.salesforce_api_version,
            }
        if provider_key == "stripe":
            return {
                "secret_key": self.stripe_secret_key.get_secret_value(),
                "webhook_secret": self.stripe_webhook_secret.get_secret_value(),
            }
        if provider_key == "twilio":
            return {
                "account_sid": self.twilio_account_sid,
                "auth_token": self.twilio_auth_token.get_secret_value(),
                "api_key": self.twilio_api_key,
                "api_secret": self.twilio_api_secret.get_secret_value(),
                "phone_number": self.twilio_phone_number,
                "messaging_service_sid": self.twilio_messaging_service_sid,
                "verify_service_sid": self.twilio_verify_service_sid,
                "webhook_secret": self.twilio_webhook_secret.get_secret_value(),
            }
        if provider_key == "sendgrid":
            return {
                "api_key": self.sendgrid_api_key.get_secret_value(),
                "from_email": self.sendgrid_from_email,
                "from_name": self.sendgrid_from_name,
            }
        if provider_key == "supabase":
            return {
                "url": self.supabase_url,
                "service_role_key": self.supabase_service_role_key.get_secret_value(),
            }
        if provider_key == "aws_s3":
            return {
                "access_key_id": self.aws_access_key_id,
                "secret_key": self.aws_secret_access_key.get_secret_value(),
                "region": self.aws_region,
                "bucket": self.aws_s3_bucket,
            }
        if provider_key == "dropbox":
            return {
                "client_id": self.dropbox_client_id,
                "client_secret": self.dropbox_client_secret.get_secret_value(),
                "refresh_token": self.dropbox_refresh_token.get_secret_value(),
            }
        if provider_key == "onedrive":
            return {
                "client_id": self.onedrive_client_id,
                "client_secret": self.onedrive_client_secret.get_secret_value(),
                "tenant_id": self.onedrive_tenant_id,
                "scopes": self.onedrive_scopes.split(","),
            }
        if provider_key == "mongodb":
            return {
                "uri": self.mongodb_uri,
                "db_name": self.mongodb_db_name,
            }
        return {}


def _derive_key(secret: str, salt: str, length: int) -> bytes:
    """Derive a fixed-size key from a passphrase using PBKDF2-SHA256."""
    import hashlib

    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 200_000, length)


def _dotenv_load() -> None:
    """Best-effort load of .env when running outside of a process manager."""
    candidate = os.path.join(os.getcwd(), ".env")
    if os.path.exists(candidate):
        from dotenv import load_dotenv

        load_dotenv(candidate)


_dotenv_load()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
