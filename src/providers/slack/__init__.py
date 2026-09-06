"""Slack provider: send messages, manage channels, and interact with the Slack API."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from exceptions import IntegrationError
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class SlackProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "slack"
    name = "Slack"
    description = "Send messages, manage channels, and interact with Slack workspaces."
    auth_type = "oauth2"
    base_url = "https://slack.com/api"
    timeout = 30.0
    supports_webhooks = True
    default_scopes = [
        "channels:read",
        "channels:manage",
        "chat:write",
        "users:read",
        "files:write",
        "reactions:write",
    ]
    oauth_authorize_url = "https://slack.com/oauth/v2/authorize"
    oauth_token_url = "https://slack.com/api/oauth.v2.access"
    oauth_revoke_url = ""
    oauth_scopes = default_scopes
    oauth_pkce = False
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="send_message",
            description="Send a message to a Slack channel.",
            params_schema={
                "required": ["channel", "text"],
                "properties": {
                    "channel": {"type": "string"},
                    "text": {"type": "string"},
                    "thread_ts": {"type": "string"},
                },
            },
        ),
        Capability(
            name="post_message_in_thread",
            description="Post a reply in a thread.",
            params_schema={
                "required": ["channel", "text", "thread_ts"],
                "properties": {
                    "channel": {"type": "string"},
                    "text": {"type": "string"},
                    "thread_ts": {"type": "string"},
                },
            },
        ),
        Capability(
            name="list_channels",
            description="List channels in the workspace.",
            params_schema={
                "properties": {
                    "limit": {"type": "integer", "default": 100},
                    "cursor": {"type": "string"},
                    "exclude_archived": {"type": "boolean", "default": True},
                },
            },
        ),
        Capability(
            name="create_channel",
            description="Create a new Slack channel.",
            params_schema={
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "is_private": {"type": "boolean", "default": False},
                },
            },
        ),
        Capability(
            name="get_channel_info",
            description="Get information about a channel.",
            params_schema={
                "required": ["channel"],
                "properties": {"channel": {"type": "string"}},
            },
        ),
        Capability(
            name="send_message_to_user",
            description="Open a DM and send a message to a user.",
            params_schema={
                "required": ["user"],
                "properties": {
                    "user": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        ),
        Capability(
            name="list_users",
            description="List users in the workspace.",
            params_schema={
                "properties": {"limit": {"type": "integer", "default": 100}},
            },
        ),
        Capability(
            name="archive_channel",
            description="Archive a Slack channel.",
            params_schema={
                "required": ["channel"],
                "properties": {"channel": {"type": "string"}},
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.context:
            return {}
        creds = self.context.credentials
        token = creds.get("access_token") or creds.get("bot_token", "")
        return {"Authorization": f"Bearer {token}"}

    def _check_response(self, resp_json: dict[str, Any]) -> dict[str, Any]:
        if not resp_json.get("ok"):
            error = resp_json.get("error", "unknown_error")
            raise IntegrationError(
                f"slack api error: {error}",
                provider="slack",
            )
        return resp_json

    async def validate_connection(self) -> bool:
        resp = await self._get("/auth.test", retry=False)
        return bool(resp.json().get("ok"))

    async def health(self) -> ProviderHealth:
        try:
            valid = await self.validate_connection()
            if valid:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "auth.test returned not ok"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("send_message")
    async def send_message(self, channel: str, text: str, thread_ts: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            body["thread_ts"] = thread_ts
        resp = await self._post("/chat.postMessage", json_data=body)
        return self._check_response(resp.json())

    @action("post_message_in_thread")
    async def post_message_in_thread(self, channel: str, text: str, thread_ts: str) -> dict[str, Any]:
        resp = await self._post(
            "/chat.postMessage",
            json_data={"channel": channel, "text": text, "thread_ts": thread_ts},
        )
        return self._check_response(resp.json())

    @action("list_channels")
    async def list_channels(
        self,
        limit: int = 100,
        cursor: str | None = None,
        exclude_archived: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "exclude_archived": str(exclude_archived).lower()}
        if cursor:
            params["cursor"] = cursor
        resp = await self._get("/conversations.list", params=params)
        return self._check_response(resp.json())

    @action("create_channel")
    async def create_channel(self, name: str, is_private: bool = False) -> dict[str, Any]:
        resp = await self._post(
            "/conversations.create",
            json_data={"name": name, "is_private": is_private},
        )
        return self._check_response(resp.json())

    @action("get_channel_info")
    async def get_channel_info(self, channel: str) -> dict[str, Any]:
        resp = await self._get("/conversations.info", params={"channel": channel})
        return self._check_response(resp.json())

    @action("send_message_to_user")
    async def send_message_to_user(self, user: str, text: str = "") -> dict[str, Any]:
        open_resp = await self._post("/conversations.open", json_data={"users": user})
        open_data = self._check_response(open_resp.json())
        channel_id = open_data["channel"]["id"]
        msg_resp = await self._post(
            "/chat.postMessage",
            json_data={"channel": channel_id, "text": text},
        )
        return self._check_response(msg_resp.json())

    @action("list_users")
    async def list_users(self, limit: int = 100) -> dict[str, Any]:
        resp = await self._get("/users.list", params={"limit": limit})
        return self._check_response(resp.json())

    @action("archive_channel")
    async def archive_channel(self, channel: str) -> dict[str, Any]:
        resp = await self._post("/conversations.archive", json_data={"channel": channel})
        return self._check_response(resp.json())

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        from config import settings

        secret = settings.slack_signing_secret.get_secret_value()
        timestamp = headers.get("x-slack-request-timestamp", "")
        raw_body = payload.get("raw_body", "")
        sig_header = headers.get("x-slack-signature", "")

        basestring = f"v0:{timestamp}:{raw_body}"
        computed = "v0=" + hmac.new(
            secret.encode(), basestring.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, sig_header)


ProviderCls = SlackProvider
provider = SlackProvider()
