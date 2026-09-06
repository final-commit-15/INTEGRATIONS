# Adding a provider

Providers are auto-discovered. Adding a new one requires only a package under `src/providers/`, a class implementing the contract, a module-level `provider` instance, config keys, and (for OAuth/webhook) declared metadata. There is no central registration list.

## Provider contract

Every provider subclasses `BaseIntegrationProvider` (`src/providers/base.py`). The shared contract:

| Attribute / method | Purpose |
| --- | --- |
| `provider_key` | Unique string key (must match the directory name). |
| `name`, `description` | Human-readable metadata shown in the API. |
| `auth_type` | `oauth2`, `api_key`, `token`, or `none`. |
| `default_scopes` | Fallback scope list. |
| `capabilities` | List of `Capability(name, description, params_schema, examples)`. |
| `base_url`, `timeout`, `retry_policy` | HTTP client defaults. |
| `supports_webhooks` | Whether the provider accepts inbound webhooks. |
| `validate_connection()` | Abstract; verify stored credentials work. |
| `refresh_token()` | Abstract (or use `OAuthProviderMixin`); exchange a refresh token. |
| `health()` | Best-effort provider probe (defaults to `validate_connection`). |
| `execute_action(action_name, payload)` | Route to the matching `@action` handler. |

HTTP helpers `_get/_post/_patch/_put/_delete/_request` provide retries, a circuit breaker, metrics, and error translation (429 -> rate limit, 5xx -> provider unavailable).

## Directory layout

```text
src/providers/<key>/
├── __init__.py      # exposes ProviderCls and module-level `provider`
└── ...              # action implementations / submodules
```

`src/providers/<key>/__init__.py`:

```python
from providers.base import BaseIntegrationProvider, ProviderContext
from . import actions  # optional

class MyProvider(BaseIntegrationProvider):
    provider_key = "myprovider"
    name = "My Provider"
    description = "…"
    auth_type = "oauth2"
    capabilities = [...]

ProviderCls = MyProvider
provider = MyProvider()
```

The registry (`src/providers/registry.py`) imports each submodule by name and registers any `ProviderCls` subclass with a non-empty `provider_key`. The module-level `provider` attribute is used as the default instance.

## `action()` decorator

Mark provider methods as executable actions:

```python
from providers.base import action, ProviderContext

class MyProvider(BaseIntegrationProvider):
    @action("send_message")
    async def send_message(self, channel: str, text: str) -> dict:
        # self.context.require("access_token")  # validated credentials
        resp = await self._post("/api/messages", json_data={"channel": channel, "text": text})
        return resp.json()
```

- The decorator sets `_af_action`; `_collect_actions()` walks the MRO and builds a dispatch map, so `execute_action` routes `action_name` to the handler.
- `Capability` entries describe params and live in `capabilities`; payloads are validated against `params_schema.required` by `IntegrationManager.validate_payload`.

## ProviderContext.require

Actions run inside a `ProviderContext` carrying the decrypted `credentials` and `metadata`:

```python
ctx = self.context          # ProviderContext
creds = ctx.require("access_token", "refresh_token")  # raises CredentialInvalid if missing
```

## Health check

- Implement `validate_connection()` to verify stored credentials grant access (e.g. `GET /auth/user`).
- `health()` defaults to `validate_connection` and returns `ProviderHealth.ok/degraded/down`.
- `IntegrationManager.validate_connection` reports `valid`, health status, and masked credentials for a connection.

## OAuth metadata

For OAuth providers, subclass `OAuthProviderMixin` and declare (`src/docs/oauth.md` for full detail):

```python
class MyProvider(OAuthProviderMixin, BaseIntegrationProvider):
    oauth_authorize_url = "https://provider.com/oauth/authorize"
    oauth_token_url = "https://provider.com/oauth/token"
    oauth_revoke_url = "https://provider.com/oauth/revoke"   # optional
    oauth_scopes = ["read", "write"]
    oauth_pkce = True
    oauth_token_header_auth = True
```

Then add client credentials + scopes in `src/config.py` and to `provider_config()` and `.env.example`.

## Webhook support

Set `supports_webhooks = True` and implement signature verification:

```python
class MyProvider(BaseWebhookProvider):
    supports_webhooks = True

    @staticmethod
    def verify_signature(headers, payload) -> bool:
        return SignatureMixin.hmac_sha256(secret, body) == headers.get("X-Producer-Signature")
```

`BaseWebhookProvider` raises `NotImplementedError` by default so you cannot accidentally accept unsigned events.

## Conventions checklist

- Package directory matches `provider_key`.
- `__init__.py` exposes `ProviderCls` (a `BaseIntegrationProvider` subclass) and module-level `provider`.
- Credentials are read through `ProviderContext.require`; never hardcode secrets.
- Actions use the `@action` decorator and are documented in `capabilities`.
- Provider config (client id/secret/scopes/webhook secret) is added to `config.Settings` and `provider_config()`.
- For webhooks, `supports_webhooks = True` and a real `verify_signature`.
- Keep `base_url` correct; set a sensible `timeout` and `retry_policy`.

## Testing guidance

- Unit tests go in `tests/unit` (or `tests/providers`); integration tests in `tests/integration`.
- Use `respx` to mock `httpx` responses; build a provider instance with a synthetic `ProviderContext(provider, workspace_id, credentials=..., metadata=...)`.
- `pytest` runs with `asyncio_mode = auto`; tests use a sqlite test DB, `RATE_LIMIT_ENABLED=false`, and a deterministic dev encryption key (see `tests/conftest.py`).
- Mark external-service tests as `integration`/`slow` in pytest to avoid CI timeouts.
- Run `make test`, `make lint` (ruff), and `make type` (mypy, strict on `src`) before submitting.
