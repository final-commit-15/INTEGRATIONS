"""Trello provider: boards, lists, cards, labels, and comments."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)

BASE_URL = "https://api.trello.com/1"


class TrelloProvider(BaseIntegrationProvider):
    provider_key = "trello"
    name = "Trello"
    description = "Manage boards, lists, cards, labels, and comments in Trello."
    auth_type = "api_key"
    base_url = BASE_URL
    timeout = 30.0
    supports_webhooks = True

    capabilities = [
        Capability(
            name="list_boards",
            description="List all boards visible to the authenticated user.",
            params_schema={},
        ),
        Capability(
            name="create_board",
            description="Create a new board.",
            params_schema={
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "default_lists": {"type": "boolean"},
                },
            },
        ),
        Capability(
            name="list_lists",
            description="List all lists on a board.",
            params_schema={"required": ["board_id"], "properties": {"board_id": {"type": "string"}}},
        ),
        Capability(
            name="create_list",
            description="Create a new list on a board.",
            params_schema={
                "required": ["board_id", "name"],
                "properties": {"board_id": {"type": "string"}, "name": {"type": "string"}},
            },
        ),
        Capability(
            name="list_cards",
            description="List all cards in a list.",
            params_schema={"required": ["list_id"], "properties": {"list_id": {"type": "string"}}},
        ),
        Capability(
            name="create_card",
            description="Create a new card in a list.",
            params_schema={
                "required": ["list_id", "name"],
                "properties": {
                    "list_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "due": {"type": "string"},
                },
            },
        ),
        Capability(
            name="get_card",
            description="Fetch a single card by id.",
            params_schema={"required": ["card_id"], "properties": {"card_id": {"type": "string"}}},
        ),
        Capability(
            name="update_card",
            description="Update arbitrary fields of a card.",
            params_schema={"required": ["card_id"], "properties": {"card_id": {"type": "string"}}},
        ),
        Capability(
            name="add_comment",
            description="Add a comment to a card.",
            params_schema={
                "required": ["card_id", "text"],
                "properties": {"card_id": {"type": "string"}, "text": {"type": "string"}},
            },
        ),
        Capability(
            name="create_label",
            description="Create a label on a board.",
            params_schema={
                "required": ["board_id", "name"],
                "properties": {
                    "board_id": {"type": "string"},
                    "name": {"type": "string"},
                    "color": {"type": "string"},
                },
            },
        ),
        Capability(
            name="move_card",
            description="Move a card to a different list.",
            params_schema={
                "required": ["card_id", "list_id"],
                "properties": {"card_id": {"type": "string"}, "list_id": {"type": "string"}},
            },
        ),
        Capability(
            name="delete_card",
            description="Permanently delete a card.",
            params_schema={"required": ["card_id"], "properties": {"card_id": {"type": "string"}}},
        ),
    ]

    # ------------------------------------------------------------------ auth

    @property
    def auth_headers(self) -> dict[str, str]:
        return {}

    def _trello_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        creds = self.context.require("api_key", "api_token") if self.context else {}
        merged = dict(params or {})
        merged["key"] = creds.get("api_key", "")
        merged["token"] = creds.get("api_token", "")
        return merged

    async def validate_connection(self) -> bool:
        resp = await self._get("/members/me", params=self._trello_params())
        data = resp.json()
        return "id" in data

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/members/me", params=self._trello_params())
            data = resp.json()
            return ProviderHealth.healthy(detail={"username": data.get("username")})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def refresh_token(self) -> bool:
        return False

    # ------------------------------------------------------------------ actions

    @action("list_boards")
    async def list_boards(self) -> dict[str, Any]:
        resp = await self._get("/members/me/boards", params=self._trello_params())
        return resp.json()

    @action("create_board")
    async def create_board(self, name: str, default_lists: bool = True) -> dict[str, Any]:
        params = self._trello_params(
            {"name": name, "defaultLists": str(bool(default_lists)).lower()}
        )
        resp = await self._post("/boards", params=params)
        return resp.json()

    @action("list_lists")
    async def list_lists(self, board_id: str) -> dict[str, Any]:
        resp = await self._get(f"/boards/{board_id}/lists", params=self._trello_params())
        return resp.json()

    @action("create_list")
    async def create_list(self, board_id: str, name: str) -> dict[str, Any]:
        params = self._trello_params({"idBoard": board_id, "name": name})
        resp = await self._post("/lists", params=params)
        return resp.json()

    @action("list_cards")
    async def list_cards(self, list_id: str) -> dict[str, Any]:
        resp = await self._get(f"/lists/{list_id}/cards", params=self._trello_params())
        return resp.json()

    @action("create_card")
    async def create_card(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        due: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"idList": list_id, "name": name}
        if description is not None:
            params["desc"] = description
        if due is not None:
            params["due"] = due
        resp = await self._post("/cards", params=self._trello_params(params))
        return resp.json()

    @action("get_card")
    async def get_card(self, card_id: str) -> dict[str, Any]:
        resp = await self._get(f"/cards/{card_id}", params=self._trello_params())
        return resp.json()

    @action("update_card")
    async def update_card(self, card_id: str, **changes: Any) -> dict[str, Any]:
        resp = await self._put(f"/cards/{card_id}", params=self._trello_params(dict(changes)))
        return resp.json()

    @action("add_comment")
    async def add_comment(self, card_id: str, text: str) -> dict[str, Any]:
        params = self._trello_params({"text": text})
        resp = await self._post(f"/cards/{card_id}/actions/comments", params=params)
        return resp.json()

    @action("create_label")
    async def create_label(self, board_id: str, name: str, color: str = "yellow") -> dict[str, Any]:
        params = self._trello_params({"idBoard": board_id, "name": name, "color": color})
        resp = await self._post("/labels", params=params)
        return resp.json()

    @action("move_card")
    async def move_card(self, card_id: str, list_id: str) -> dict[str, Any]:
        params = self._trello_params({"idList": list_id})
        resp = await self._put(f"/cards/{card_id}", params=params)
        return resp.json()

    @action("delete_card")
    async def delete_card(self, card_id: str) -> dict[str, Any]:
        await self._delete(f"/cards/{card_id}", params=self._trello_params())
        return {"deleted": True}

    # ------------------------------------------------------------------ webhooks

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        import hashlib
        import hmac
        import json

        from config import settings

        secret = settings.webhook_default_secret.get_secret_value()
        if not secret:
            return True
        signature = headers.get("x-trello-webhook-signature") or headers.get("X-AgentForge-Signature") or ""
        if not signature:
            return False
        expected = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        provided = signature
        if provided.startswith("sha256="):
            provided = provided[len("sha256="):]
        return hmac.compare_digest(provided, expected)


ProviderCls = TrelloProvider
provider = TrelloProvider()
