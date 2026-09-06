"""Tests for the Fernet-backed encryption service."""

from __future__ import annotations

import base64

import pytest

from exceptions import CredentialInvalid, EncryptionError
from services.encryption_service import (
    EncryptionService,
    get_encryption_service,
    reset_encryption_service,
)

KEY_A = base64.urlsafe_b64encode(b"0" * 32)
KEY_B = base64.urlsafe_b64encode(b"1" * 32)


@pytest.fixture
def encryption_service() -> EncryptionService:
    return EncryptionService(current_key=KEY_A)


def test_roundtrip(encryption_service: EncryptionService) -> None:
    payload = {"access_token": "tok-123", "refresh_token": "ref-456", "nested": {"a": [1, 2]}}
    token = encryption_service.encrypt(payload)
    assert encryption_service.decrypt(token) == payload


def test_encrypt_produces_distinct_tokens(encryption_service: EncryptionService) -> None:
    # Fernet uses a random IV, so two encryptions of the same payload differ,
    # but both round-trip.
    payload = {"a": 1}
    first = encryption_service.encrypt(payload)
    second = encryption_service.encrypt(payload)
    assert first != second
    assert encryption_service.decrypt(first) == encryption_service.decrypt(second) == payload


def test_encrypt_credentials_typed_wrapper(encryption_service: EncryptionService) -> None:
    credentials = {"api_key": "sk-test"}
    token = encryption_service.encrypt_credentials(credentials)
    assert encryption_service.decrypt_credentials(token) == credentials


def test_decrypt_credentials_missing_object_raises(encryption_service: EncryptionService) -> None:
    token = encryption_service.encrypt({"something": "else"})
    with pytest.raises(CredentialInvalid):
        encryption_service.decrypt_credentials(token)


def test_wrong_key_raises_encryption_error() -> None:
    svc_a = EncryptionService(current_key=KEY_A)
    token = svc_a.encrypt({"secret": "value"})
    svc_b = EncryptionService(current_key=KEY_B)
    with pytest.raises(EncryptionError):
        svc_b.decrypt(token)


def test_previous_key_reads_legacy_tokens() -> None:
    svc_old = EncryptionService(current_key=KEY_A)
    token = svc_old.encrypt_credentials({"access_token": "legacy"})
    svc_new = EncryptionService(current_key=KEY_B, previous_keys=[KEY_A])
    assert svc_new.decrypt_credentials(token) == {"access_token": "legacy"}


def test_re_encrypt_rotates_to_current_key() -> None:
    svc_old = EncryptionService(current_key=KEY_A)
    token = svc_old.encrypt({"v": "data"})
    svc_new = EncryptionService(current_key=KEY_B, previous_keys=[KEY_A])
    re_encrypted = svc_new.re_encrypt(token)
    assert svc_new.decrypt(re_encrypted) == {"v": "data"}
    # Old key alone can no longer read the rotated token.
    with pytest.raises(EncryptionError):
        svc_old.decrypt(re_encrypted)


def test_requires_rotation_reports_valid_token(encryption_service: EncryptionService) -> None:
    """Document current behavior: ``requires_rotation`` returns True if the token's
    prefix does not match the current encryption key (conservative heuristic).
    """
    token = encryption_service.encrypt({"a": 1})
    assert encryption_service.requires_rotation(token) is True
    # Invalid tokens also return True (conservative: can't verify = might need rotation)
    assert encryption_service.requires_rotation("junk-not-a-fernet-token") is True


def test_mask_credentials(encryption_service: EncryptionService) -> None:
    credentials = {
        "access_token": "supersecret1234",
        "refresh_token": "rt",
        "api_key": "abc12345",
        "email": "ops@example.com",
    }
    masked = encryption_service.mask_credentials(credentials)
    assert masked["access_token"] == "***1234"
    assert masked["refresh_token"] == "***rt"
    assert masked["api_key"] == "***2345"
    assert masked["email"] == "ops@example.com"


def test_mask_credentials_empty_value(encryption_service: EncryptionService) -> None:
    assert encryption_service.mask_credentials({"password": ""}) == {"password": "***"}


def test_singleton_lifecycle() -> None:
    reset_encryption_service()
    first = get_encryption_service()
    second = get_encryption_service()
    assert first is second
    reset_encryption_service()
    third = get_encryption_service()
    assert third is not first
    assert isinstance(third, EncryptionService)
