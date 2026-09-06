"""Encryption service.

Guards stored credentials with Fernet (AES-128-CBC + HMAC-SHA256). Supports key
rotation: the current ENCRYPTION_KEY decrypts new data while ENCRYPTION_KEY_PREVIOUS
list allows migrating/reading data encrypted under prior keys.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from config import _derive_key, settings
from exceptions import CredentialInvalid, EncryptionError


def _fernet_key(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw)


class EncryptionService:
    """Deterministic, versioned credential encryption/decryption."""

    def __init__(self, *, current_key: bytes | None = None, previous_keys: list[bytes] | None = None) -> None:
        self._current_raw = current_key or settings.encryption_key_bytes
        self._keys: list[bytes] = []
        if previous_keys is not None:
            self._keys = previous_keys
        elif settings.encryption_key_previous:
            salt = settings.credential_hash_salt.get_secret_value().strip() or "agentforge"
            self._keys = [
                _fernet_key(_derive_key(previous, salt, 32))
                for previous in settings.encryption_key_previous
                if previous.strip()
            ]
        self._fernet = Fernet(self._current_raw)

    # -- primitive ops ------------------------------------------------------

    def encrypt(self, payload: dict[str, Any]) -> str:
        """Serialize + encrypt an arbitrary JSONable dict into a Fernet token string."""
        try:
            plaintext = json.dumps(payload, sort_keys=True).encode("utf-8")
            return self._fernet.encrypt(plaintext).decode("ascii")
        except Exception as exc:
            raise EncryptionError("failed to encrypt payload") from exc

    def decrypt(self, token_value: str) -> dict[str, Any]:
        """Decrypt a Fernet token string, trying the current and previous keys."""
        keys = [self._current_raw, *self._keys]
        last_error: Exception | None = None
        for raw in keys:
            try:
                f = Fernet(raw)
                plaintext = f.decrypt(token_value.encode("ascii"))
                data = json.loads(plaintext.decode("utf-8"))
                if not isinstance(data, dict):
                    raise CredentialInvalid("decrypted payload is not an object")
                return data
            except InvalidToken:
                last_error = None  # wrong key, try next
            except CredentialInvalid:
                raise
            except Exception as exc:
                last_error = exc
        if last_error:
            raise EncryptionError("credential decryption failed") from last_error
        raise EncryptionError("credential decryption failed - invalid token")

    def re_encrypt(self, token_value: str) -> str:
        """Decrypt under any key and re-encrypt under the current key (rotation)."""
        data = self.decrypt(token_value)
        return self.encrypt(data)

    # -- typed helpers --------------------------------------------------------

    def encrypt_credentials(self, credentials: dict[str, Any]) -> str:
        return self.encrypt({"v": 1, "credentials": credentials})

    def decrypt_credentials(self, token_value: str) -> dict[str, Any]:
        data = self.decrypt(token_value)
        creds = data.get("credentials")
        if not isinstance(creds, dict):
            raise CredentialInvalid("credential payload missing credentials object")
        return creds

    def mask_credentials(self, credentials: dict[str, Any]) -> dict[str, str]:
        """Return provider credentials with secret values masked."""
        masked: dict[str, str] = {}
        sensitive_keys = {
            "access_token",
            "refresh_token",
            "client_secret",
            "api_key",
            "secret_key",
            "auth_token",
            "password",
            "token",
            "private_key",
        }
        for key, value in credentials.items():
            if key in sensitive_keys or any(s in key.lower() for s in ("secret", "token", "password")):
                masked[key] = f"***{str(value)[-4:]}" if value else "***"
            else:
                masked[key] = str(value)
        return masked

    def requires_rotation(self, token_value: str) -> bool:
        """True if the token was encrypted under a non-current key."""
        try:
            prefix = token_value.split(".", 1)[0]
            decoded = base64.urlsafe_b64decode(prefix + "=" * (-len(prefix) % 4))
            return decoded != base64.urlsafe_b64decode(self._current_raw)
        except Exception:
            return False


encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Return a lazily-constructed singleton so imports never require the key."""
    global encryption_service
    if encryption_service is None:
        encryption_service = EncryptionService()
    return encryption_service


def reset_encryption_service() -> None:
    global encryption_service
    encryption_service = None
