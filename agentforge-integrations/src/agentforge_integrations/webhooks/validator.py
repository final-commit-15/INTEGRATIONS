import hashlib
import hmac
import logging
import time

from ..core.config import settings

logger = logging.getLogger(__name__)

# Configure whether validation is mandatory (default True)
VALIDATION_REQUIRED = getattr(settings, "WEBHOOK_VALIDATION_REQUIRED", True)
SLACK_TIMESTAMP_TOLERANCE = 60  # seconds


def validate_signature(integration_name: str, body: bytes, headers: dict[str, str]) -> bool:
    """
    Validate HMAC signature for webhooks.
    If validation is required and secret missing, returns False.
    """
    integration_name = integration_name.lower()

    # GitHub
    if integration_name == "github":
        secret = settings.github_webhook_secret
        if not secret:
            if VALIDATION_REQUIRED:
                logger.error("GitHub webhook secret missing; rejecting request")
                return False
            logger.warning("GitHub webhook secret not configured, validation bypassed (unsafe)")
            return True
        signature_header = headers.get("X-Hub-Signature-256")
        if not signature_header:
            return False
        expected = hmac.new(
            key=secret.encode(),
            msg=body,
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature_header)

    # Slack
    elif integration_name == "slack":
        secret = settings.integration_slack_signing_secret
        if not secret:
            if VALIDATION_REQUIRED:
                logger.error("Slack signing secret missing; rejecting request")
                return False
            logger.warning("Slack signing secret not configured, validation bypassed (unsafe)")
            return True

        timestamp = headers.get("X-Slack-Request-Timestamp")
        signature = headers.get("X-Slack-Signature")
        if not timestamp or not signature:
            return False

        # Replay protection
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > SLACK_TIMESTAMP_TOLERANCE:
                logger.warning(f"Slack request timestamp too old: {ts}")
                return False
        except ValueError:
            return False

        basestring = f"v0:{timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(
            key=secret.encode(),
            msg=basestring.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # Jira / Teams (simple secret match)
    elif integration_name in ("jira", "teams"):
        secret = getattr(settings, f"{integration_name}_webhook_secret", None)
        if not secret:
            if VALIDATION_REQUIRED:
                logger.error(f"{integration_name} webhook secret missing; rejecting request")
                return False
            logger.warning(f"{integration_name} webhook secret not configured, validation bypassed (unsafe)")
            return True
        provided = headers.get("X-Webhook-Secret")
        return hmac.compare_digest(secret, provided)

    # Unknown integration – if validation required, reject
    else:
        if VALIDATION_REQUIRED:
            logger.warning(f"No validation configured for {integration_name}, rejecting")
            return False
        logger.warning(f"No validation for {integration_name}, accepting all")
        return True