import pytest

from agentforge_integrations.core.base import Integration, IntegrationConfig


class DummyIntegration(Integration):
    async def initialize(self):
        self._initialized = True
    async def health_check(self):
        return True
    async def execute(self, action, **kwargs):
        return {"action": action}


def test_integration_config_defaults():
    config = IntegrationConfig(name="test")
    assert config.name == "test"
    assert config.enabled is True
    assert config.credentials == {}
    assert config.extra == {}


def test_integration_abstract_methods():
    with pytest.raises(TypeError):
        Integration(IntegrationConfig(name="test"))  # abstract


@pytest.mark.asyncio
async def test_dummy_integration():
    config = IntegrationConfig(name="dummy")
    inst = DummyIntegration(config)
    assert inst.initialized is False
    await inst.initialize()
    assert inst.initialized is True
    assert await inst.health_check() is True
    result = await inst.execute("test", foo="bar")
    assert result["action"] == "test"