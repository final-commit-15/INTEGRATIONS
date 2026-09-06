"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class ComponentHealth(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down"]
    latency_ms: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    uptime_seconds: float
    components: list[ComponentHealth] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Generic API wrapper
# ---------------------------------------------------------------------------


class ApiResponse(BaseModel, Generic[T]):
    data: T
    message: str | None = None
    request_id: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    provider: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Workspace & auth context
# ---------------------------------------------------------------------------


class Principal(BaseModel):
    user_id: str
    roles: list[str] = Field(default_factory=list)
    workspace_id: str | None = None


class WorkspaceOut(ORMModel):
    id: str
    name: str
    owner_id: str | None = None
    is_active: bool


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: HttpUrl
    state: str
    provider: str
    expires_in_seconds: int


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthConnectResult(BaseModel):
    provider: str
    workspace_id: str
    connected: bool
    scopes: list[str]
    expires_at: datetime | None = None


class OAuthProviderInfo(BaseModel):
    key: str
    name: str
    description: str
    auth_type: str
    oauth_supported: bool
    capabilities: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


class CapabilityOut(BaseModel):
    name: str
    description: str
    params_schema: dict[str, Any] = Field(default_factory=dict)


class IntegrationConnectionOut(ORMModel):
    id: str
    workspace_id: str
    provider: str
    status: str
    scopes: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    expires_at: datetime | None = None


class ExecuteActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    provider_connection_id: str | None = None


class ExecuteActionResult(BaseModel):
    provider: str
    action: str
    success: bool
    data: Any = None
    latency_ms: float | None = None


class ValidateConnectionResult(BaseModel):
    provider: str
    valid: bool
    checks: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


class CredentialCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    name: str = Field(default="default", max_length=128)
    credentials: dict[str, Any] = Field(...)


class CredentialUpdate(BaseModel):
    credentials: dict[str, Any] = Field(...)


class CredentialOut(BaseModel):
    provider: str
    name: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    masked_fields: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


class WebhookRegisterRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    target_url: HttpUrl
    secret: SecretStr | None = None
    events: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=5, ge=0, le=20)


class WebhookSubscriptionOut(ORMModel):
    id: str
    workspace_id: str
    provider: str
    target_url: str
    events: list[str]
    is_active: bool
    max_retries: int


class WebhookEventOut(ORMModel):
    id: str
    workspace_id: str
    provider: str
    event_type: str | None = None
    delivery_status: str
    attempts: int
    created_at: datetime


class WebhookDispatchRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    events: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class AdminIntegrationRow(BaseModel):
    id: str
    workspace_id: str
    provider: str
    status: str
    created_at: datetime
    updated_at: datetime


class AdminWebhookRow(BaseModel):
    id: str
    workspace_id: str
    provider: str
    target_url: str
    is_active: bool


class AdminAuditRow(ORMModel):
    id: str
    workspace_id: str
    actor_id: str | None = None
    provider: str | None = None
    action: str
    outcome: str
    created_at: datetime


class PaginatedResult(BaseModel, Generic[T]):
    items: list[T]
    total: int = 0
