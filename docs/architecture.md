# Architecture

AgentForge Integrations is an async FastAPI microservice that provides provider execution, OAuth2, webhooks, and encrypted credential management for the AgentForge platform. It is multi-tenant (per-`workspace_id` isolation), event-driven (Celery over Redis), and fully containerized.

## System components

| Component | Responsibility | Entry point |
| --- | --- | --- |
| API (`api` service) | HTTP surface: integration execution, OAuth, credentials, webhooks, admin | `src/main.py` (`main:app`), gunicorn + uvicorn worker |
| Provider registry | Auto-discovers provider packages from `src/providers/` | `src/providers/registry.py` |
| OAuth service | Authorization URL, token exchange, refresh, revoke, state + PKCE | `src/services/oauth_service.py` |
| Webhook dispatcher | Verify, dedupe, store, dispatch, retry, dead-letter | `src/services/webhook_dispatcher.py` |
| Encryption service | Fernet encrypt/decrypt with key rotation | `src/services/encryption_service.py` |
| Credential service | Encrypted credential CRUD + rotation | `src/services/credential_service.py` |
| Integration manager | Resolves connections/credentials and executes provider actions | `src/services/integration_manager.py` |
| Redis service | Caching, webhook dedup, distributed locks, job queues | `src/services/redis_service.py` |
| Background tasks | Token refresh, webhook retry/dead-letter, state/credential cleanup | `src/tasks/` (Celery app `tasks.celery_app`) |
| Telemetry | OpenTelemetry tracing + custom metrics | `src/telemetry/` |
| Database | Async SQLAlchemy ORM over Postgres (sqlite for dev/tests) | `src/database/database.py`, models in `src/models/` |

## Request lifecycle

1. A request enters through the ASGI app (`main:app`). Middleware (`src/middleware.py`) assigns request/correlation IDs, binds them to the structlog context, records API latency/request metrics, and converts exceptions into a consistent `ErrorResponse` envelope.
2. The `slowapi` limiter (default `60/minute`) runs first and returns `429` when exceeded, keyed by authenticated principal or client IP.
3. CORS is applied from `CORS_ORIGINS`. A `X-Processed-In-Ms` header is added to every response.
4. FastAPI routes requests to routers mounted under `/api/v1` (`src/api/__init__.py`): health, oauth, integrations, credentials, webhooks, admin.
5. Protected endpoints resolve the principal from the `Authorization: Bearer` JWT via `dependencies.get_principal`; admin endpoints require the `admin` role.
6. The app lifespan (`src/main.py`) configures telemetry/logging, loads the provider registry (`registry.load()`), and — outside production — calls `init_db()`. On shutdown it disposes the DB engine, closes Redis, and shuts down telemetry.

## Provider registry auto-discovery

- The registry (`src/providers/registry.py`) scans `src/providers/` with `pkgutil.iter_modules` and imports every package.
- A package is registered if it exposes `ProviderCls`, a subclass of `BaseIntegrationProvider` with a non-empty `provider_key`.
- Import failures are logged and skipped; the app never crashes because of one broken provider.
- Each provider package also exposes a module-level `provider` instance. There is no hardcoded provider list — adding a folder registers a provider automatically.
- There are 23 provider packages. The registry is populated during lifespan, and the count is stored in `app.state.provider_count`.

## DB schema overview

All tables are defined in `src/models/__init__.py` on the `Base` declarative base. Every tenant-scoped row carries a `workspace_id`; migrations live in `alembic/`.

| Table | Purpose |
| --- | --- |
| `workspaces` | Tenant workspaces owning connections, credentials, and webhooks. |
| `integration_connections` | A workspace-provider connection with encrypted credentials, scopes, status, expiry. Unique on `(workspace_id, provider)`. |
| `credentials` | Encrypted credential blobs (Fernet) with an optional hash for fast lookup. Unique on `(workspace_id, provider, name)`. |
| `oauth_states` | One-time OAuth state tokens with PKCE verifier, scopes, redirect URI, expiry, consumed flag. |
| `webhook_subscriptions` | Registered subscriber targets (URL + secret + event filter + retry budget). |
| `webhook_events` | Persisted inbound events with raw payload, headers, delivery status, attempt count. Unique on `dedup_key`. |
| `webhook_deliveries` | Per-attempt outbound delivery records (status code, response body, success). |
| `integration_audit_logs` | Immutable audit trail for security-sensitive integration events. |

## Service layer

- **Encryption** (`encryption_service.py`): Fernet (AES-128-CBC + HMAC-SHA256). The current `ENCRYPTION_KEY` encrypts new data; `ENCRYPTION_KEY_PREVIOUS` enables reading and rotating data under prior keys.
- **OAuth** (`oauth_service.py`): builds authorization URLs (state + PKCE S256), exchanges authorization codes, persists encrypted tokens, refreshes with re-encryption, and revokes where the provider exposes a revoke endpoint. Uses PostgreSQL upsert on `(workspace_id, provider)` with a portable path for sqlite.
- **Webhooks** (`webhook_dispatcher.py`): verifies signatures per provider, dedupes via Redis (`WebhookDedup`), persists events, dispatches to matching active subscriptions with HMAC-SHA256 signing, retries with budget, and dead-letters overflow.
- **Integration manager** (`integration_manager.py`): lists/fetches connections, decrypts credentials, builds provider instances from the registry, validates payloads against capability schemas, executes actions, and performs on-demand token refresh on expiry.
- **Credentials** (`credential_service.py`): encrypted CRUD scoped to a workspace plus `rotate_expired` for the maintenance task.

## Background tasks

Celery is configured in `src/tasks/__init__.py` (`tasks.celery_app`) with Redis as broker and backend. Async task functions are wrapped with the `async_task` decorator which runs each coroutine in its own event loop.

```
                         +-------------------------------------+
                         |  Celery beat scheduler              |
                         +------------------+------------------+
                                            |
     +----------------+--------+-----------+----------------+----------------+
     |                |        |           |                |                |
reg refresh   retry_failed   dead_letter  cleanup_states  rotate_creds
(tasks.token) (tasks.webhook)(tasks.webhook)(tasks.maint)  (tasks.maint)
     |                |        |           |                |
     v                v        v           v                v
  OAuthService   WebhookDispatcher     Cleanup         CredentialService
```

| Task function | Beat name | Runs |
| --- | --- | --- |
| `refresh_ending_tokens_task` | `refresh-oauth-tokens-hourly` | hourly |
| `retry_webhooks_task` | `retry-failed-webhooks-every-2m` | every 120s |
| `dead_letter_task` | `dead-letter-overflow-hourly` | hourly |
| `cleanup_expired_states_task` | `cleanup-expired-oauth-states-daily` | every 6h |
| `rotate_expired_credentials_task` | `rotate-expired-credentials-daily` | every 24h |

Manual/on-demand tasks: `refresh_single_token_task`, `dispatch_webhook_task`, `cleanup_expired_credentials_task`.

## Security model

- **Encryption at rest**: credentials stored as Fernet tokens (`encryption_service.encrypt_credentials`). In production an unset `ENCRYPTION_KEY` fails fast at startup (`config.encryption_key_bytes`).
- **Key rotation**: previous keys listed in `ENCRYPTION_KEY_PREVIOUS` decrypt legacy rows; `re_encrypt`/`requires_rotation` support migration.
- **Authentication**: JWT access tokens (HS256, `JWT_SECRET`) resolved via `security.decode_token`; workspace comes from the `ws` claim.
- **Authorization**: any authenticated principal for normal routes; the `admin` role for admin routes.
- **Credential masking**: secret values are masked (`***…`) in API responses and log output. structlog redacts sensitive fields.
- **Webhook verification**: inbound provider signatures verified via `BaseWebhookProvider.verify_signature`/`SignatureMixin`; outbound delivery signed with HMAC-SHA256 (`X-AgentForge-Signature`).
- **Rate limiting**: slowapi limits keyed by principal or IP across three tiers (default, webhook, OAuth).
- **Multi-tenancy**: every resource is filtered by `workspace_id`.
