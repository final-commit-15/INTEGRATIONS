
from unittest.mock import AsyncMock

import pytest
from httpx import Request, Response

from agentforge_integrations.core.base import IntegrationConfig
from agentforge_integrations.integrations.github.client import GitHubIntegration


@pytest.fixture
def github_config():
    return IntegrationConfig(
        name="github",
        credentials={"api_token": "test_token"},
    )


@pytest.mark.asyncio
async def test_github_get_repository(github_config):
    integration = GitHubIntegration(github_config)

    await integration.initialize()

    integration.client = AsyncMock()

    mock_resp = Response(
        200,
        json={
            "name": "test-repo",
            "full_name": "owner/test-repo",
        },
        request=Request(
            "GET",
            "https://api.github.com/repos/owner/test-repo",
        ),
    )

    integration.client.get.return_value = mock_resp

    result = await integration.get_repository("owner", "test-repo")

    assert result["name"] == "test-repo"
    integration.client.get.assert_called_once_with(
        "/repos/owner/test-repo"
    )


@pytest.mark.asyncio
async def test_github_health_check_failure(github_config):
    integration = GitHubIntegration(github_config)

    await integration.initialize()

    integration.client = AsyncMock()
    integration.client.get.side_effect = Exception("Network error")

    assert await integration.health_check() is False