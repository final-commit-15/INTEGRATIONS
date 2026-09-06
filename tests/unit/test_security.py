"""Tests for JWT creation/decoding and principal extraction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config import settings
from exceptions import UnauthorizedError
from security import (
    _mint_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    principal_from_claims,
    token_expiry_seconds,
)


def test_access_token_roundtrip() -> None:
    token = create_access_token(subject="user-1", workspace_id="ws-1", roles=["user"])
    claims = decode_token(token, expected_type="access")
    assert claims["sub"] == "user-1"
    assert claims["ws"] == "ws-1"
    assert claims["roles"] == ["user"]
    assert claims["iss"] == settings.app_name
    assert claims["aud"] == settings.app_name


def test_refresh_token_roundtrip_type_check() -> None:
    token = create_refresh_token(subject="user-1")
    claims = decode_token(token, expected_type="refresh")
    assert claims["type"] == "refresh"


def test_decode_with_wrong_expected_type_raises() -> None:
    token = create_access_token(subject="user-1")
    with pytest.raises(UnauthorizedError):
        decode_token(token, expected_type="refresh")


def test_expired_token_raises_unauthorized() -> None:
    expired = _mint_token(
        token_type="access",
        subject="user-1",
        expires=datetime.now(UTC) - timedelta(minutes=5),
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_token(expired)
    assert "invalid or expired" in exc_info.value.message


def test_tampered_signature_raises() -> None:
    token = create_access_token(subject="user-1")
    # Change the last char of the signature portion.
    tampered = token[:-2] + ("A" if token[-1] != "A" else "B") + token[-1]
    with pytest.raises(UnauthorizedError):
        decode_token(tampered)


def test_plain_garbage_token_raises() -> None:
    with pytest.raises(UnauthorizedError):
        decode_token("not.a.jwt")


def test_principal_from_claims() -> None:
    subject, workspace_id, roles = principal_from_claims(
        {"sub": "u1", "ws": "w1", "roles": ["admin", "user"]}
    )
    assert (subject, workspace_id, roles) == ("u1", "w1", ["admin", "user"])


def test_principal_from_claims_missing_subject_raises() -> None:
    with pytest.raises(UnauthorizedError):
        principal_from_claims({"roles": []})


def test_token_expiry_seconds() -> None:
    claims = {"exp": int(datetime.now(UTC).timestamp()) + 300}
    assert 295 <= token_expiry_seconds(claims) <= 300
    assert token_expiry_seconds({}) == 0


def test_token_contains_custom_claims() -> None:
    token = create_access_token(subject="u", roles=["admin"], extra_claims={"org": "acme"})
    claims = decode_token(token)
    assert claims["org"] == "acme"
