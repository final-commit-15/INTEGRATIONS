import os
from typing import Any

from ..core.config import settings
from ..security.secret_manager import SecretManager


class CredentialManager:
    """Retrieves credentials from environment, vault, or encrypted storage."""

    def __init__(self, secret_manager: SecretManager | None = None):
        self._secret_manager = secret_manager or SecretManager(settings.ENCRYPTION_KEY)

    async def get_credentials(self, integration_name: str) -> dict[str, Any]:
        """
        Fetch credentials for a given integration.
        Prefers environment variables: INTEGRATION_<NAME>_<KEY>.
        """
        prefix = f"integration_{integration_name.lower()}_"
        creds = {}
        for key, value in os.environ.items():
            if key.lower().startswith(prefix):
                # Remove prefix and lower-case the key
                cred_key = key[len(prefix):].lower()
                creds[cred_key] = value

        # If credentials are encrypted, decrypt them
        if self._secret_manager:
            creds = self._secret_manager.decrypt_credentials(creds)
        return creds