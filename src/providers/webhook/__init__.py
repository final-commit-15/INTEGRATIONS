"""Generic outbound webhook provider: deliveries, signing, and ping probes."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx

from config import settings
from exceptions import IntegrationError
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)
from utils.security import validate_target_url


class WebhookProvider(BaseIntegrationProvider):
    provider_key = "webhook"
    name = "Webhook"
    description = "Send signed webhook deliveries and probe endpoint availability."
    auth_type = "none"
    base_url = ""
    timeout = 15.0
    supports_webhooks = True

    allowed_status = (401, 403, 404, 409, 422)

    capabilities = [
        Capability(
            name="send_webhook",
            description="Send an outbound webhook payload to a URL.",
            params_schema={
                "required": ["url", "payload"],
                "properties": {
                    "url": {"type": "string"},
                    "payload": {"type": "object"},
                    "headers": {"type": "object"},
                    "method": {"type": "string"},
                    "secret": {"type": "string"},
                },
            },
        ),
        Capability(
            name="send_signed_webhook",
            description="Send a webhook signed with a provided secret.",
            params_schema={
                "required": ["url", "payload", "secret"],
                "properties": {
                    "url": {"type": "string"},
                    "payload": {"type": "object"},
                    "secret": {"type": "string"},
                    "method": {"type": "string"},
                },
            },
        ),
        Capability(
            name="ping",
            description="Probe a URL to check it is reachable.",
            params_schema={"required": ["url"], "properties": {"url": {"type": "string"}}},
        ),
    ]

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self.timeout)
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                limits=limits,
                headers=self.base_headers,
            )
        return self._client

    @staticmethod
    def _sign(payload: Any, secret: str) -> str:
        body = json.dumps(payload) if not isinstance(payload, str) else payload
        return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    async def validate_connection(self) -> bool:
        return True

    async def health(self) -> ProviderHealth:
        return ProviderHealth.healthy()

    async def refresh_token(self) -> bool:
        return False

    # ------------------------------------------------------------------ webhooks
    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        secret = settings.webhook_default_secret.get_secret_value()
        if not secret:
            return True
        import json as _json

        signature = headers.get("X-Webhook-Signature") or headers.get("X-AgentForge-Signature") or ""
        if not signature:
            return False
        expected = hmac.new(secret.encode(), _json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        provided = signature
        if provided.startswith("sha256="):
            provided = provided[len("sha256="):]
        return hmac.compare_digest(provided, expected)

    # ------------------------------------------------------------------ actions

    @action("send_webhook")
    async def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
        method: str = "POST",
        secret: str | None = None,
    ) -> dict[str, Any]:
        url = validate_target_url(url)
        if secret is None:
            secret = settings.webhook_default_secret.get_secret_value() or ""
        body = json.dumps(payload)
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest() if secret else ""
        req_headers: dict[str, str] = dict(headers or {})
        if signature:
            req_headers["X-AgentForge-Signature"] = f"sha256={signature}"
        resp = await self._request(
            method.upper(),
            url,
            json_data=payload,
            headers=req_headers,
            allowed_status=self.allowed_status,
        )
        if resp.status_code >= 400:
            await resp.aread()
            raise IntegrationError(
                f"webhook delivery failed: HTTP {resp.status_code}",
                provider=self.provider_key,
                details={"status_code": resp.status_code, "body": resp.text[:200]},
            )
        return {"delivered": True, "status_code": resp.status_code, "response": resp.text[:2000]}

    @action("send_signed_webhook")
    async def send_signed_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str,
        method: str = "POST",
    ) -> dict[str, Any]:
        url = validate_target_url(url)
        signature = self._sign(payload, secret)
        req_headers = {"X-Webhook-Signature": f"sha256={signature}"}
        resp = await self._request(
            method.upper(),
            url,
            json_data=payload,
            headers=req_headers,
            allowed_status=self.allowed_status,
        )
        if resp.status_code >= 400:
            await resp.aread()
            raise IntegrationError(
                f"webhook delivery failed: HTTP {resp.status_code}",
                provider=self.provider_key,
                details={"status_code": resp.status_code, "body": resp.text[:200]},
            )
        return {"delivered": True, "status_code": resp.status_code, "response": resp.text[:2000]}

    @action("ping")
    async def ping(self, url: str) -> dict[str, Any]:
        url = validate_target_url(url)
        try:
            resp = await self._request("GET", url, allowed_status=self.allowed_status, retry=False)
            return {"alive": resp.status_code < 400, "status_code": resp.status_code}
        except httpx.HTTPError:
            return {"alive": False, "status_code": None}
        except Exception:
            return {"alive": False, "status_code": None}


ProviderCls = WebhookProvider
provider = WebhookProvider()
