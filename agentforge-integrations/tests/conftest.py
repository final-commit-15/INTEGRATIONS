import pytest_asyncio

from agentforge_integrations.auth.credentials import CredentialManager
from agentforge_integrations.core.manager import IntegrationManager
from agentforge_integrations.security.secret_manager import SecretManager


@pytest_asyncio.fixture
async def integration_manager():
    credential_manager = CredentialManager()
    return IntegrationManager(credential_manager)


@pytest_asyncio.fixture
async def secret_manager():
    # Use a fixed key for testing (not secure, but fine for tests)
    return SecretManager(encryption_key="2HqZIP2hE5y5vBqoW9YKCtE9KzUK5ZvG7uJYQzP6S7U=")