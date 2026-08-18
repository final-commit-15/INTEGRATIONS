from ...core.registry import IntegrationRegistry
from .client import DocumentationIntegration
from .models import Document, DocumentFolder

IntegrationRegistry.register("documentation", DocumentationIntegration)

__all__ = ["Document", "DocumentFolder", "DocumentationIntegration"]