"""Provider base contract.

Every integration provider subclasses :class:`BaseIntegrationProvider` and
implements the lifecycle methods required by the registry, execution engine,
OAuth manager, and webhook dispatcher.

Adding a new provider requires only:
1. A package under ``src/providers/<name>/``,
2. A class implementing this contract and a module-level ``provider`` instance,
3. Configuration keys in :mod:`config`,
4. A registration entry (auto-discovered).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from config import settings
from exceptions import (
    ActionNotFound,
    CredentialInvalid,
    IntegrationError,
    ProviderUnavailable,
    RateLimitExceeded,
)
from telemetry import metrics
from utils.circuit_breaker import CircuitBreaker, breaker_for
from utils.retry import RetryPolicy, with_retry

AuthType = Literal["oauth2", "api_key", "token", "none"]


@dataclass(frozen=True)
class Capability:
    """Declarative description of an executable action."""

    name: str
    description: str
    params_schema: dict[str, Any]
    examples: list[str] = field(default_factory=list)


@dataclass
class ProviderContext:
    """Resolved, decrypted context for a single connection execution."""

    provider: str
    workspace_id: str
    credentials: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def require(self, *keys: str) -> dict[str, Any]:
        missing = [k for k in keys if not self.credentials.get(k)]
        if missing:
            raise CredentialInvalid(
                f"missing required credential fields: {', '.join(missing)}",
                provider=self.provider,
            )
        return self.credentials


@dataclass(frozen=True)
class ProviderHealth:
    status: Literal["ok", "degraded", "down"]
    latency_ms: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def healthy(cls, latency_ms: float | None = None, detail: dict[str, Any] | None = None) -> ProviderHealth:
        return cls(status="ok", latency_ms=latency_ms, detail=detail or {})

    @classmethod
    def down(cls, detail: dict[str, Any] | None = None) -> ProviderHealth:
        return cls(status="down", detail=detail or {})


def action(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator marking a provider method as an executable action."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func._af_action = name  # type: ignore[attr-defined]
        return func

    return decorator


class BaseIntegrationProvider(ABC):
    """Abstract base class shared by every integration provider."""

    provider_key: str = ""
    name: str = ""
    description: str = ""
    auth_type: AuthType = "oauth2"
    default_scopes: list[str] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    base_url: str = ""
    timeout: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    supports_webhooks: bool = False

    # OAuth endpoint metadata (used by the universal OAuth manager).
    oauth_authorize_url: str = ""
    oauth_token_url: str = ""
    oauth_revoke_url: str = ""
    oauth_scopes: list[str] = field(default_factory=list)
    oauth_pkce: bool = True
    oauth_token_header_auth: bool = True

    def oauth_enrich_token(self, token_response: dict[str, Any]) -> dict[str, Any]:
        """Hook for providers to enrich stored credentials during token exchange."""
        return {}

    def __init__(
        self,
        context: ProviderContext | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.context = context
        self._client = client
        self.breaker: CircuitBreaker = breaker_for(self.provider_key)
        self.retry_policy = type(self).retry_policy
        self._dispatch: dict[str, Callable[..., Any]] = self._collect_actions()

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    @property
    def base_headers(self) -> dict[str, str]:
        return {
            "User-Agent": f"agentforge-integrations/{settings.app_version}",
            "Accept": "application/json",
        }

    @property
    def auth_headers(self) -> dict[str, str]:
        """Provider-specific authorization headers. Override per provider."""
        return {}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self.timeout)
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            kwargs: dict[str, Any] = {}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                headers=self.base_headers,
                **kwargs,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Core request helper with retries + circuit breaker + metrics
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        data: Any = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
        allowed_status: tuple[int, ...] = (),
        retry: bool = True,
    ) -> httpx.Response:
        self.breaker.allow_request()
        full_headers = {**self.base_headers, **self.auth_headers}
        if headers:
            full_headers.update(headers)

        async def _do() -> httpx.Response:
            resp = await self.client.request(
                method,
                url,
                params=params,
                json=json_data,
                data=data,
                files=files,
                headers=full_headers,
            )
            if resp.status_code == 429:
                raise RateLimitExceeded(
                    "provider rate limit exceeded",
                    provider=self.provider_key,
                    details={"status_code": resp.status_code},
                )
            if resp.status_code in {500, 502, 503, 504}:
                raise ProviderUnavailable(
                    "provider returned a server error",
                    provider=self.provider_key,
                    details={"status_code": resp.status_code},
                )
            if resp.status_code >= 400 and resp.status_code not in allowed_status:
                await resp.aread()
                raise IntegrationError(
                    f"provider request failed: HTTP {resp.status_code}",
                    provider=self.provider_key,
                    details={"status_code": resp.status_code, "body": _safe_preview(resp.text)},
                )
            return resp

        if retry:
            try:
                resp = await with_retry(_do, policy=self.retry_policy)
            except Exception:
                self.breaker.record_failure()
                raise
        else:
            try:
                resp = await _do()
            except Exception:
                self.breaker.record_failure()
                raise

        self.breaker.record_success()
        return resp

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def _patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PATCH", url, **kwargs)

    async def _put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PUT", url, **kwargs)

    async def _delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("DELETE", url, **kwargs)

    # ------------------------------------------------------------------
    # Abstract lifecycle contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Verify stored credentials still grant access (e.g. GET /auth/user)."""

    async def connect(self) -> None:
        """Any one-time setup after successful OAuth exchange. Default no-op."""

    async def disconnect(self) -> None:
        """Release provider-local resources. Default closes the HTTP client."""
        await self.aclose()

    @abstractmethod
    async def refresh_token(self) -> bool:
        """Exchange a refresh token for a new access token. Return False when
        the refresh token is expired/revoked."""

    async def health(self) -> ProviderHealth:
        """Best-effort provider health probe. Default relies on validate_connection."""
        try:
            valid = await self.validate_connection()
        except Exception as exc:
            metrics.record_provider_call(self.provider_key, False, 0.0)
            return ProviderHealth.down(detail={"error": str(exc)})
        if valid:
            return ProviderHealth.healthy()
        return ProviderHealth.down(detail={"reason": "invalid connection"})

    # ------------------------------------------------------------------
    # Action routing / capabilities
    # ------------------------------------------------------------------

    def _collect_actions(self) -> dict[str, Callable[..., Any]]:
        """Collect all methods decorated with :func:`action` across the MRO."""
        dispatch: dict[str, Callable[..., Any]] = {}
        for cls in reversed(type(self).__mro__):
            for attr_name, attr in vars(cls).items():
                action_name = getattr(attr, "_af_action", None)
                if action_name and callable(attr):
                    dispatch[action_name] = attr.__get__(self, type(self))
        return dispatch

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": cap.name,
                "description": cap.description,
                "params_schema": cap.params_schema,
                "examples": cap.examples,
            }
            for cap in self.capabilities
        ]

    async def execute_action(self, action_name: str, payload: dict[str, Any]) -> Any:
        """Route an action name + payload to the handler, recording metrics."""
        handler = self._dispatch.get(action_name)
        if handler is None:
            raise ActionNotFound(
                f"action {action_name!r} not supported by provider {self.provider_key}",
                provider=self.provider_key,
            )
        import time

        start = time.perf_counter()
        try:
            result = await handler(**payload)
            metrics.record_provider_call(self.provider_key, True, (time.perf_counter() - start) * 1000)
            return result
        except Exception:
            metrics.record_provider_call(self.provider_key, False, (time.perf_counter() - start) * 1000)
            raise

    def get_capability(self, name: str) -> Capability | None:
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_credentials(self, credentials: dict[str, Any]) -> None:
        if self.context:
            self.context.credentials.update(credentials)

    async def _response_json(self, resp: httpx.Response) -> dict[str, Any]:
        return resp.json()


def _safe_preview(body: str, *, limit: int = 200) -> str:
    if not body:
        return ""
    return body[:limit] + ("..." if len(body) > limit else "")


class OAuthProviderMixin:
    """Standard refresh_token implementation for OAuth2 providers.

    Providers that subclass this don't need to re-implement refresh logic;
    they only declare their ``oauth_*`` class attributes.
    """

    async def refresh_token(self) -> bool:
        if self.context is None:
            return False
        from database.database import async_session_factory
        from services.oauth_service import get_oauth_service

        try:
            async with async_session_factory() as session:
                try:
                    credentials, _ = await get_oauth_service().refresh_access_token(
                        provider=self.provider_key,
                        workspace_id=self.context.workspace_id,
                        session=session,
                    )
                finally:
                    await session.close()
            self._set_credentials(credentials)
            return True
        except Exception:
            return False


class BaseWebhookProvider(BaseIntegrationProvider, ABC):
    """Mixin contract for providers that receive inbound webhook events.

    While webhooks are routed through the dispatcher, providers opt in via
    this base class so the registry can advertise ``webhook_supported``.
    """

    webhook_parser: Callable[[dict[str, Any], dict[str, str]], dict[str, Any]] | None = None

    @staticmethod
    def verify_signature(headers: dict[str, str], payload: dict[str, Any]) -> bool:
        """Override per provider. A no-op (accept) by default — insecure; always
        override in production providers that claim ``supports_webhooks``."""
        raise NotImplementedError("webhook providers must implement signature verification")


class SignatureMixin:
    """Reusable HMAC-SHA256 signature helpers for webhook verification."""

    @staticmethod
    def hmac_sha256(secret: str, body: str) -> str:
        import hashlib
        import hmac

        return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
