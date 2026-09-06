"""JWT authentication, token minting, and principal extraction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt

from config import settings
from exceptions import UnauthorizedError

TokenType = Literal["access", "refresh"]


def _secret() -> str:
    return settings.jwt_secret.get_secret_value()


def create_access_token(
    *,
    subject: str,
    workspace_id: str | None = None,
    roles: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return _mint_token(
        token_type="access",
        subject=subject,
        workspace_id=workspace_id,
        roles=roles,
        expires=expires,
        extra_claims=extra_claims,
    )


def create_refresh_token(*, subject: str) -> str:
    expires = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    return _mint_token(token_type="refresh", subject=subject, expires=expires)


def _mint_token(
    *,
    token_type: TokenType,
    subject: str,
    expires: datetime,
    workspace_id: str | None = None,
    roles: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    claims: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": datetime.now(UTC),
        "exp": expires,
        "iss": settings.app_name,
        "aud": settings.app_name,
    }
    if workspace_id:
        claims["ws"] = workspace_id
    if roles:
        claims["roles"] = roles
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, _secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a JWT. Raises UnauthorizedError on any failure."""
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.app_name,
            issuer=settings.app_name,
        )
    except JWTError as exc:
        raise UnauthorizedError("invalid or expired token") from exc
    if expected_type and claims.get("type") != expected_type:
        raise UnauthorizedError(f"expected {expected_type} token")
    return claims


def principal_from_claims(claims: dict[str, Any]) -> tuple[str, str | None, list[str]]:
    subject = claims.get("sub")
    if not subject:
        raise UnauthorizedError("token missing subject")
    workspace_id = claims.get("ws")
    roles = claims.get("roles") or []
    return subject, workspace_id, roles


def token_expiry_seconds(claims: dict[str, Any]) -> int:
    exp = claims.get("exp")
    if not exp:
        return 0
    return max(0, int(exp) - int(datetime.now(UTC).timestamp()))
