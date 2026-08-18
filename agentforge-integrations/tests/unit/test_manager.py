import pytest

from agentforge_integrations.core.base import Integration
from agentforge_integrations.core.exceptions import ConfigurationError
from agentforge_integrations.core.registry import IntegrationRegistry


class DummyIntegration(Integration):
    async def initialize(self): self._initialized = True
    async def health_check(self): return True
    async def execute(self, action, **kwargs): return {"action": action, "kwargs": kwargs}


@pytest.mark.asyncio
async def test_manager_load_integration(integration_manager):
    IntegrationRegistry.register("dummy", DummyIntegration)
    await integration_manager.load_integration("dummy")
    assert "dummy" in integration_manager._instances


@pytest.mark.asyncio
async def test_manager_execute(integration_manager):
    IntegrationRegistry.register("dummy", DummyIntegration)
    result = await integration_manager.execute("dummy", "test", foo="bar")
    assert result["action"] == "test"
    assert result["kwargs"]["foo"] == "bar"


@pytest.mark.asyncio
async def test_manager_load_unknown(integration_manager):
    with pytest.raises(ConfigurationError):
        await integration_manager.load_integration("unknown")