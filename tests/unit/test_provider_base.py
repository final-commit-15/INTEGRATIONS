"""Tests for the provider base contract: action routing, context, health."""

from __future__ import annotations

import pytest

from exceptions import ActionNotFound, CredentialInvalid
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderContext,
    ProviderHealth,
    action,
)


class FakeProvider(BaseIntegrationProvider):
    provider_key = "fake"
    name = "Fake"
    auth_type = "token"
    base_url = "https://fake.example.com"

    capabilities = [
        Capability(name="echo", description="Echo a value", params_schema={"required": ["value"]}),
        Capability(name="fail", description="Raise", params_schema={}),
    ]

    async def validate_connection(self) -> bool:
        return True

    async def refresh_token(self) -> bool:
        return True

    @action("echo")
    async def echo(self, value: str) -> dict[str, str]:
        return {"echo": value}

    @action("fail")
    async def fail(self) -> None:
        raise RuntimeError("boom")


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


def test_action_decorator_collects_actions(provider: FakeProvider) -> None:
    assert set(provider._dispatch) == {"echo", "fail"}


def test_collect_actions_respects_mro(provider: FakeProvider) -> None:
    # _dispatch entries are bound methods.
    assert callable(provider._dispatch["echo"])
    assert provider._dispatch["echo"].__self__ is provider


async def test_execute_dispatches_to_handler(provider: FakeProvider) -> None:
    result = await provider.execute_action("echo", {"value": "hi"})
    assert result == {"echo": "hi"}


async def test_execute_propagates_exception(provider: FakeProvider) -> None:
    with pytest.raises(RuntimeError):
        await provider.execute_action("fail", {})


async def test_unknown_action_raises_action_not_found(provider: FakeProvider) -> None:
    with pytest.raises(ActionNotFound) as exc_info:
        await provider.execute_action("does_not_exist", {})
    assert exc_info.value.code == "action_not_found"
    assert exc_info.value.provider == "fake"
    assert "does_not_exist" in exc_info.value.message


def test_provider_context_require_passes_when_present() -> None:
    context = ProviderContext(provider="fake", workspace_id="ws-1", credentials={"api_key": "k"})
    assert context.require("api_key") == context.credentials


def test_provider_context_require_raises_when_missing() -> None:
    context = ProviderContext(provider="fake", workspace_id="ws-1", credentials={"api_key": "k"})
    with pytest.raises(CredentialInvalid) as exc_info:
        context.require("missing", "also_missing")
    assert exc_info.value.provider == "fake"
    assert "missing, also_missing" in exc_info.value.message


async def test_health_returns_provider_health(provider: FakeProvider) -> None:
    health = await provider.health()
    assert isinstance(health, ProviderHealth)
    assert health.status == "ok"


async def test_health_down_on_failure() -> None:
    class Broken(FakeProvider):
        async def validate_connection(self) -> bool:
            raise RuntimeError("unreachable")

    health = await Broken().health()
    assert isinstance(health, ProviderHealth)
    assert health.status == "down"
    assert "unreachable" in health.detail.get("error", "")


def test_provider_health_helpers() -> None:
    healthy = ProviderHealth.healthy(latency_ms=1.5, detail={"x": 1})
    assert healthy.status == "ok"
    assert healthy.latency_ms == 1.5
    down = ProviderHealth.down(detail={"reason": "x"})
    assert down.status == "down"
    assert down.detail == {"reason": "x"}


def test_capability_dataclass() -> None:
    cap = Capability(name="x", description="d", params_schema={}, examples=["a"])
    assert cap.examples == ["a"]
    assert cap.name == "x"


def test_list_capabilities_returns_dicts(provider: FakeProvider) -> None:
    caps = provider.list_capabilities()
    assert caps == [
        {"name": "echo", "description": "Echo a value", "params_schema": {"required": ["value"]}, "examples": []},
        {"name": "fail", "description": "Raise", "params_schema": {}, "examples": []},
    ]


def test_get_capability(provider: FakeProvider) -> None:
    assert provider.get_capability("echo").name == "echo"
    assert provider.get_capability("nope") is None


def test_base_headers_include_user_agent(provider: FakeProvider) -> None:
    headers = provider.base_headers
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("agentforge-integrations/")


def test_client_lazy_creation_and_close(provider: FakeProvider) -> None:
    async def _probe() -> None:
        client = provider.client
        assert client is not None
        assert provider._client is client
        await provider.aclose()
        assert provider._client is None

    import asyncio

    asyncio.run(_probe())
