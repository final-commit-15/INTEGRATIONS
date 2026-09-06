# Operations

## Health and readiness

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Liveness + dependency readiness. Returns `status` (`ok`/`degraded`/`down`), `version`, `uptime_seconds`, and per-component (`database`, `redis`) status + latency. In production any down dependency makes the overall status `down`. |
| `GET /api/v1/health/live` | Kubernetes liveness probe (process is up). |
| `GET /api/v1/health/ready` | Kubernetes readiness probe (DB and Redis reachable). |

## Logging

Logging is configured in `src/logging_config.py` with structlog.

- **Development** (`DEBUG=true`): colorful console renderer.
- **Production**: JSON lines to stdout with ISO timestamps, logger name, log level, request/correlation IDs, and secret masking. Sensitive field names (`password`, `token`, `access_token`, `refresh_token`, `secret`, `client_secret`, `authorization`, `api_key`, `session_id`, `cookie`) are replaced with `[REDACTED]`.
- Request and correlation IDs are surfaced as `request_id`/`correlation_id` and echoed in `X-Request-Id`/`X-Correlation-Id` response headers.
- Noisy loggers (`uvicorn.access`, `sqlalchemy.engine`, `httpx`) are silenced to WARNING outside debug.

## Metrics

- **`/admin/stats`** (`GET /api/v1/admin/stats`, admin role) returns aggregate counters at rest: `connections`, `webhook_subscriptions`, `webhook_events`, `audit_logs`. No PII.
- **OpenTelemetry** (`src/telemetry/`), enabled via `OTEL_ENABLED` and exported over OTLP to `OTEL_EXPORTER_OTLP_ENDPOINT`:
  - Traces: instrumented FastAPI, httpx, and SQLAlchemy; `X-Processed-In-Ms` timing, `api.latency` histogram, `api.requests` counter.
  - Provider metrics: `provider.latency`, `provider.calls` (outcome).
  - Webhook metrics: `webhook.received`, `webhook.deliveries`, `webhook.retries`.
  - OAuth metrics: `oauth.refresh`.
  - `OTEL_TRACES_SAMPLE_RATIO` controls sampling (default 0.1).

## Celery maintenance

Celery app `tasks.celery_app` (broker/backend = `REDIS_URL`).

| Beat entry | Task | Schedule | What it does |
| --- | --- | --- | --- |
| `refresh-oauth-tokens-hourly` | `tasks.token_tasks.refresh_ending_tokens_task` | hourly (minute 5) | Refresh access tokens approaching or past expiry (batch 200). |
| `retry-failed-webhooks-every-2m` | `tasks.webhook_tasks.retry_webhooks_task` | every 120s | Re-dispatch failed events within retry budget. |
| `dead-letter-overflow-hourly` | `tasks.webhook_tasks.dead_letter_task` | hourly (minute 35) | Mark events past the retry budget as dead-lettered. |
| `cleanup-expired-oauth-states-daily` | `tasks.maintenance_tasks.cleanup_expired_states_task` | every 6h | Delete consumed/expired OAuth state rows. |
| `rotate-expired-credentials-daily` | `tasks.maintenance_tasks.rotate_expired_credentials_task` | every 24h | Flag expired credentials for re-auth. |

Manual tasks:

| Task | Purpose |
| --- | --- |
| `agentforge.refresh_single_token` | Force refresh of one workspace/provider token. |
| `agentforge.dispatch_webhook` | Dispatch a single persisted event by id. |
| `agentforge.cleanup_expired_credentials` | Remove expired credential records. |

Run one `beat` and scale `worker` replicas as needed.

## Admin endpoints

All admin routes require a bearer token whose claims include the `admin` role (`dependencies.require_admin`).

| Endpoint | Description |
| --- | --- |
| `GET /api/v1/admin/integrations` | List connections across all workspaces (filter by `provider`, paginated `limit`/`offset`). |
| `GET /api/v1/admin/webhooks` | List webhook subscriptions across all workspaces (paginated). |
| `GET /api/v1/admin/logs` | List audit log entries (filter by `provider`, `workspace_id`, paginated). |
| `GET /api/v1/admin/stats` | Aggregate counters (no PII). |

## Troubleshooting

**ENCRYPTION_KEY not configured**
- If `ENVIRONMENT=production`, startup fails fast with `RuntimeError("ENCRYPTION_KEY is not configured")` — set a Fernet key.
- In dev/test an empty key uses a deterministic fallback, so `init_db` and the test suite work out of the box.
- Generate a key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- After rotating a key, list the old one(s) in `ENCRYPTION_KEY_PREVIOUS` so existing rows remain decryptable; use re-encryption on stored blobs to migrate.

**sqlite vs postgres upsert**
- In `oauth_service._upsert_connection`, Postgres uses `INSERT ... ON CONFLICT DO UPDATE`; sqlite/dev/test uses a select-then-insert-or-update portable path. Behavior is identical, but only Postgres uses the efficient upsert. Do not rely on `ON CONFLICT` semantics against sqlite.

**Redis down**
- `/health` and `/health/ready` report `redis` as down.
- Webhook deduplication, token cache, and Celery broker/backend all depend on Redis; with Redis down, dedup and scheduling degrade.
- Redis connections are lazy: `get_redis()` creates the client on first use, keyed by `REDIS_URL`. Ensure the URL is reachable from API, worker, and beat.

**Webhook events not delivering**
- Confirm the provider declares `supports_webhooks` and `verify_signature` passes; an invalid signature raises `WebhookVerificationFailed`.
- Confirm a matching active subscription exists for the workspace/provider.
- Check `attempts` vs `WEBHOOK_RETRY_MAX`; events exceeding the budget are dead-lettered.
- Manually replay via `POST /api/v1/webhooks/dispatch/{event_id}`.
