from unittest.mock import AsyncMock, patch

import pytest
from httpx import Response

from agentforge_integrations.auth.oauth2 import OAuth2Auth


@pytest.mark.asyncio
async def test_oauth2_token_refresh():
    mock_response = Response(
        200,
        json={"access_token": "new_token", "expires_in": 3600},
    )

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_post:
        oauth = OAuth2Auth("url", "id", "secret")

        token = await oauth.get_access_token()

        assert token == "new_token"
        mock_post.assert_called_once()