"""Webhook receive, register, and event-listing endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from dependencies import PrincipalDep
from exceptions import WebhookVerificationFailed
from models import WebhookEvent, WebhookSubscription
from schemas import (
    ApiResponse,
    PaginatedResult,
    WebhookEventOut,
    WebhookRegisterRequest,
    WebhookSubscriptionOut,
)
from services.audit_service import get_audit_service
from services.webhook_dispatcher import default_webhook_secret, get_dispatcher

router = APIRouter()


@router.post("/{provider}", name="webhook_receive")
async def receive_webhook(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    raw_body: bytes | None = None,
) -> dict[str, Any]:
    """Receive an inbound webhook event from a provider.

    The body is read raw to allow signature verification over the exact bytes.
    ``X-Workspace-Id`` header selects the owning workspace.
    """
    body = await request.body()
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise WebhookVerificationFailed("invalid JSON webhook payload", provider=provider) from exc

    workspace_id = request.headers.get("X-Workspace-Id")
    if not workspace_id:
        raise WebhookVerificationFailed("missing X-Workspace-Id header", provider=provider)

    headers = {k: v for k, v in request.headers.items()}
    event = await get_dispatcher().verify_and_store(
        provider=provider,
        workspace_id=workspace_id,
        headers=headers,
        payload=payload,
        session=session,
    )
    await get_dispatcher().dispatch_event(event=event, session=session)
    return {"status": "accepted", "event_id": event.id}


@router.get("/events", response_model=ApiResponse[PaginatedResult[WebhookEventOut]])
async def list_events(
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
    provider: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ApiResponse[PaginatedResult[WebhookEventOut]]:
    """List persisted webhook events for the caller's workspace."""
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise WebhookVerificationFailed("workspace required")
    query = select(WebhookEvent).where(WebhookEvent.workspace_id == workspace_id)
    if provider:
        query = query.where(WebhookEvent.provider == provider)
    from sqlalchemy import func

    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()
    events_result = await session.execute(
        query.order_by(WebhookEvent.created_at.desc()).offset(offset).limit(limit)
    )
    events = list(events_result.scalars().all())
    return ApiResponse(
        data=PaginatedResult(
            items=[WebhookEventOut.model_validate(e) for e in events],
            total=total,
        )
    )


@router.post("/register", response_model=ApiResponse[WebhookSubscriptionOut])
async def register_webhook(
    request: Request,
    payload: WebhookRegisterRequest,
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[WebhookSubscriptionOut]:
    """Register a subscriber URL to receive verified events for a provider."""
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise WebhookVerificationFailed("workspace required")
    secret_value = payload.secret.get_secret_value() if payload.secret else default_webhook_secret()
    subscription = WebhookSubscription(
        workspace_id=workspace_id,
        provider=payload.provider,
        target_url=str(payload.target_url),
        secret=secret_value,
        events=payload.events,
        metadata_json=payload.metadata,
        max_retries=payload.max_retries,
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)
    await get_audit_service().record(
        session=session,
        workspace_id=workspace_id,
        actor_id=principal.user_id,
        action="webhook.register",
        provider=payload.provider,
        resource=subscription.id,
        ip_address=request.client.host if request.client else None,
    )
    return ApiResponse(data=WebhookSubscriptionOut.model_validate(subscription))


@router.get("/subscriptions", response_model=ApiResponse[list[WebhookSubscriptionOut]])
async def list_subscriptions(
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[WebhookSubscriptionOut]]:
    workspace_id = principal.workspace_id
    if not workspace_id:
        raise WebhookVerificationFailed("workspace required")
    result = await session.execute(
        select(WebhookSubscription).where(WebhookSubscription.workspace_id == workspace_id)
    )
    subs = list(result.scalars().all())
    return ApiResponse(data=[WebhookSubscriptionOut.model_validate(s) for s in subs])


@router.delete("/{webhook_id}", response_model=ApiResponse[dict])
async def delete_webhook(
    webhook_id: str,
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Deactivate a webhook subscription."""
    workspace_id = principal.workspace_id
    result = await session.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.workspace_id == workspace_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise WebhookVerificationFailed("webhook subscription not found")
    subscription.is_active = False
    await session.commit()
    return ApiResponse(data={"id": webhook_id, "deleted": True})


@router.post("/dispatch/{event_id}", response_model=ApiResponse[dict])
async def redispatch_event(
    event_id: str,
    principal: PrincipalDep,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Manually re-dispatch a persisted event to its subscribers."""
    result = await session.execute(
        select(WebhookEvent).where(
            WebhookEvent.id == event_id,
            WebhookEvent.workspace_id == principal.workspace_id,
        )
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise WebhookVerificationFailed("event not found")
    deliveries = await get_dispatcher().dispatch_event(event=event, session=session)
    return ApiResponse(data={"event_id": event_id, "deliveries": len(deliveries)})
