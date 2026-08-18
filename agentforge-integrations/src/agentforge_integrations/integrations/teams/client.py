from typing import Any

import httpx

from ...auth.oauth2 import OAuth2Auth
from ...core.base import Integration, IntegrationConfig
from ...core.exceptions import AuthenticationError
from ...utils.logging import get_logger
from ...utils.retry import retry
from .webhooks import TeamsWebhookHandler

logger = get_logger(__name__)


class TeamsIntegration(Integration):
    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.client: httpx.AsyncClient | None = None
        self.oauth: OAuth2Auth | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("Teams integration is not initialized")
        return self.client

    async def initialize(self) -> None:
        client_id = self.config.credentials.get("client_id")
        client_secret = self.config.credentials.get("client_secret")
        if not client_id or not client_secret:
            raise AuthenticationError("Teams client_id and client_secret required.")

        self.oauth = OAuth2Auth(
            token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
            client_id=client_id,
            client_secret=client_secret,
            scope="https://graph.microsoft.com/.default",
        )
        self.client = httpx.AsyncClient(
            base_url="https://graph.microsoft.com/v1.0",
            timeout=30.0,
            auth=self.oauth,
        )
        self._initialized = True
        logger.info("Teams integration initialized.")

    async def health_check(self) -> bool:
        try:
            resp = await self.http_client.get("/users?$top=1")
            return resp.status_code == 200
        except Exception:
            return False

    async def execute(self, action: str, **kwargs) -> Any:
        method_map = {
            "send_message_to_channel": self.send_message_to_channel,
            "send_message_to_chat": self.send_message_to_chat,
            "list_teams": self.list_teams,
            "list_channels": self.list_channels,
            "get_message": self.get_message,
        }
        method = method_map.get(action)
        if not method:
            raise ValueError(f"Unknown action for Teams: {action}")
        return await method(**kwargs)

    @retry(max_attempts=3, backoff=1.0)
    async def send_message_to_channel(self, team_id: str, channel_id: str, message: str) -> dict[str, Any]:
        payload = {"body": {"content": message}}
        resp = await self.http_client.post(
            f"/teams/{team_id}/channels/{channel_id}/messages",
            json=payload,
        )
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def send_message_to_chat(self, chat_id: str, message: str) -> dict[str, Any]:
        payload = {"body": {"content": message}}
        resp = await self.http_client.post(f"/chats/{chat_id}/messages", json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    @retry(max_attempts=3, backoff=1.0)
    async def list_teams(self) -> list[dict[str, Any]]:
        resp = await self.http_client.get("/me/joinedTeams")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json().get("value", [])

    @retry(max_attempts=3, backoff=1.0)
    async def list_channels(self, team_id: str) -> list[dict[str, Any]]:
        resp = await self.http_client.get(f"/teams/{team_id}/channels")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json().get("value", [])

    @retry(max_attempts=3, backoff=1.0)
    async def get_message(self, team_id: str, channel_id: str, message_id: str) -> dict[str, Any]:
        resp = await self.http_client.get(f"/teams/{team_id}/channels/{channel_id}/messages/{message_id}")
        if resp.status_code >= 400:
            resp.raise_for_status()
        return resp.json()

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        handler = TeamsWebhookHandler(self)
        await handler.handle_webhook(event_type, payload)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()