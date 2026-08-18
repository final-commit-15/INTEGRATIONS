from typing import ClassVar

from .base import Integration


class IntegrationRegistry:
    _integrations: ClassVar[dict[str, type[Integration]]] = {}

    @classmethod
    def register(cls, name: str, integration_cls: type[Integration]) -> None:
        cls._integrations[name.lower()] = integration_cls

    @classmethod
    def get(cls, name: str) -> type[Integration] | None:
        return cls._integrations.get(name.lower())

    @classmethod
    def list_integrations(cls) -> list[str]:
        return list(cls._integrations.keys())

    @classmethod
    def clear(cls) -> None:
        cls._integrations.clear()