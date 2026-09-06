"""Twilio provider: SMS, WhatsApp, messages, calls, and OTP verification."""

from __future__ import annotations

import base64
from typing import Any

from config import settings
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.twilio.com/2010-04-01/Accounts"


class TwilioProvider(BaseIntegrationProvider):
    provider_key = "twilio"
    name = "Twilio"
    description = "Send SMS, WhatsApp messages, make calls, and verify OTP codes."
    auth_type = "api_key"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = True

    capabilities = [
        Capability(
            name="send_sms",
            description="Send an SMS message.",
            params_schema={
                "required": ["to", "body"],
                "properties": {
                    "to": {"type": "string"},
                    "body": {"type": "string"},
                    "from_": {"type": "string"},
                },
            },
        ),
        Capability(
            name="send_whatsapp",
            description="Send a WhatsApp message.",
            params_schema={
                "required": ["to", "body"],
                "properties": {
                    "to": {"type": "string"},
                    "body": {"type": "string"},
                    "from_": {"type": "string"},
                },
            },
        ),
        Capability(
            name="list_messages",
            description="List recent messages for the account.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="get_message",
            description="Fetch a message by SID.",
            params_schema={"required": ["message_sid"], "properties": {"message_sid": {"type": "string"}}},
        ),
        Capability(
            name="send_otp",
            description="Send a one-time password via SMS.",
            params_schema={
                "required": ["to"],
                "properties": {
                    "to": {"type": "string"},
                    "channel": {"type": "string"},
                    "verify_service_sid": {"type": "string"},
                },
            },
        ),
        Capability(
            name="verify_otp",
            description="Verify a one-time password.",
            params_schema={
                "required": ["to", "code"],
                "properties": {
                    "to": {"type": "string"},
                    "code": {"type": "string"},
                    "verify_service_sid": {"type": "string"},
                },
            },
        ),
        Capability(
            name="make_call",
            description="Make an outbound phone call.",
            params_schema={
                "required": ["to"],
                "properties": {
                    "to": {"type": "string"},
                    "from_": {"type": "string"},
                    "twiml": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        sid = self.context.credentials.get("account_sid", "") if self.context else ""
        token = self.context.credentials.get("auth_token", "") if self.context else ""
        token_bytes = base64.b64encode(f"{sid}:{token}".encode()).decode()
        return {"Authorization": f"Basic {token_bytes}"}

    def _account_sid(self) -> str:
        return self.context.credentials.get("account_sid", "") if self.context else ""

    def _services_url(self) -> str:
        return "https://api.twilio.com/2010-04-01"

    def _verify_url(self) -> str:
        return "https://verify.twilio.com/v2"

    async def validate_connection(self) -> bool:
        sid = self._account_sid()
        resp = await self._get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}")
        data = resp.json()
        return "status" in data

    async def health(self) -> ProviderHealth:
        try:
            sid = self._account_sid()
            resp = await self._get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}")
            data = resp.json()
            return ProviderHealth.healthy(detail={"status": data.get("status")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def refresh_token(self) -> bool:
        return False

    @action("send_sms")
    async def send_sms(
        self,
        to: str,
        body: str,
        from_: str | None = None,
    ) -> dict[str, Any]:
        sid = self._account_sid()
        sender = from_ or (self.context.credentials.get("phone_number", "") if self.context else "")
        data = {"To": to, "Body": body}
        if sender:
            data["From"] = sender
        resp = await self._post(
            f"{BASE_URL}/{sid}/Messages.json",
            data=data,
        )
        return resp.json()

    @action("send_whatsapp")
    async def send_whatsapp(
        self,
        to: str,
        body: str,
        from_: str | None = None,
    ) -> dict[str, Any]:
        sid = self._account_sid()
        sender = from_ or (self.context.credentials.get("phone_number", "") if self.context else "")
        data = {
            "To": f"whatsapp:{to}",
            "Body": body,
        }
        if sender:
            data["From"] = f"whatsapp:{sender}"
        resp = await self._post(
            f"{BASE_URL}/{sid}/Messages.json",
            data=data,
        )
        return resp.json()

    @action("list_messages")
    async def list_messages(self, limit: int = 20) -> dict[str, Any]:
        sid = self._account_sid()
        resp = await self._get(
            f"{BASE_URL}/{sid}/Messages.json",
            params={"limit": limit},
        )
        return resp.json()

    @action("get_message")
    async def get_message(self, message_sid: str) -> dict[str, Any]:
        sid = self._account_sid()
        resp = await self._get(f"{BASE_URL}/{sid}/Messages/{message_sid}.json")
        return resp.json()

    @action("send_otp")
    async def send_otp(
        self,
        to: str,
        channel: str = "sms",
        verify_service_sid: str | None = None,
    ) -> dict[str, Any]:
        service_sid = (
            verify_service_sid
            or (self.context.credentials.get("verify_service_sid", "") if self.context else "")
            or settings.twilio_verify_service_sid
        )
        resp = await self._post(
            f"{self._verify_url()}/Services/{service_sid}/Verifications",
            data={"To": to, "Channel": channel},
        )
        return resp.json()

    @action("verify_otp")
    async def verify_otp(
        self,
        to: str,
        code: str,
        verify_service_sid: str | None = None,
    ) -> dict[str, Any]:
        service_sid = (
            verify_service_sid
            or (self.context.credentials.get("verify_service_sid", "") if self.context else "")
            or settings.twilio_verify_service_sid
        )
        resp = await self._post(
            f"{self._verify_url()}/Services/{service_sid}/VerificationCheck",
            data={"To": to, "Code": code},
        )
        data = resp.json()
        return {"valid": data.get("status") == "approved"}

    @action("make_call")
    async def make_call(
        self,
        to: str,
        from_: str | None = None,
        twiml: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        sid = self._account_sid()
        sender = from_ or (self.context.credentials.get("phone_number", "") if self.context else "")
        data: dict[str, Any] = {"To": to}
        if sender:
            data["From"] = sender
        if twiml:
            data["Twiml"] = twiml
        if url:
            data["Url"] = url
        resp = await self._post(
            f"{BASE_URL}/{sid}/Calls.json",
            data=data,
        )
        return resp.json()

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac
        import json

        from config import settings

        signature = headers.get("X-Twilio-Signature", "")
        if not signature:
            return False

        auth_token = settings.twilio_auth_token.get_secret_value()
        body = json.dumps(payload)
        expected = hmac.new(
            auth_token.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


ProviderCls = TwilioProvider
provider = TwilioProvider()
