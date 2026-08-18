from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class IntegrationConfig(BaseModel):
    """Base configuration for any integration."""
    name: str
    enabled: bool = True
    credentials: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class Integration(ABC):
    """Abstract base class for all external integrations."""

    def __init__(self, config: IntegrationConfig):
        self.config = config
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Perform setup: authenticate, build clients, etc."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity and credentials are valid."""

    @abstractmethod
    async def execute(self, action: str, **kwargs) -> Any:
        """Generic entry point for agents."""

    async def close(self) -> None:
        """Release resources (optional)."""

    @property
    def initialized(self) -> bool:
        return self._initialized