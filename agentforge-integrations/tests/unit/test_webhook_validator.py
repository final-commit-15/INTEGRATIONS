import hashlib
import hmac

from agentforge_integrations.core.config import settings
from agentforge_integrations.webhooks.validator import validate_signature


def test_github_valid_signature(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "secret")
    body = b'{"test":1}'
    headers = {"X-Hub-Signature-256": "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()}
    assert validate_signature("github", body, headers) is True

def test_github_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    monkeypatch.setattr("agentforge_integrations.webhooks.validator.VALIDATION_REQUIRED", True)
    assert validate_signature("github", b"", {}) is False