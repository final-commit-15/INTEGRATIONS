"""Tests for security helpers: masking, hashing, constant-time compare, SSRF."""

from __future__ import annotations

import base64

import pytest

from utils.security import (
    base64url_encode_fernet,
    constant_time_equals,
    hash_credential,
    is_private_ip,
    mask_dict,
    mask_secret,
    validate_target_url,
)


def test_mask_secret_none_returns_literal_none() -> None:
    assert mask_secret(None) == "None"
    assert mask_secret("") == "None"


def test_mask_secret_short_value_fully_masked() -> None:
    assert mask_secret("abc") == "***"


def test_mask_secret_tail_visible() -> None:
    assert mask_secret("longsecretvalue") == "***********alue"
    assert mask_secret("longsecretvalue", visible_chars=2) == "*************ue"
    assert mask_secret("abc12345") == "****2345"


def test_mask_dict_masks_sensitive_keys() -> None:
    source = {"api_key": "sk-123", "name": "agent", "access_token": "tok"}
    masked = mask_dict(source, sensitive={"api_key"})
    assert masked["api_key"] == "***"
    assert masked["access_token"] == "***"
    assert masked["name"] == "agent"
    # Original dict is not mutated.
    assert source["api_key"] == "sk-123"


def test_hash_credential_deterministic() -> None:
    salt = "agentforge"
    assert hash_credential("value-1", salt) == hash_credential("value-1", salt)
    assert hash_credential("value-1", salt) != hash_credential("value-2", salt)
    assert len(hash_credential("value-1", salt)) == 64


def test_constant_time_equals() -> None:
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abd") is False
    assert constant_time_equals("", "") is True


def test_base64url_encode_fernet() -> None:
    encoded = base64url_encode_fernet("hello")
    assert "=" not in encoded
    assert base64.urlsafe_b64decode(encoded + "==") == b"hello"


def test_is_private_ip() -> None:
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("10.0.0.5") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("169.254.169.254") is True
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("not-an-ip") is True


def test_validate_target_url_rejects_bad_scheme() -> None:
    with pytest.raises(ValueError):
        validate_target_url("ftp://example.com/x")


def test_validate_target_url_rejects_localhost() -> None:
    with pytest.raises(ValueError):
        validate_target_url("http://localhost:9000/hook")
    with pytest.raises(ValueError):
        validate_target_url("https://127.0.0.1/hook")


def test_validate_target_url_accepts_public(monkeypatch) -> None:
    monkeypatch.setattr("utils.security.socket.gethostbyname", lambda host: "93.184.216.34")
    assert validate_target_url("https://example.com/hook") == "https://example.com/hook"


def test_validate_target_url_rejects_private_resolution(monkeypatch) -> None:
    monkeypatch.setattr("utils.security.socket.gethostbyname", lambda host: "10.1.2.3")
    with pytest.raises(ValueError):
        validate_target_url("https://intranet.corp/hook")
