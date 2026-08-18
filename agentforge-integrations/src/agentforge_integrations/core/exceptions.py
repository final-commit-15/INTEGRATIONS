class IntegrationError(Exception):
    """Base exception for all integration errors."""


class ConfigurationError(IntegrationError):
    """Missing or invalid configuration."""


class AuthenticationError(IntegrationError):
    """Authentication failed (invalid token, OAuth error, etc.)."""


class RateLimitError(IntegrationError):
    """Rate limit exceeded."""


class WebhookError(IntegrationError):
    """Webhook validation or processing error."""


class TimeoutError(IntegrationError):
    """Request timeout."""


class NotFoundError(IntegrationError):
    """Resource not found."""
