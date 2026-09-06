"""Gmail provider: read, send, draft, and search emails via Google APIs."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from typing import Any

import httpx

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)

BASE_URL = "https://gmail.googleapis.com/gmail/v1"


class GmailProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "gmail"
    name = "Gmail"
    description = "Read, send, draft, and search emails in a Gmail mailbox."
    auth_type = "oauth2"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = False
    default_scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ]
    oauth_authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_url = "https://oauth2.googleapis.com/token"
    oauth_revoke_url = "https://oauth2.googleapis.com/revoke"
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="send_email",
            description="Send a plaintext or HTML email.",
            params_schema={
                "required": ["to"],
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "html": {"type": "boolean"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "attachments": {"type": "array"},
                },
            },
            examples=["gmail.send_email to=user@example.com subject=Hello body=World"],
        ),
        Capability(
            name="draft_email",
            description="Create an email draft without sending.",
            params_schema={
                "required": ["to"],
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        ),
        Capability(
            name="search_emails",
            description="Search the inbox with a Gmail query string.",
            params_schema={
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
            },
        ),
        Capability(
            name="read_email",
            description="Fetch a single message by id.",
            params_schema={"required": ["email_id"], "properties": {"email_id": {"type": "string"}}},
        ),
        Capability(
            name="list_messages",
            description="List recent messages from the inbox.",
            params_schema={"properties": {"max_results": {"type": "integer"}, "label_ids": {"type": "array"}}},
        ),
        Capability(
            name="list_labels",
            description="List all mailbox labels.",
            params_schema={},
        ),
        Capability(
            name="mark_read",
            description="Mark a message as read.",
            params_schema={"required": ["email_id"], "properties": {"email_id": {"type": "string"}}},
        ),
        Capability(
            name="get_thread",
            description="Fetch a full thread by id.",
            params_schema={"required": ["thread_id"], "properties": {"thread_id": {"type": "string"}}},
        ),
    ]

    # ------------------------------------------------------------------ auth

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {"Authorization": f"Bearer {token}"}

    async def validate_connection(self) -> bool:
        profile = await self._get_profile()
        return "emailAddress" in profile

    async def health(self) -> ProviderHealth:
        try:
            profile = await self._get_profile()
            return ProviderHealth.healthy(detail={"email": profile.get("emailAddress")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def _get_profile(self) -> dict[str, Any]:
        resp = await self._get("/users/me/profile")
        return resp.json()

    # ------------------------------------------------------------------ actions

    @action("send_email")
    async def send_email(
        self,
        to: str,
        subject: str = "",
        body: str = "",
        html: bool = False,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        profile = await self._get_profile()
        sender = profile.get("emailAddress", "")
        raw = _build_mime_message(
            to=to,
            sender=sender,
            subject=subject,
            body=body,
            html=html,
            cc=cc or [],
            bcc=bcc or [],
            attachments=attachments or [],
        )
        resp = await self._post(
            "/users/me/messages/send",
            json_data={"raw": urlsafe_b64encode(raw.encode()).decode()},
        )
        return resp.json()

    @action("draft_email")
    async def draft_email(
        self,
        to: str,
        subject: str = "",
        body: str = "",
        html: bool = False,
        cc: list[str] | None = None,
    ) -> dict[str, Any]:
        profile = await self._get_profile()
        sender = profile.get("emailAddress", "")
        raw = _build_mime_message(
            to=to, sender=sender, subject=subject, body=body, html=html, cc=cc or [], bcc=[], attachments=[]
        )
        resp = await self._post(
            "/users/me/drafts",
            json_data={"message": {"raw": urlsafe_b64encode(raw.encode()).decode()}},
        )
        return resp.json()

    @action("search_emails")
    async def search_emails(self, query: str, max_results: int = 20) -> dict[str, Any]:
        resp = await self._get("/users/me/messages", params={"q": query, "maxResults": max_results})
        return resp.json()

    @action("read_email")
    async def read_email(self, email_id: str, format: str = "full") -> dict[str, Any]:
        resp = await self._get(f"/users/me/messages/{email_id}", params={"format": format})
        return resp.json()

    @action("list_messages")
    async def list_messages(self, max_results: int = 20, label_ids: list[str] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"maxResults": max_results}
        if label_ids:
            params["labelIds"] = label_ids
        resp = await self._get("/users/me/messages", params=params)
        return resp.json()

    @action("list_labels")
    async def list_labels(self) -> dict[str, Any]:
        resp = await self._get("/users/me/labels")
        return resp.json()

    @action("mark_read")
    async def mark_read(self, email_id: str) -> dict[str, Any]:
        resp = await self._patch(
            f"/users/me/messages/{email_id}",
            json_data={"removeLabelIds": ["UNREAD"]},
        )
        return resp.json()

    @action("get_thread")
    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        resp = await self._get(f"/users/me/threads/{thread_id}")
        return resp.json()


def _build_mime_message(
    *,
    to: str,
    sender: str,
    subject: str,
    body: str,
    html: bool,
    cc: list[str],
    bcc: list[str],
    attachments: list[dict[str, Any]],
) -> str:
    """Build a minimal RFC-2822 message."""
    import base64

    lines = [
        f"From: {sender}",
        f"To: {to}",
        f"Subject: {subject}",
        "MIME-Version: 1.0",
    ]
    if cc:
        lines.append(f"Cc: {', '.join(cc)}")
    if bcc:
        lines.append(f"Bcc: {', '.join(bcc)}")

    if attachments:
        boundary = "agentforge_mixed_boundary"
        lines.append(f"Content-Type: multipart/mixed; boundary=\"{boundary}\"")
        lines.append("")
        lines.append(f"--{boundary}")
        lines.append("Content-Type: text/plain; charset=UTF-8")
        lines.append("Content-Transfer-Encoding: 7bit")
        lines.append("")
        lines.append(body)
        for attachment in attachments:
            filename = attachment.get("filename", "attachment.bin")
            content = attachment.get("content", "")
            ctype = attachment.get("mime_type", "application/octet-stream")
            lines.append(f"--{boundary}")
            lines.append(f"Content-Type: {ctype}; name=\"{filename}\"")
            lines.append("Content-Transfer-Encoding: base64")
            lines.append("")
            try:
                encoded = base64.b64encode(bytes(content, "utf-8")).decode() if isinstance(content, str) else base64.b64encode(content).decode()
            except Exception:
                encoded = ""
            lines.append(encoded)
        lines.append(f"--{boundary}--")
    else:
        content_type = "text/html; charset=UTF-8" if html else "text/plain; charset=UTF-8"
        lines.append(f"Content-Type: {content_type}")
        lines.append("Content-Transfer-Encoding: 7bit")
        lines.append("")
        lines.append(body)
    return "\r\n".join([line for line in lines if line is not None])


ProviderCls = GmailProvider
provider = GmailProvider()
