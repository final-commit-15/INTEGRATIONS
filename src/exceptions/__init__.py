"""Custom exceptions used across the AgentForge Integrations service."""

from __future__ import annotations

from typing import Any


class IntegrationError(Exception):
    """Base class for all integration errors."""

    status_code: int = 500
    code: str = "integration_error"

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.provider = provider
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.provider:
            payload["provider"] = self.provider
        if self.details:
            payload["details"] = self.details
        return payload


class ProviderUnavailable(IntegrationError):
    """Raised when a third-party provider is unreachable or degrading."""

    status_code = 503
    code = "provider_unavailable"


class OAuthFailed(IntegrationError):
    """Raised when the OAuth exchange or authorization fails."""

    status_code = 401
    code = "oauth_failed"


class TokenExpired(IntegrationError):
    """Raised when the stored access token is expired and cannot be refreshed."""

    status_code = 401
    code = "token_expired"


class CredentialInvalid(IntegrationError):
    """Raised when stored credentials are missing, corrupted, or rejected."""

    status_code = 401
    code = "credential_invalid"


class WebhookVerificationFailed(IntegrationError):
    """Raised when a webhook signature cannot be verified."""

    status_code = 401
    code = "webhook_verification_failed"


class RateLimitExceeded(IntegrationError):
    """Raised when a provider or API rate limit is exceeded."""

    status_code = 429
    code = "rate_limit_exceeded"


class ProviderNotFound(IntegrationError):
    """Raised when requesting an unregistered provider."""

    status_code = 404
    code = "provider_not_found"


class ActionNotFound(IntegrationError):
    """Raised when a provider does not expose the requested action."""

    status_code = 404
    code = "action_not_found"


class WorkspaceNotFound(IntegrationError):
    """Raised when a workspace cannot be resolved."""

    status_code = 404
    code = "workspace_not_found"


class ConnectionNotFound(IntegrationError):
    """Raised when an integration connection does not exist."""

    status_code = 404
    code = "connection_not_found"


class CredentialNotFound(IntegrationError):
    """Raised when a credential record is missing."""

    status_code = 404
    code = "credential_not_found"


class ValidationError(IntegrationError):
    """Raised when an action payload fails validation."""

    status_code = 422
    code = "validation_error"


class CircuitBreakerOpen(IntegrationError):
    """Raised when the provider circuit breaker is open."""

    status_code = 503
    code = "circuit_breaker_open"


class EncryptionError(IntegrationError):
    """Raised when credential encryption/decryption fails."""

    status_code = 500
    code = "encryption_error"


class WebhookDeliveryFailed(IntegrationError):
    """Raised when a webhook cannot be dispatched to a subscriber."""

    status_code = 502
    code = "webhook_delivery_failed"


class UnauthorizedError(IntegrationError):
    """Raised when the calling principal is not authorized."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(IntegrationError):
    """Raised when the calling principal lacks RBAC permission."""

    status_code = 403
    code = "forbidden"
