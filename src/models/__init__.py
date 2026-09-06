"""SQLAlchemy ORM models.

Every table carries workspace_id for multi-tenant isolation, timestamps, and
soft-delete where appropriate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Workspace(Base, TimestampMixin):
    """A tenant workspace. Workspaces own integrations, credentials, and webhooks."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    connections: Mapped[list[IntegrationConnection]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    credentials: Mapped[list[Credential]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    webhook_subscriptions: Mapped[list[WebhookSubscription]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class IntegrationConnection(Base, TimestampMixin):
    """A connection between a workspace and an external provider."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_workspace_provider"),
        Index("ix_connections_workspace_provider", "workspace_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="connected", nullable=False)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="connections")


class Credential(Base, TimestampMixin):
    """Encrypted credentials for a workspace + provider.

    ``encrypted_blob`` holds the Fernet-encrypted JSON payload. The credential
    hash enables fast lookup without decrypting every row.
    """

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", "name", name="uq_ws_provider_name"),
        Index("ix_credentials_hash", "credential_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="default", nullable=False)
    encrypted_blob: Mapped[str] = mapped_column(Text, nullable=False)
    credential_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="credentials")


class OAuthState(Base, TimestampMixin):
    """One-time OAuth state tokens with workspace + provider context and PKCE verifier."""

    __tablename__ = "oauth_states"
    __table_args__ = (Index("ix_oauth_state_token", "state_token", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    state_token: Mapped[str] = mapped_column(String(128), nullable=False)
    code_verifier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    redirect_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WebhookSubscription(Base, TimestampMixin):
    """A registered webhook target that receives verified events."""

    __tablename__ = "webhook_subscriptions"
    __table_args__ = (Index("ix_webhook_sub_ws_provider", "workspace_id", "provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    events: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="webhook_subscriptions")


class WebhookEvent(Base, TimestampMixin):
    """An inbound event received from a provider, persisted for replay/audit."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        Index("ix_webhook_events_ws_provider_ts", "workspace_id", "provider", "created_at"),
        Index("ix_webhook_events_dedup", "dedup_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    headers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WebhookDelivery(Base, TimestampMixin):
    """Outbound delivery attempt record for a dispatched event."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_delivery_event", "event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class IntegrationAuditLog(Base, TimestampMixin):
    """Immutable audit trail for security-sensitive integration events."""

    __tablename__ = "integration_audit_logs"
    __table_args__ = (
        Index("ix_audit_ws_ts", "workspace_id", "created_at"),
        Index("ix_audit_actor", "actor_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
