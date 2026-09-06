"""Provider registry.

Auto-discovers provider packages under ``providers`` using pkgutil (no
hardcoded imports). Each provider package must expose a module-level
``provider`` instance and a ``ProviderCls`` class.

Adding a new provider: create the folder under ``providers/``, implement the
base class contract, expose ``ProviderCls``/``provider`` — it becomes available
immediately.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from exceptions import ProviderNotFound
from providers.base import BaseIntegrationProvider, ProviderContext

PROVIDERS_PACKAGE = __package__


def discover_providers() -> dict[str, type[BaseIntegrationProvider]]:
    """Discover provider packages by scanning the providers package submodules."""
    discovered: dict[str, type[BaseIntegrationProvider]] = {}
    for module_info in pkgutil.iter_modules(importlib.import_module(PROVIDERS_PACKAGE).__path__):
        module_name = module_info.name
        try:
            module = importlib.import_module(f"{PROVIDERS_PACKAGE}.{module_name}")
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "provider import failed", extra={"provider_module": module_name}
            )
            continue
        provider_cls = getattr(module, "ProviderCls", None)
        if (
            provider_cls is not None
            and isinstance(provider_cls, type)
            and issubclass(provider_cls, BaseIntegrationProvider)
            and getattr(provider_cls, "provider_key", "")
        ):
            discovered[provider_cls.provider_key] = provider_cls
    return discovered


class ProviderRegistry:
    """Singleton registry mapping provider keys to provider classes."""

    def __init__(self) -> None:
        self._providers: dict[str, type[BaseIntegrationProvider]] = {}
        self._import_errors: dict[str, str] = {}

    def load(self) -> None:
        discovered = discover_providers()
        self._providers.update(discovered)

    def register(self, provider_key: str, provider_cls: type[BaseIntegrationProvider]) -> None:
        self._providers[provider_key] = provider_cls

    def get(self, provider_key: str) -> type[BaseIntegrationProvider]:
        if provider_key not in self._providers:
            raise ProviderNotFound(f"provider {provider_key!r} is not registered")
        return self._providers[provider_key]

    def get_or_none(self, provider_key: str) -> type[BaseIntegrationProvider] | None:
        return self._providers.get(provider_key)

    def all(self) -> dict[str, type[BaseIntegrationProvider]]:
        return dict(self._providers)

    def keys(self) -> list[str]:
        return sorted(self._providers)

    def build(
        self,
        provider_key: str,
        context: ProviderContext | None = None,
        **kwargs: Any,
    ) -> BaseIntegrationProvider:
        return self.get(provider_key)(context=context, **kwargs)


registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    return registry
