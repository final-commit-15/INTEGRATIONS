import httpx
import pytest

from agentforge_integrations.auth.apikey import APIKeyAuth


@pytest.mark.asyncio
async def test_apikey_auth():
    auth = APIKeyAuth("test-key", header_name="X-API-Key", prefix="")
    request = httpx.Request("GET", "https://example.com")
    await auth(request)
    assert request.headers["X-API-Key"] == "test-key"