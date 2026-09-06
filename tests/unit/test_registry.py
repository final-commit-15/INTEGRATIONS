"""Tests for the provider registry: discovery, registration, and capabilities."""

from __future__ import annotations

import importlib

import pytest

from providers.registry import get_registry, registry

EXPECTED_PROVIDERS = {
    "airtable",
    "aws_s3",
    "discord",
    "dropbox",
    "github",
    "gmail",
    "google_calendar",
    "google_drive",
    "hubspot",
    "jira",
    "mongodb",
    "mysql",
    "notion",
    "onedrive",
    "postgres",
    "salesforce",
    "sendgrid",
    "slack",
    "stripe",
    "supabase",
    "trello",
    "twilio",
    "webhook",
}

KNOWN_ACTIONS: dict[str, set[str]] = {
    "stripe": {"list_customers", "create_customer", "get_event"},
    "slack": {"send_message", "list_channels", "create_channel"},
    "github": {"list_repositories", "get_repository", "create_issue", "list_branches"},
    "notion": {"search", "create_page", "query_database"},
    "sendgrid": {"send_email", "list_templates"},
    "dropbox": {"upload_file", "list_folder"},
}


def test_all_expected_providers_registered() -> None:
    keys = set(registry.keys())
    assert keys == EXPECTED_PROVIDERS
    assert len(keys) == 23


@pytest.mark.parametrize("key", sorted(EXPECTED_PROVIDERS))
def test_each_provider_has_class_and_instance(key: str) -> None:
    provider_cls = registry.get(key)
    module = importlib.import_module(f"providers.{key}")
    assert module.ProviderCls is provider_cls
    assert isinstance(module.provider, provider_cls)
    # Module-level instance has the same key.
    assert module.provider.provider_key == key


@pytest.mark.parametrize("key", sorted(EXPECTED_PROVIDERS))
def test_provider_key_matches_module_name(key: str) -> None:
    provider_cls = registry.get(key)
    assert provider_cls.provider_key == key
    assert provider_cls.__module__ == f"providers.{key}"


@pytest.mark.parametrize("key", sorted(EXPECTED_PROVIDERS))
def test_capabilities_are_executable_actions(key: str) -> None:
    provider = registry.build(key)
    capability_names = {cap.name for cap in provider.capabilities}
    assert capability_names, f"{key} declares no capabilities"
    missing = capability_names - set(provider._dispatch)
    assert not missing, f"{key} capabilities without handlers: {sorted(missing)}"
    # And every declared action is surfaced as a capability.
    extra = set(provider._dispatch) - capability_names
    assert not extra, f"{key} actions without capability declarations: {sorted(extra)}"


@pytest.mark.parametrize(
    ("provider", "expected_actions"),
    [(k, v) for k, v in KNOWN_ACTIONS.items()],
)
def test_known_action_set(provider: str, expected_actions: set[str]) -> None:
    provider_cls = registry.get(provider)
    names = {cap.name for cap in provider_cls.capabilities}
    assert expected_actions <= names


def test_registry_get_unknown_raises() -> None:
    from exceptions import ProviderNotFound

    with pytest.raises(ProviderNotFound):
        registry.get("definitely-not-registered")


def test_registry_get_or_none_unknown() -> None:
    assert registry.get_or_none("nope") is None


def test_get_registry_returns_singleton() -> None:
    assert get_registry() is registry


def test_unregistered_webhook_flag_surface() -> None:
    assert registry.get("github").supports_webhooks is True
    assert registry.get("notion").supports_webhooks is False
    assert registry.get("stripe").supports_webhooks is True
