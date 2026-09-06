"""Credential management service: create, list, update, delete credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from exceptions import CredentialInvalid, CredentialNotFound
from models import Credential
from schemas import CredentialCreate, CredentialUpdate
from services.encryption_service import EncryptionService, get_encryption_service
from utils.security import hash_credential


class CredentialService:
    """Encryption-aware credential CRUD scoped to a workspace."""

    def __init__(self, encryption: EncryptionService | None = None) -> None:
        self.encryption = encryption or get_encryption_service()

    @staticmethod
    def _hash(credentials: dict[str, Any]) -> str:
        salt = settings.credential_hash_salt.get_secret_value().strip() or "agentforge"
        canonical = "|".join(f"{k}:{v}" for k, v in sorted(credentials.items()))
        return hash_credential(canonical, salt)

    async def create(
        self,
        *,
        workspace_id: str,
        provider: str,
        data: CredentialCreate,
        session: AsyncSession,
    ) -> Credential:
        if not data.credentials:
            raise CredentialInvalid("credentials cannot be empty", provider=provider)
        expires_at = data.credentials.pop("expires_at", None)
        encrypted = self.encryption.encrypt_credentials(data.credentials)
        record = Credential(
            workspace_id=workspace_id,
            provider=provider,
            name=data.name,
            encrypted_blob=encrypted,
            credential_hash=self._hash(data.credentials),
            expires_at=_parse_expiry(expires_at),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def get(self, *, workspace_id: str, provider: str, session: AsyncSession) -> Credential:
        result = await session.execute(
            select(Credential).where(
                Credential.workspace_id == workspace_id,
                Credential.provider == provider,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise CredentialNotFound(f"no credentials for provider {provider!r}")
        return record

    async def list(self, *, workspace_id: str, session: AsyncSession) -> list[Credential]:
        result = await session.execute(
            select(Credential)
            .where(Credential.workspace_id == workspace_id)
            .order_by(Credential.created_at.desc())
        )
        return list(result.scalars().all())

    async def decrypt_for(self, *, workspace_id: str, provider: str, session: AsyncSession) -> dict[str, Any]:
        record = await self.get(workspace_id=workspace_id, provider=provider, session=session)
        return self.encryption.decrypt_credentials(record.encrypted_blob)

    async def update(
        self,
        *,
        workspace_id: str,
        provider: str,
        data: CredentialUpdate,
        session: AsyncSession,
    ) -> Credential:
        record = await self.get(workspace_id=workspace_id, provider=provider, session=session)
        if not data.credentials:
            raise CredentialInvalid("credentials cannot be empty", provider=provider)
        expires_at = data.credentials.pop("expires_at", None)
        record.encrypted_blob = self.encryption.encrypt_credentials(data.credentials)
        record.credential_hash = self._hash(data.credentials)
        record.expires_at = _parse_expiry(expires_at)
        await session.commit()
        await session.refresh(record)
        return record

    async def delete(self, *, workspace_id: str, provider: str, session: AsyncSession) -> None:
        record = await self.get(workspace_id=workspace_id, provider=provider, session=session)
        await session.delete(record)
        await session.commit()

    async def rotate_expired(
        self, *, session: AsyncSession, now: datetime | None = None
    ) -> list[str]:
        """Flag credentials that are expired or unreadable. Returns affected ids."""
        now = now or datetime.now(UTC)
        result = await session.execute(
            select(Credential).where(
                Credential.expires_at.is_not(None),
                Credential.expires_at < now,
            )
        )
        affected: list[str] = []
        for record in result.scalars().all():
            record.expires_at = None  # allow re-auth flow to rewrite
            affected.append(record.id)
        await session.commit()
        return affected


def _parse_expiry(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, str):
        from datetime import datetime as dt

        try:
            parsed = dt.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC)
        except ValueError:
            return None
    return None


credential_service: CredentialService | None = None


def get_credential_service() -> CredentialService:
    global credential_service
    if credential_service is None:
        credential_service = CredentialService()
    return credential_service
