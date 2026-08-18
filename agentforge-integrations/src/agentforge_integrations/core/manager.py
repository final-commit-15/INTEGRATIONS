import logging
from typing import Any

from ..auth.credentials import CredentialManager
from .base import Integration, IntegrationConfig
from .exceptions import ConfigurationError, IntegrationError
from .registry import IntegrationRegistry

logger = logging.getLogger(__name__)


class IntegrationManager:
    """Orchestrates integration lifecycle and provides unified API for agents."""

    def __init__(self, credential_manager: CredentialManager):
        self._credential_manager = credential_manager
        self._instances: dict[str, Integration] = {}
        self._configs: dict[str, IntegrationConfig] = {}

    async def load_integration(self, name: str) -> None:
        """Load, configure, and initialize an integration by name."""
        name = name.lower()
        if name in self._instances:
            return

        cls = IntegrationRegistry.get(name)
        if not cls:
            raise ConfigurationError(f"Integration '{name}' not registered.")

        # Fetch credentials from secure storage
        creds = await self._credential_manager.get_credentials(name)

        config = IntegrationConfig(
            name=name,
            enabled=True,
            credentials=creds,
        )
        instance = cls(config)
        await instance.initialize()
        self._instances[name] = instance
        self._configs[name] = config
        logger.info(f"Integration '{name}' loaded successfully.")

    async def execute(self, integration_name: str, action: str, **kwargs) -> Any:
        """Execute an action on a specific integration."""
        integration_name = integration_name.lower()
        if integration_name not in self._instances:
            await self.load_integration(integration_name)
        integration = self._instances[integration_name]
        return await integration.execute(action, **kwargs)

    async def get_integration(self, name: str) -> Integration:
        name = name.lower()
        if name not in self._instances:
            await self.load_integration(name)
        return self._instances[name]

    async def health_check_all(self) -> dict[str, bool]:
        results = {}
        for name in IntegrationRegistry.list_integrations():
            try:
                if name not in self._instances:
                    await self.load_integration(name)
                results[name] = await self._instances[name].health_check()
            except (IntegrationError, RuntimeError):
                results[name] = False
        return results

    async def close_all(self) -> None:
        for name, inst in self._instances.items():
            try:
                await inst.close()
            except Exception:
                logger.exception(f"Error closing integration '{name}'")
        self._instances.clear()