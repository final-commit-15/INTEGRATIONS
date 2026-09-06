"""/providers package. Importing this package triggers auto-discovery."""

from .base import (
    BaseIntegrationProvider,
    BaseWebhookProvider,
    Capability,
    ProviderContext,
    ProviderHealth,
    action,
)
from .registry import ProviderRegistry, get_registry, registry

__all__ = [
    "BaseIntegrationProvider",
    "BaseWebhookProvider",
    "Capability",
    "ProviderContext",
    "ProviderHealth",
    "ProviderRegistry",
    "action",
    "get_registry",
    "registry",
]
