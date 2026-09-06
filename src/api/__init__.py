"""/api package with FastAPI routers."""

from fastapi import APIRouter

from api import admin, auth, credentials, health, integrations, webhooks

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(credentials.router, prefix="/credentials", tags=["credentials"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

__all__ = ["api_router"]
