"""Shared FastAPI dependencies: auth, workspace resolution, rate limits."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import get_db
from exceptions import ForbiddenError, UnauthorizedError
from schemas import Principal
from security import decode_token, principal_from_claims
from utils.context import set_workspace_id

bearer_scheme = HTTPBearer(auto_error=False)


def _rate_limit_key(request: Request) -> str:
    """Default rate-limit key: the authenticated principal or client IP."""
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal:
        return principal.user_id
    client = request.client
    return client.host if client else "unknown"


def _admin_principal(principal: Principal) -> Principal:
    if "admin" not in principal.roles:
        raise ForbiddenError(
            "admin role required",
            details={"required_role": "admin", "user_id": principal.user_id},
        )
    return principal


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> Principal:
    """Resolve the authenticated principal from the Authorization header."""
    if credentials is None:
        raise UnauthorizedError("missing bearer token")
    claims = decode_token(credentials.credentials, expected_type="access")
    user_id, ws_id, roles = principal_from_claims(claims)
    principal = Principal(user_id=user_id, roles=roles, workspace_id=ws_id)
    if ws_id:
        set_workspace_id(ws_id)
    return principal


def require_workspace(principal: Principal = Depends(get_principal)) -> tuple[str, Principal]:
    """Return (workspace_id, principal), enforcing workspace presence."""
    if not principal.workspace_id:
        raise UnauthorizedError("workspace is required")
    return principal.workspace_id, principal


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    return _admin_principal(principal)


def get_traceparent(
    request: Request,
    traceparent_header: Annotated[str | None, Header(alias="traceparent")] = None,
) -> str | None:
    return traceparent_header


PrincipalDep = Annotated[Principal, Depends(get_principal)]
WorkspaceIdDep = Annotated[str, Depends(require_workspace)]
AdminDep = Annotated[Principal, Depends(require_admin)]
DBSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_redis_client() -> Redis:
    from services.redis_service import get_redis

    return await get_redis()


RedisDep = Annotated[Redis, Depends(get_redis_client)]


__all__ = [
    "AdminDep",
    "DBSessionDep",
    "PrincipalDep",
    "RedisDep",
    "WorkspaceIdDep",
    "bearer_scheme",
    "get_admin_rate_limit_key",
    "get_principal",
    "get_rate_limit_key",
    "get_redis_client",
    "require_admin",
    "require_workspace",
]


def get_rate_limit_key(request: Request) -> str:
    return _rate_limit_key(request)


def get_admin_rate_limit_key(request: Request) -> str:
    return _rate_limit_key(request)
