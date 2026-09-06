"""Google Calendar provider: manage calendars and events via the Google Calendar API."""

from __future__ import annotations

from typing import Any

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    OAuthProviderMixin,
    ProviderHealth,
    action,
)


class GoogleCalendarProvider(OAuthProviderMixin, BaseIntegrationProvider):
    provider_key = "google_calendar"
    name = "Google Calendar"
    description = "List calendars, create, update, and delete events in Google Calendar."
    auth_type = "oauth2"
    base_url = "https://www.googleapis.com/calendar/v3"
    timeout = 30.0
    supports_webhooks = False
    default_scopes = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ]
    oauth_authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_url = "https://oauth2.googleapis.com/token"
    oauth_revoke_url = "https://oauth2.googleapis.com/revoke"
    oauth_scopes = default_scopes
    oauth_pkce = True
    oauth_token_header_auth = False

    capabilities = [
        Capability(
            name="list_calendars",
            description="List all calendars for the authenticated user.",
            params_schema={},
        ),
        Capability(
            name="create_event",
            description="Create a new calendar event.",
            params_schema={
                "required": ["summary", "start", "end"],
                "properties": {
                    "summary": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "calendar_id": {"type": "string", "default": "primary"},
                },
            },
        ),
        Capability(
            name="update_event",
            description="Update fields on an existing event.",
            params_schema={
                "required": ["event_id"],
                "properties": {
                    "event_id": {"type": "string"},
                    "calendar_id": {"type": "string", "default": "primary"},
                },
            },
        ),
        Capability(
            name="delete_event",
            description="Delete an event by id.",
            params_schema={
                "required": ["event_id"],
                "properties": {
                    "event_id": {"type": "string"},
                    "calendar_id": {"type": "string", "default": "primary"},
                },
            },
        ),
        Capability(
            name="list_events",
            description="List upcoming events from a calendar.",
            params_schema={
                "properties": {
                    "calendar_id": {"type": "string", "default": "primary"},
                    "time_min": {"type": "string"},
                    "time_max": {"type": "string"},
                    "max_results": {"type": "integer", "default": 50},
                },
            },
        ),
        Capability(
            name="get_event",
            description="Get a single event by id.",
            params_schema={
                "required": ["event_id"],
                "properties": {
                    "event_id": {"type": "string"},
                    "calendar_id": {"type": "string", "default": "primary"},
                },
            },
        ),
    ]

    @property
    def auth_headers(self) -> dict[str, str]:
        token = self.context.credentials.get("access_token", "") if self.context else ""
        return {"Authorization": f"Bearer {token}"}

    async def validate_connection(self) -> bool:
        resp = await self._get("/users/me/calendarList")
        return bool(resp.json())

    async def health(self) -> ProviderHealth:
        try:
            resp = await self._get("/users/me/calendarList")
            return ProviderHealth.healthy()
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    @action("list_calendars")
    async def list_calendars(self) -> dict[str, Any]:
        resp = await self._get("/users/me/calendarList")
        return resp.json()

    @action("create_event")
    async def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        resp = await self._post(f"/calendars/{calendar_id}/events", json_data=body)
        return resp.json()

    @action("update_event")
    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        **changes: Any,
    ) -> dict[str, Any]:
        resp = await self._patch(
            f"/calendars/{calendar_id}/events/{event_id}",
            json_data=changes,
        )
        return resp.json()

    @action("delete_event")
    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        await self._delete(f"/calendars/{calendar_id}/events/{event_id}")
        return {"deleted": True}

    @action("list_events")
    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"maxResults": max_results}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        resp = await self._get(f"/calendars/{calendar_id}/events", params=params)
        return resp.json()

    @action("get_event")
    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        resp = await self._get(f"/calendars/{calendar_id}/events/{event_id}")
        return resp.json()


ProviderCls = GoogleCalendarProvider
provider = GoogleCalendarProvider()
