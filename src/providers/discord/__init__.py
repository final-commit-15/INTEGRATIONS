"""Discord provider: send messages, list guilds, and manage channels via the Discord API."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class DiscordProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "discord"
    name = "Discord"
    description = "Send messages, list guilds, and manage channels on Discord."
    auth_type = "oauth2"
    base_url = "https://discord.com/api/v10"
    timeout = 30.0
    supports_webhooks = True
    default_scopes = ["bot", "identify", "guilds"]
    oauth_authorize_url = "https://discord.com/oauth2/authorize"
    oauth_token_url = "https://discord.com/api/v10/oauth2/token"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = False
    oauth_token_header_auth = True

    capabilities = [
        Capability(
            name="send_message",
            description="Send a message to a Discord channel.",
            params_schema={
                "required": ["channel_id", "content"],
                "properties": {
                    "channel_id": {"type": "string"},
                    "content": {"type": "string"},
                    "tts": {"type": "boolean"},
                },
            },
        ),
        Capability(
            name="read_channel",
            description="Read messages from a Discord channel.",
            params_schema={
                "required": ["channel_id"],
                "properties": {
                    "channel_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
        Capability(
            name="list_guilds",
            description="List guilds the bot/user is in.",
            params_schema={
                "properties": {"limit": {"type": "integer", "default": 100}},
            },
        ),
        Capability(
            name="list_channels",
            description="List channels in a guild.",
            params_schema={
                "required": ["guild_id"],
                "properties": {"guild_id": {"type": "string"}},
            },
        ),
        Capability(
            name="create_channel",
            description="Create a channel in a guild.",
            params_schema={
                "required": ["guild_id", "name"],
                "properties": {
                    "guild_id": {"type": "string"},
                    "name": {"type": "string"},
                    "channel_type": {"type": "integer", "default": 0},
                },
            },
        ),
        Capability(
            name="send_typing",
            description="Show a typing indicator in a channel.",
            params_schema={
                "required": ["channel_id"],
                "properties": {"channel_id": {"type": "string"}},
            },
        ),
        Capability(
            name="get_user",
            description="Get information about a Discord user.",
            params_schema={
                "required": ["user_id"],
                "properties": {"user_id": {"type": "string"}},
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.context:
            return {}
        creds = self.context.credentials
        bot_token = creds.get("bot_token", "")
        if bot_token:
            return {"Authorization": f"Bot {bot_token}"}
        access_token = creds.get("access_token", "")
        return {"Authorization": f"Bearer {access_token}"}

    async def validate_connection(self) -> bool:
        resp = await self._get("/users/@me")
        data = resp.json()
        return resp.status_code == 200 and "id" in data

    async def health(self) -> ProviderHealth:
        try:
            valid = await self.validate_connection()
            if valid:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "could not validate connection"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("send_message")
    async def send_message(self, channel_id: str, content: str, tts: bool | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"content": content}
        if tts is not None:
            body["tts"] = tts
        resp = await self._post(f"/channels/{channel_id}/messages", json_data=body)
        return resp.json()

    @action("read_channel")
    async def read_channel(self, channel_id: str, limit: int = 50) -> dict[str, Any]:
        resp = await self._get(f"/channels/{channel_id}/messages", params={"limit": limit})
        return resp.json()

    @action("list_guilds")
    async def list_guilds(self, limit: int = 100) -> dict[str, Any]:
        resp = await self._get("/users/@me/guilds", params={"limit": limit})
        return resp.json()

    @action("list_channels")
    async def list_channels(self, guild_id: str) -> dict[str, Any]:
        resp = await self._get(f"/guilds/{guild_id}/channels")
        return resp.json()

    @action("create_channel")
    async def create_channel(self, guild_id: str, name: str, channel_type: int = 0) -> dict[str, Any]:
        resp = await self._post(
            f"/guilds/{guild_id}/channels",
            json_data={"name": name, "type": channel_type},
        )
        return resp.json()

    @action("send_typing")
    async def send_typing(self, channel_id: str) -> dict[str, Any]:
        resp = await self._post(f"/channels/{channel_id}/typing")
        return resp.json()

    @action("get_user")
    async def get_user(self, user_id: str) -> dict[str, Any]:
        resp = await self._get(f"/users/{user_id}")
        return resp.json()

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        return bool(headers.get("x-signature-ed25519"))


ProviderCls = DiscordProvider
provider = DiscordProvider()
