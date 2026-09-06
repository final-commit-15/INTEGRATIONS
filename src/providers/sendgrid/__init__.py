"""SendGrid provider: send transactional email and manage templates via the SendGrid API."""

from __future__ import annotations

from typing import Any

from exceptions import IntegrationError
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)


class SendGridProvider(BaseIntegrationProvider):
    provider_key = "sendgrid"
    name = "SendGrid"
    description = "Send transactional email and manage templates via the SendGrid API."
    auth_type = "api_key"
    base_url = "https://api.sendgrid.com/v3"
    timeout = 30.0
    supports_webhooks = True

    capabilities = [
        Capability(
            name="send_email",
            description="Send a plaintext or HTML email.",
            params_schema={
                "required": ["to", "subject"],
                "properties": {
                    "to": {"type": ["string", "array"]},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "html": {"type": "string"},
                    "from_email": {"type": "string"},
                    "from_name": {"type": "string"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
        Capability(
            name="list_templates",
            description="List transactional templates.",
            params_schema={"properties": {"page_size": {"type": "integer", "default": 20}}},
        ),
        Capability(
            name="get_template",
            description="Fetch a single template by id.",
            params_schema={"required": ["template_id"], "properties": {"template_id": {"type": "string"}}},
        ),
        Capability(
            name="send_template_email",
            description="Send an email using a dynamic transactional template.",
            params_schema={
                "required": ["to", "template_id"],
                "properties": {
                    "to": {"type": ["string", "array"]},
                    "template_id": {"type": "string"},
                    "dynamic_data": {"type": "object"},
                    "from_email": {"type": "string"},
                },
            },
        ),
        Capability(
            name="list_suppression_blocks",
            description="List emails currently blocked by SendGrid suppression.",
            params_schema={"properties": {"limit": {"type": "integer", "default": 10}}},
        ),
        Capability(
            name="list_api_keys",
            description="List API keys in the account.",
            params_schema={"properties": {"limit": {"type": "integer", "default": 10}}},
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        api_key = ""
        if self.context:
            api_key = self.context.credentials.get("api_key", "")
        if not api_key:
            api_key = _api_key()
        return {"Authorization": f"Bearer {api_key}"}

    async def validate_connection(self) -> bool:
        resp = await self._get("/user/profile", retry=False)
        return resp.status_code == 200

    async def health(self) -> ProviderHealth:
        try:
            valid = await self.validate_connection()
            if valid:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "GET /user/profile did not return 200"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    def _require_api_key(self) -> str:
        if self.context:
            api_key = self.context.credentials.get("api_key", "")
            if api_key:
                return api_key
        from config import settings

        if settings.sendgrid_api_key and settings.sendgrid_api_key.get_secret_value():
            return settings.sendgrid_api_key.get_secret_value()
        raise IntegrationError(
            "sendgrid api_key is not configured",
            provider=self.provider_key,
        )

    async def refresh_token(self) -> bool:
        return False

    @action("send_email")
    async def send_email(
        self,
        to: str | list[str],
        subject: str,
        body: str | None = None,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict[str, Any]:
        sender_email = from_email or self._default_from_email()
        payload = {
            "personalizations": [_personalization(to, cc=cc, bcc=bcc)],
            "from": {"email": sender_email, "name": from_name} if from_name else {"email": sender_email},
            "subject": subject,
            "content": _content(body=body, html=html),
        }
        resp = await self._post("/mail/send", json_data=payload)
        message_id = resp.headers.get("X-Message-Id") if hasattr(resp, "headers") else None
        return {"success": True, "message_id": message_id}

    @action("list_templates")
    async def list_templates(self, page_size: int = 20) -> dict[str, Any]:
        resp = await self._get("/templates", params={"page_size": page_size})
        return resp.json()

    @action("get_template")
    async def get_template(self, template_id: str) -> dict[str, Any]:
        resp = await self._get(f"/templates/{template_id}")
        return resp.json()

    @action("send_template_email")
    async def send_template_email(
        self,
        to: str | list[str],
        template_id: str,
        dynamic_data: dict[str, Any] | None = None,
        from_email: str | None = None,
    ) -> dict[str, Any]:
        sender_email = from_email or self._default_from_email()
        recipients = [to] if isinstance(to, str) else list(to)
        personalization: dict[str, Any] = {
            "to": [{"email": r} for r in recipients],
            "dynamic_template_data": dynamic_data or {},
        }
        payload = {
            "personalizations": [personalization],
            "from": {"email": sender_email},
            "template_id": template_id,
        }
        resp = await self._post("/mail/send", json_data=payload)
        message_id = resp.headers.get("X-Message-Id") if hasattr(resp, "headers") else None
        return {"success": True, "message_id": message_id}

    @action("list_suppression_blocks")
    async def list_suppression_blocks(self, limit: int = 10) -> dict[str, Any]:
        resp = await self._get("/suppression/blocks", params={"limit": limit})
        return resp.json()

    @action("list_api_keys")
    async def list_api_keys(self, limit: int = 10) -> dict[str, Any]:
        resp = await self._get("/api_keys", params={"limit": limit})
        return resp.json()

    def _default_from_email(self) -> str:
        if self.context:
            from_email = self.context.credentials.get("from_email", "")
            if from_email:
                return from_email
        from config import settings

        return settings.sendgrid_from_email or "noreply@agentforge.ai"

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac

        from config import settings

        api_key = settings.sendgrid_api_key.get_secret_value() if settings.sendgrid_api_key else ""
        signature = headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        timestamp = headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")
        body = payload.get("raw_body", "")
        if not signature and not api_key:
            return True
        if not signature or not timestamp or not api_key:
            return False
        computed = hmac.new(
            api_key.encode(),
            f"{timestamp}{body}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, signature)


def _personalization(
    to: str | list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict[str, Any]:
    recipients = [to] if isinstance(to, str) else list(to)
    personalization: dict[str, Any] = {"to": [{"email": r} for r in recipients]}
    if cc:
        personalization["cc"] = [{"email": r} for r in (cc if isinstance(cc, list) else [cc])]
    if bcc:
        personalization["bcc"] = [{"email": r} for r in (bcc if isinstance(bcc, list) else [bcc])]
    return personalization


def _content(body: str | None = None, html: str | None = None) -> list[dict[str, str]]:
    if html:
        return [{"type": "text/html", "value": html}]
    return [{"type": "text/plain", "value": body or ""}]


def _api_key() -> str:
    from config import settings

    return settings.sendgrid_api_key.get_secret_value() if settings.sendgrid_api_key else ""


ProviderCls = SendGridProvider
provider = SendGridProvider()
