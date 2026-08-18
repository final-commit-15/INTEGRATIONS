import pytest

from agentforge_integrations.auth.credentials import CredentialManager


@pytest.mark.asyncio
async def test_credentials_from_env(monkeypatch):
    monkeypatch.setenv("integration_github_api_token", "test123")
    manager = CredentialManager()
    creds = await manager.get_credentials("github")
    assert creds["api_token"] == "test123"