from unittest.mock import AsyncMock

import pytest
from httpx import Request, Response

from agentforge_integrations.core.base import IntegrationConfig
from agentforge_integrations.integrations.jira.client import JiraIntegration


@pytest.mark.asyncio
async def test_jira_get_issue():
    config = IntegrationConfig(
        name="jira",
        credentials={
            "base_url": "https://test.atlassian.net",
            "email": "x",
            "api_token": "y",
        },
    )

    inst = JiraIntegration(config)

    await inst.initialize()

    inst.client = AsyncMock()
    mock_resp = Response(
        200,
        json={
            "key": "TEST-1",
            "fields": {
                "summary": "test"
            }
        },
        request=Request(
            "GET",
            "https://test.atlassian.net/rest/api/3/issue/TEST-1",
        ),
    )
    inst.client.get.return_value = mock_resp

    result = await inst.get_issue("TEST-1")

    assert result["key"] == "TEST-1"