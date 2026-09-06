"""Stripe provider: customers, charges, payment intents, refunds, and events."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.stripe.com"


class StripeProvider(BaseIntegrationProvider):
    provider_key = "stripe"
    name = "Stripe"
    description = "Manage Stripe customers, charges, payment intents, refunds, and events."
    auth_type = "api_key"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = True

    capabilities = [
        Capability(
            name="list_customers",
            description="List Stripe customers.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="create_customer",
            description="Create a new customer.",
            params_schema={
                "properties": {
                    "email": {"type": "string"},
                    "name": {"type": "string"},
                    "metadata": {"type": "object"},
                    "description": {"type": "string"},
                },
            },
        ),
        Capability(
            name="get_customer",
            description="Fetch a customer by id.",
            params_schema={"required": ["customer_id"], "properties": {"customer_id": {"type": "string"}}},
        ),
        Capability(
            name="update_customer",
            description="Update a customer.",
            params_schema={"required": ["customer_id"], "properties": {"customer_id": {"type": "string"}}},
        ),
        Capability(
            name="list_charges",
            description="List Stripe charges.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="create_charge",
            description="Create a charge.",
            params_schema={
                "required": ["amount"],
                "properties": {
                    "amount": {"type": "integer"},
                    "currency": {"type": "string"},
                    "source": {"type": "string"},
                    "description": {"type": "string"},
                    "customer": {"type": "string"},
                },
            },
        ),
        Capability(
            name="create_payment_intent",
            description="Create a PaymentIntent.",
            params_schema={
                "required": ["amount"],
                "properties": {
                    "amount": {"type": "integer"},
                    "currency": {"type": "string"},
                    "payment_method_types": {"type": "array"},
                    "metadata": {"type": "object"},
                },
            },
        ),
        Capability(
            name="confirm_payment_intent",
            description="Confirm a PaymentIntent.",
            params_schema={
                "required": ["payment_intent_id"],
                "properties": {
                    "payment_intent_id": {"type": "string"},
                    "payment_method": {"type": "string"},
                },
            },
        ),
        Capability(
            name="create_refund",
            description="Create a refund for a charge.",
            params_schema={
                "required": ["charge_id"],
                "properties": {
                    "charge_id": {"type": "string"},
                    "amount": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="list_events",
            description="List Stripe events.",
            params_schema={"properties": {"limit": {"type": "integer"}}},
        ),
        Capability(
            name="get_event",
            description="Fetch a Stripe event by id.",
            params_schema={"required": ["event_id"], "properties": {"event_id": {"type": "string"}}},
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        secret_key = self.context.credentials.get("secret_key", "") if self.context else ""
        return {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def validate_connection(self) -> bool:
        resp = await self._get("/v1/balance")
        return resp.status_code == 200

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/v1/balance")
            if resp.status_code == 200:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "balance returned non-200"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def refresh_token(self) -> bool:
        return False

    @action("list_customers")
    async def list_customers(self, limit: int = 10) -> dict[str, Any]:
        resp = await self._get("/v1/customers", params={"limit": str(limit)})
        return resp.json()

    @action("create_customer")
    async def create_customer(
        self,
        email: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if email:
            data["email"] = email
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = str(v)
        resp = await self._post("/v1/customers", data=data)
        return resp.json()

    @action("get_customer")
    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        resp = await self._get(f"/v1/customers/{customer_id}")
        return resp.json()

    @action("update_customer")
    async def update_customer(self, customer_id: str, **changes: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in changes.items():
            data[key] = str(value)
        resp = await self._post(f"/v1/customers/{customer_id}", data=data)
        return resp.json()

    @action("list_charges")
    async def list_charges(self, limit: int = 10) -> dict[str, Any]:
        resp = await self._get("/v1/charges", params={"limit": str(limit)})
        return resp.json()

    @action("create_charge")
    async def create_charge(
        self,
        amount: int,
        currency: str = "usd",
        source: str | None = None,
        description: str | None = None,
        customer: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"amount": str(amount), "currency": currency}
        if source:
            data["source"] = source
        if description:
            data["description"] = description
        if customer:
            data["customer"] = customer
        resp = await self._post("/v1/charges", data=data)
        return resp.json()

    @action("create_payment_intent")
    async def create_payment_intent(
        self,
        amount: int,
        currency: str = "usd",
        payment_method_types: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"amount": str(amount), "currency": currency}
        if payment_method_types:
            for pmt in payment_method_types:
                data.setdefault("payment_method_types[]", []).append(pmt)
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = str(v)
        resp = await self._post("/v1/payment_intents", data=data)
        return resp.json()

    @action("confirm_payment_intent")
    async def confirm_payment_intent(
        self,
        payment_intent_id: str,
        payment_method: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if payment_method:
            data["payment_method"] = payment_method
        resp = await self._post(f"/v1/payment_intents/{payment_intent_id}/confirm", data=data)
        return resp.json()

    @action("create_refund")
    async def create_refund(
        self,
        charge_id: str,
        amount: int | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"charge": charge_id}
        if amount is not None:
            data["amount"] = str(amount)
        resp = await self._post("/v1/refunds", data=data)
        return resp.json()

    @action("list_events")
    async def list_events(self, limit: int = 10) -> dict[str, Any]:
        resp = await self._get("/v1/events", params={"limit": str(limit)})
        return resp.json()

    @action("get_event")
    async def get_event(self, event_id: str) -> dict[str, Any]:
        resp = await self._get(f"/v1/events/{event_id}")
        return resp.json()

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac
        import json

        from config import settings

        secret = settings.stripe_webhook_secret.get_secret_value()
        if not secret:
            return True

        signature = headers.get("Stripe-Signature", "")
        if not signature:
            return False

        timestamp = ""
        provided = ""
        for part in signature.split(","):
            if part.startswith("t="):
                timestamp = part[2:]
            elif part.startswith("v1="):
                provided = part[3:]

        if not timestamp or not provided:
            return False

        body = json.dumps(payload)
        expected = hmac.new(
            secret.encode(),
            f"{timestamp}.{body}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, provided)


ProviderCls = StripeProvider
provider = StripeProvider()
