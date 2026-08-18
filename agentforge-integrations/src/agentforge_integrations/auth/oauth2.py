import asyncio
import logging
import time

import httpx

from ..core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class OAuth2Auth(httpx.Auth):
    """OAuth2 client credentials authentication with async token refresh."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        refresh_buffer: int = 60,
    ) -> None:
        self.token_url = token_url
        self.http_client_id = client_id
        self.http_client_secret = client_secret
        self.scope = scope
        self.refresh_buffer = refresh_buffer

        self._access_token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing it when necessary."""
        if (
            self._access_token
            and time.time() < (self._expires_at - self.refresh_buffer)
        ):
            return self._access_token

        async with self._lock:
            if (
                self._access_token
                and time.time() < (self._expires_at - self.refresh_buffer)
            ):
                return self._access_token

            await self._refresh_token()

            if self._access_token is None:
                raise AuthenticationError("OAuth2 access token unavailable")

            return self._access_token

    async def _refresh_token(self) -> None:
        data = {
            "grant_type": "client_credentials",
            "client_id": self.http_client_id,
            "client_secret": self.http_client_secret,
        }

        if self.scope:
            data["scope"] = self.scope

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data=data,
                timeout=30.0,
            )

            if resp.status_code != 200:
                logger.error(f"OAuth2 token error: {resp.text}")
                raise AuthenticationError(
                    f"OAuth2 failed: {resp.status_code}"
                )

            payload = resp.json()
            self._access_token = payload["access_token"]

            expires_in = payload.get("expires_in", 3600)
            self._expires_at = time.time() + expires_in

            logger.info("OAuth2 token refreshed.")

    async def async_auth_flow(self, request: httpx.Request):
        token = await self.get_access_token()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request