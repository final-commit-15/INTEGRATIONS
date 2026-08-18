import base64
import os
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..core.exceptions import ConfigurationError


class SecretManager:
    """Encrypt/decrypt sensitive credentials using Fernet (symmetric)."""

    def __init__(self, encryption_key: str | None = None, salt: bytes | None = None):
        if encryption_key:
            # Assume base64-encoded Fernet key
            self.key = encryption_key
        else:
            # Derive key from environment or generate one (not recommended for prod)
            password = os.getenv("ENCRYPTION_PASSWORD", "default-insecure")
            salt = salt or b"agentforge-salt"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            self.key = key.decode()

        self.cipher = Fernet(self.key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return base64."""
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        """Decrypt a base64-encoded encrypted string."""
        return self.cipher.decrypt(encrypted.encode()).decode()

    def encrypt_credentials(self, creds: dict[str, Any]) -> dict[str, Any]:
        """Encrypt all string values in credentials dict."""
        result = {}
        for k, v in creds.items():
            if isinstance(v, str) and v.startswith("encrypted::"):
                # Already encrypted, keep as-is
                result[k] = v
            elif isinstance(v, str):
                result[k] = f"encrypted::{self.encrypt(v)}"
            else:
                result[k] = v
        return result

    def decrypt_credentials(self, creds: dict[str, Any]) -> dict[str, Any]:
        """Decrypt encrypted credential values."""
        result = {}
        for k, v in creds.items():
            if isinstance(v, str) and v.startswith("encrypted::"):
                try:
                    result[k] = self.decrypt(v[len("encrypted::"):])
                except (ValueError, ConfigurationError) as e:
                    raise ConfigurationError(
                        f"Failed to decrypt credential {k}: {e}"
                    ) from e
            else:
                result[k] = v
        return result