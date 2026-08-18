from unittest.mock import AsyncMock

import pytest

from agentforge_integrations.core.manager import IntegrationManager
from agentforge_integrations.webhooks.dispatcher import WebhookDispatcher


@pytest.mark.asyncio
async def test_dispatch_calls_handle_webhook():
    mock_manager = AsyncMock(spec=IntegrationManager)
    mock_integration = AsyncMock()
    mock_integration.handle_webhook = AsyncMock()
    mock_manager.get_integration.return_value = mock_integration

    dispatcher = WebhookDispatcher(mock_manager)
    await dispatcher.dispatch("github", b'{"event":"test"}', {"X-GitHub-Event": "push"})
    mock_manager.get_integration.assert_called_with("github")
    mock_integration.handle_webhook.assert_called_with("push", {"event": "test"})