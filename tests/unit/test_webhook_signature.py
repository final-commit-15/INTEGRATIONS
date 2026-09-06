"""Tests for webhook signature verification across provider styles."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from config import settings
from providers.base import SignatureMixin
from providers.github import GithubProvider
from providers.slack import SlackProvider
from providers.stripe import StripeProvider
from providers.webhook import WebhookProvider

SECRET = "test-signing-secret"


def _hmac_hex(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# SignatureMixin (generic hmac-sha256)
# ---------------------------------------------------------------------------


def test_signature_mixin_hmac_sha256_matches_reference() -> None:
    assert SignatureMixin.hmac_sha256(SECRET, "hello") == _hmac_hex(SECRET, "hello")


def test_signature_mixin_hmac_is_secret_sensitive() -> None:
    assert SignatureMixin.hmac_sha256("secret-a", "body") != SignatureMixin.hmac_sha256("secret-b", "body")


# ---------------------------------------------------------------------------
# Generic/Hub-Style (webhook provider) hmac
# ---------------------------------------------------------------------------


def test_webhook_provider_verifies_sha256_prefix() -> None:
    payload = {"event": "ping", "data": {"ok": True}}
    body = json.dumps(payload)
    sig = SignatureMixin.hmac_sha256(settings.webhook_default_secret.get_secret_value(), body)
    headers = {"X-Webhook-Signature": f"sha256={sig}"}
    assert WebhookProvider.verify_signature(headers, payload) is True


def test_webhook_provider_rejects_tampered_payload() -> None:
    payload = {"event": "ping", "data": {"ok": True}}
    body = json.dumps(payload)
    sig = SignatureMixin.hmac_sha256(settings.webhook_default_secret.get_secret_value(), body)
    headers = {"X-Webhook-Signature": f"sha256={sig}"}
    tampered = {"event": "evil", "data": {"ok": True}}
    assert WebhookProvider.verify_signature(headers, tampered) is False


# ---------------------------------------------------------------------------
# Slack-style (timestamped basestring "v0:<ts>:<body>")
# ---------------------------------------------------------------------------


def test_slack_verify_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "slack_signing_secret", _Secret(SECRET))
    ts = str(int(time.time()))
    raw_body = '{"type": "event_callback", "event": {"type": "message"}}'
    basestring = f"v0:{ts}:{raw_body}"
    signature = "v0=" + _hmac_hex(SECRET, basestring)
    headers = {"x-slack-request-timestamp": ts, "x-slack-signature": signature}
    assert SlackProvider.verify_signature(headers, {"raw_body": raw_body}) is True


def test_slack_verify_signature_rejects_tampered_body(monkeypatch) -> None:
    monkeypatch.setattr(settings, "slack_signing_secret", _Secret(SECRET))
    ts = str(int(time.time()))
    raw_body = '{"type": "event_callback", "event": {"type": "message"}}'
    signature = "v0=" + _hmac_hex(SECRET, f"v0:{ts}:{raw_body}")
    headers = {"x-slack-request-timestamp": ts, "x-slack-signature": signature}
    tampered = {"raw_body": '{"type": "event_callback", "event": {"type": "evil"}}'}
    assert SlackProvider.verify_signature(headers, tampered) is False


def test_slack_verify_signature_rejects_missing_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "slack_signing_secret", _Secret(SECRET))
    assert SlackProvider.verify_signature({}, {"raw_body": "{}"}) is False


# ---------------------------------------------------------------------------
# Stripe-style (signed timestamp "t=<ts>,v1=<sig>")
# ---------------------------------------------------------------------------


def test_stripe_verify_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", _Secret(SECRET))
    ts = str(int(time.time()))
    payload = {"id": "evt_123", "type": "customer.created", "data": {}}
    body = json.dumps(payload)
    sig = _hmac_hex(SECRET, f"{ts}.{body}")
    headers = {"Stripe-Signature": f"t={ts},v1={sig}"}
    assert StripeProvider.verify_signature(headers, payload) is True


def test_stripe_verify_signature_rejects_tampered_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", _Secret(SECRET))
    ts = str(int(time.time()))
    payload = {"id": "evt_123", "type": "customer.created", "data": {}}
    body = json.dumps(payload)
    sig = _hmac_hex(SECRET, f"{ts}.{body}")
    headers = {"Stripe-Signature": f"t={ts},v1={sig}"}
    tampered = {"id": "evt_999", "type": "customer.created", "data": {}}
    assert StripeProvider.verify_signature(headers, tampered) is False


def test_stripe_verify_signature_rejects_malformed_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", _Secret(SECRET))
    payload = {"id": "evt_1"}
    assert StripeProvider.verify_signature({"Stripe-Signature": "garbage"}, payload) is False


# ---------------------------------------------------------------------------
# GitHub-style (X-Hub-Signature-256 over json.dumps payload)
# ---------------------------------------------------------------------------


def test_github_verify_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "github_webhook_secret", _Secret(SECRET))
    payload = {"action": "opened", "issue": {"number": 1}}
    body = json.dumps(payload)
    headers = {"X-Hub-Signature-256": "sha256=" + _hmac_hex(SECRET, body)}
    assert GithubProvider.verify_signature(headers, payload) is True


def test_github_verify_signature_rejects_tampered(monkeypatch) -> None:
    monkeypatch.setattr(settings, "github_webhook_secret", _Secret(SECRET))
    payload = {"action": "opened", "issue": {"number": 1}}
    body = json.dumps(payload)
    headers = {"X-Hub-Signature-256": "sha256=" + _hmac_hex(SECRET, body)}
    assert GithubProvider.verify_signature(headers, {"action": "closed", "issue": {"number": 1}}) is False


class _Secret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)
