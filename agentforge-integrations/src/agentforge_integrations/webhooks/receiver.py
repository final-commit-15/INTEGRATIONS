import logging

from fastapi import FastAPI, HTTPException, Request, status

from ..auth.credentials import CredentialManager
from ..core.manager import IntegrationManager
from .dispatcher import WebhookDispatcher
from .validator import validate_signature

logger = logging.getLogger(__name__)

app = FastAPI(title="AgentForge Integration Webhook Receiver")

credential_manager = CredentialManager()
integration_manager = IntegrationManager(credential_manager)
webhook_dispatcher = WebhookDispatcher(integration_manager)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/webhooks/{integration_name}")
async def webhook_receiver(integration_name: str, request: Request):
    """
    Generic webhook endpoint.

    Validates the webhook signature and dispatches the event
    through the shared WebhookDispatcher.
    """
    body = await request.body()
    headers = dict(request.headers)

    if not validate_signature(integration_name, body, headers):
        logger.warning(
            "Invalid webhook signature for %s",
            integration_name,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    try:
        await webhook_dispatcher.dispatch(
            integration_name,
            body,
            headers,
        )
    except Exception:
        logger.exception(
            "Webhook dispatch error for %s",
            integration_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )

    return {"status": "ok"}