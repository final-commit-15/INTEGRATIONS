from typing import Any

import httpx

from ...core.base import Integration, IntegrationConfig
from ...core.exceptions import AuthenticationError, IntegrationError
from ...utils.logging import get_logger
from ...utils.retry import retry
from .webhooks import SlackWebhookHandler

logger = get_logger(__name__)


class SlackIntegration(Integration):
    BASE_URL = "https://slack.com/api"

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("Slack integration is not initialized")
        return self.client

    async def initialize(self) -> None:
        token = self.config.credentials.get("bot_token")
        if not token:
            raise AuthenticationError("Slack bot token missing.")
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        self._initialized = True
        logger.info("Slack integration initialized.")

    async def health_check(self) -> bool:
        try:
            resp = await self.http_client.get("/auth.test")
            return resp.status_code == 200 and resp.json().get("ok") is True
        except Exception:
            return False

    async def execute(self, action: str, **kwargs) -> Any:
        method_map = {
            "send_message": self.send_message,
            "send_ephemeral": self.send_ephemeral,
            "update_message": self.update_message,
            "delete_message": self.delete_message,
            "get_channel_history": self.get_channel_history,
            "list_channels": self.list_channels,
            "list_users": self.list_users,
            "add_reaction": self.add_reaction,
        }
        method = method_map.get(action)
        if not method:
            raise ValueError(f"Unknown action for Slack: {action}")
        return await method(**kwargs)

    @retry(max_attempts=3, backoff=1.0)
    async def send_message(self, channel: str, text: str, thread_ts: str | None = None) -> dict[str, Any]:
        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        resp = await self.http_client.post("/chat.postMessage", data=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack error: {result.get('error')}")
        return result

    @retry(max_attempts=3, backoff=1.0)
    async def send_ephemeral(self, channel: str, user: str, text: str) -> dict[str, Any]:
        payload = {"channel": channel, "user": user, "text": text}
        resp = await self.http_client.post("/chat.postEphemeral", data=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack ephemeral error: {result.get('error')}")
        return result

    @retry(max_attempts=3, backoff=1.0)
    async def update_message(self, channel: str, ts: str, text: str) -> dict[str, Any]:
        payload = {"channel": channel, "ts": ts, "text": text}
        resp = await self.http_client.post("/chat.update", data=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack update error: {result.get('error')}")
        return result

    @retry(max_attempts=3, backoff=1.0)
    async def delete_message(self, channel: str, ts: str) -> dict[str, Any]:
        payload = {"channel": channel, "ts": ts}
        resp = await self.http_client.post("/chat.delete", data=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack delete error: {result.get('error')}")
        return result

    @retry(max_attempts=3, backoff=1.0)
    async def get_channel_history(self, channel: str, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "channel": channel,
            "limit": limit,
        }
        resp = await self.http_client.get(
            "/conversations.history",
            params=params,
        )
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack history error: {result.get('error')}")
        return result.get("messages", [])

    @retry(max_attempts=3, backoff=1.0)
    async def list_channels(self, exclude_archived: bool = True) -> list[dict[str, Any]]:
        params: dict[str, bool] = {"exclude_archived": exclude_archived}
        resp = await self.http_client.get("/conversations.list", params=params)
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack list channels error: {result.get('error')}")
        return result.get("channels", [])

    @retry(max_attempts=3, backoff=1.0)
    async def list_users(self) -> list[dict[str, Any]]:
        resp = await self.http_client.get("/users.list")
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack list users error: {result.get('error')}")
        return result.get("members", [])

    @retry(max_attempts=3, backoff=1.0)
    async def add_reaction(self, channel: str, name: str, timestamp: str) -> dict[str, Any]:
        payload = {"channel": channel, "name": name, "timestamp": timestamp}
        resp = await self.http_client.post("/reactions.add", data=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise IntegrationError(f"Slack reaction error: {result.get('error')}")
        return result

    async def handle_webhook(self, event_type: str | None, payload: dict[str, Any]) -> None:
        handler = SlackWebhookHandler(self)
        await handler.handle_webhook(event_type, payload)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()