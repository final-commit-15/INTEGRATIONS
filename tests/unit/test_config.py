"""Tests for application configuration (settings defaults and provider config)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from config import Settings, settings

GOOGLE_PROVIDERS = ("gmail", "google_drive", "google_calendar")


def test_settings_defaults() -> None:
    assert settings.app_name == "agentforge-integrations"
    assert settings.app_version == "1.0.0"
    assert settings.environment == "development"
    assert settings.rate_limit_enabled is False
    assert settings.jwt_secret.get_secret_value() == "change-me-in-production"
    assert settings.api_v1_prefix == "/api/v1"


@pytest.mark.parametrize("provider", GOOGLE_PROVIDERS)
def test_provider_config_google(provider: str) -> None:
    cfg = settings.provider_config(provider)
    assert {"client_id", "client_secret", "scopes", "api_key"} <= set(cfg)
    assert isinstance(cfg["scopes"], list)
    assert "openid" in cfg["scopes"]


def test_provider_config_slack() -> None:
    cfg = settings.provider_config("slack")
    assert set(cfg) == {"client_id", "client_secret", "scopes", "signing_secret"}
    assert "chat:write" in cfg["scopes"]


def test_provider_config_github() -> None:
    cfg = settings.provider_config("github")
    assert set(cfg) == {"client_id", "client_secret", "scopes", "webhook_secret"}
    assert "repo" in cfg["scopes"]


def test_provider_config_stripe() -> None:
    assert set(settings.provider_config("stripe")) == {"secret_key", "webhook_secret"}


def test_provider_config_aws_s3() -> None:
    cfg = settings.provider_config("aws_s3")
    assert {"access_key_id", "secret_key", "region", "bucket"} <= set(cfg)
    assert cfg["region"] == "us-east-1"


def test_provider_config_twilio() -> None:
    cfg = settings.provider_config("twilio")
    assert {
        "account_sid",
        "auth_token",
        "api_key",
        "api_secret",
        "phone_number",
        "messaging_service_sid",
        "verify_service_sid",
        "webhook_secret",
    } <= set(cfg)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("notion", {"client_id", "client_secret", "scopes"}),
        ("discord", {"client_id", "client_secret", "bot_token", "scopes"}),
        ("jira", {"client_id", "client_secret", "api_token", "site_url", "scopes"}),
        ("trello", {"api_key", "api_token"}),
        ("airtable", {"api_key", "base_id"}),
        ("hubspot", {"client_id", "client_secret", "scopes"}),
        ("salesforce", {"client_id", "client_secret", "instance_url", "api_version"}),
        ("sendgrid", {"api_key", "from_email", "from_name"}),
        ("supabase", {"url", "service_role_key"}),
    ],
)
def test_provider_config_key_sets(provider: str, expected: set[str]) -> None:
    assert set(settings.provider_config(provider)) == expected


def test_provider_config_unknown_is_empty() -> None:
    assert settings.provider_config("not_a_provider") == {}


def test_scopes_list_properties() -> None:
    assert isinstance(settings.google_scopes_list, list)
    assert all(isinstance(s, str) and s for s in settings.google_scopes_list)
    assert "gmail.send" in settings.google_scopes_list
    assert "drive.file" in settings.google_scopes_list
    assert "chat:write" in settings.slack_scopes_list


def test_is_production_flag() -> None:
    dev = Settings(environment="development", encryption_key="")
    prod = Settings(environment="production", encryption_key="change-me-16-bytes")
    assert dev.is_production is False
    assert prod.is_production is True


def test_dev_encryption_key_is_valid_fernet() -> None:
    key = settings.encryption_key_bytes
    assert len(key) <= 64
    # A valid Fernet key must decode to exactly 32 bytes and construct Fernet.
    Fernet(key)


def test_encryption_key_uses_explicit_value_when_set() -> None:
    explicit = "0123456789abcdef0123456789abcdef"
    standalone = Settings(ENCRYPTION_KEY=explicit)
    assert standalone.encryption_key_bytes != settings.encryption_key_bytes
    Fernet(standalone.encryption_key_bytes)


def test_production_without_key_raises() -> None:
    prod = Settings(environment="production", encryption_key="")
    with pytest.raises(RuntimeError):
        prod.encryption_key_bytes
