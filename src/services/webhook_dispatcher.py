"""Webhook verification and dispatch engine.

Handles inbound provider webhooks (signature verification + deduplication +
persistence) and outbound delivery to registered subscriber URLs with retry,
exponential backoff, and dead-letter accounting.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from exceptions import WebhookVerificationFailed
from models import WebhookDelivery, WebhookEvent, WebhookSubscription
from providers.registry import get_registry
from services.redis_service import WebhookDedup
from telemetry import metrics
from utils.security import validate_target_url


class WebhookDispatcher:
    """Verifies inbound events and dispatches outbound deliveries."""

    def __init__(self) -> None:
        self.dedup = WebhookDedup()

    # ------------------------------------------------------------------
    # Inbound verification & persistence
    # ------------------------------------------------------------------

    async def verify_and_store(
        self,
        *,
        provider: str,
        workspace_id: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        session: AsyncSession,
    ) -> WebhookEvent:
        """Verify signature, dedupe, persist, and return the event."""
        provider_cls = get_registry().get(provider)
        if not provider_cls.supports_webhooks:
            raise WebhookVerificationFailed(
                f"provider {provider} does not accept webhooks", provider=provider
            )

        self._assert_signature(provider_cls, headers, payload)
        event_type = (payload.get("type") or payload.get("event") or payload.get("action") or None)

        dedup_key = self._dedup_key(provider, headers, event_type, payload)
        if dedup_key and await self.dedup.seen(dedup_key):
            metrics.inc_webhook_received(provider)
            raise WebhookVerificationFailed(
                "duplicate webhook event", provider=provider, details={"dedup_key": dedup_key}
            )

        event = WebhookEvent(
            workspace_id=workspace_id,
            provider=provider,
            event_type=event_type,
            dedup_key=dedup_key,
            raw_payload=payload,
            headers={k: v for k, v in headers.items() if k.lower() not in {"authorization", "cookie", "x-hub-signature"}},
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        metrics.inc_webhook_received(provider)
        return event

    def _assert_signature(self, provider_cls: Any, headers: dict[str, str], payload: dict[str, Any]) -> None:
        verify = provider_cls.verify_signature  # type: ignore[attr-defined]
        if verify is None:
            return
        valid = verify(headers, payload)
        if not valid:
            raise WebhookVerificationFailed(
                "webhook signature verification failed", provider=provider_cls.provider_key
            )

    def _dedup_key(
        self, provider: str, headers: dict[str, str], event_type: str | None, payload: dict[str, Any]
    ) -> str | None:
        candidates = [
            headers.get("X-Hub-Zoom-Event-Id") or headers.get("x-github-event-id")
            or headers.get("X-Request-Id") or headers.get("X-Stripe-Trace-Id")
            or headers.get("x-twilio-signature-ts"),
        ]
        for candidate in candidates:
            if candidate:
                return f"{provider}:{candidate}"
        if event_type and payload.get("id"):
            return f"{provider}:{event_type}:{payload.get('id')}"
        return None

    # ------------------------------------------------------------------
    # Outbound delivery
    # ------------------------------------------------------------------

    async def dispatch_event(
        self,
        *,
        event: WebhookEvent,
        session: AsyncSession,
    ) -> list[WebhookDelivery]:
        """Deliver an inbound event to all matching active subscriptions."""
        result = await session.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.workspace_id == event.workspace_id,
                WebhookSubscription.provider == event.provider,
                WebhookSubscription.is_active.is_(True),
            )
        )
        subscriptions = list(result.scalars().all())
        if not subscriptions:
            event.delivery_status = "no_subscribers"
            await session.commit()
            return []

        deliveries: list[WebhookDelivery] = []
        for subscription in subscriptions:
            deliveries.append(
                await self.deliver_to_subscription(
                    subscription=subscription, event=event, session=session
                )
            )
        return deliveries

    async def deliver_to_subscription(
        self,
        *,
        subscription: WebhookSubscription,
        event: WebhookEvent,
        session: AsyncSession,
    ) -> WebhookDelivery:
        """Perform a single delivery attempt with HMAC signing."""
        await session.refresh(event)
        target = validate_target_url(subscription.target_url)
        secret = subscription.secret or settings.webhook_default_secret.get_secret_value()
        body = json.dumps(
            {
                "id": event.id,
                "type": event.event_type,
                "provider": event.provider,
                "workspace_id": event.workspace_id,
                "timestamp": event.created_at.isoformat(),
                "data": event.raw_payload,
            },
            default=str,
        )

        attempts = event.attempts
        delivery = WebhookDelivery(
            event_id=event.id,
            subscription_id=subscription.id,
            attempt=attempts + 1,
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    target,
                    content=body,
                    headers=self._sign_headers(body, secret, subscription),
                )
            delivery.status_code = response.status_code
            delivery.response_body = (response.text or "")[:2000]
            delivery.success = response.status_code < 400
        except httpx.HTTPError as exc:
            delivery.response_body = str(exc)[:2000]
            delivery.success = False

        event.attempts = attempts + 1
        if delivery.success:
            event.delivery_status = "delivered"
            event.delivered_at = datetime.now(UTC)
            metrics.inc_webhook_delivered(event.provider, True)
        else:
            event.delivery_status = "failed"
            metrics.inc_webhook_delivered(event.provider, False)
            metrics.inc_webhook_retry(event.provider)

        session.add(delivery)
        await session.commit()
        return delivery

    def _sign_headers(
        self, body: str, secret: str, subscription: WebhookSubscription
    ) -> dict[str, str]:
        digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-AgentForge-Signature": f"sha256={digest}",
            "X-AgentForge-Event": subscription.provider,
            "X-AgentForge-Hook-Id": subscription.id,
        }

    # ------------------------------------------------------------------
    # Retry / dead-letter
    # ------------------------------------------------------------------

    async def retry_failed(self, *, session: AsyncSession, limit: int = 100) -> int:
        """Re-dispatch failed events that are still within their retry budget."""
        result = await session.execute(
            select(WebhookEvent)
            .where(
                WebhookEvent.delivery_status == "failed",
                WebhookEvent.attempts < settings.webhook_retry_max,
            )
            .limit(limit)
        )
        events = list(result.scalars().all())
        for event in events:
            await self.dispatch_event(event=event, session=session)
        return len(events)

    async def dead_letter_overflow(self, *, session: AsyncSession, limit: int = 50) -> list[WebhookEvent]:
        """Mark events exceeding retry budget as dead-lettered."""
        result = await session.execute(
            select(WebhookEvent)
            .where(
                WebhookEvent.delivery_status == "failed",
                WebhookEvent.attempts >= settings.webhook_retry_max,
            )
            .limit(limit)
        )
        events = list(result.scalars().all())
        for event in events:
            event.delivery_status = "dead_lettered"
        await session.commit()
        return events


def default_webhook_secret() -> str:
    if settings.webhook_default_secret.get_secret_value():
        return settings.webhook_default_secret.get_secret_value()
    return secrets.token_urlsafe(32)


dispatcher = WebhookDispatcher()


def get_dispatcher() -> WebhookDispatcher:
    return dispatcher
