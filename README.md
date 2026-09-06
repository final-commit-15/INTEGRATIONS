# AgentForge Integrations

Enterprise OAuth, provider execution, webhooks, and credential management microservice for the AgentForge platform.

![CI](.github/workflows/ci.yml)
![Python 3.12](.github/workflows/ci.yml)
![Coverage](.github/workflows/ci.yml)

## Feature highlights

- **23 connectors** auto-discovered from `src/providers/` via pkgutil (no hardcoded imports): Gmail, Google Drive, Google Calendar, Slack, GitHub, Notion, Discord, Jira, Trello, Airtable, HubSpot, Salesforce, Stripe, Twilio, SendGrid, Supabase, AWS S3, Dropbox, OneDrive, MongoDB, MySQL, Postgres, and generic webhook.
- **Universal OAuth2 manager** with PKCE, state lifecycle, refresh, and revocation.
- **Webhook engine** with signature verification, deduplication, retries, exponential backoff, and dead-lettering.
- **Encrypted credentials** at rest (Fernet) with key rotation.
- **Async SQLAlchemy + Postgres** with multi-tenant workspace isolation.
- **Celery background tasks** for token refresh, webhook retries, maintenance, and dead-lettering.
- **Rate limiting** via slowapi.
- **OpenTelemetry** tracing and metrics.
- **Docker Compose** for the full stack.

## Quickstart

### Docker Compose (Postgres + Redis + API + worker + beat)

```sh
cp .env.example .env
# fill in provider client ids/secrets and ENCRYPTION_KEY/JWT_SECRET
docker compose up --build -d
```

This starts Postgres, Redis, the `migrate` job (`alembic upgrade head`), the API, the Celery `worker`, and the Celery `beat` scheduler. The API is served on `http://localhost:8000`, docs at `http://localhost:8000/docs` (non-production).

### Local development

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev,prod]"
cp .env.example .env
make dev                         # uvicorn main:app --reload on :8000 (PYTHONPATH=src)
```

`.env` is loaded from the repo root. Copy `.env.example` and fill in real values; never commit `.env`. The key variables are `DATABASE_URL`, `REDIS_URL`, `ENCRYPTION_KEY`, `JWT_SECRET`, and per-provider client id/secret pairs.

## Environment variables

All settings live in `src/config.py` as typed Pydantic settings. See `.env.example` for the recommended block.

### Service and platform

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `agentforge-integrations` | Application name. |
| `APP_VERSION` | `1.0.0` | Version reported by health endpoints. |
| `ENVIRONMENT` | `development` | `development`, `staging`, or `production`. Disables `/docs`, `/redoc`, `/openapi.json`, and `init_db` autocreate in production. |
| `DEBUG` | `false` | When true, enables console logging renderer and verbose errors. |
| `LOG_LEVEL` | `INFO` | Log level. |
| `API_V1_PREFIX` | `/api/v1` | Route prefix for all routers. |
| `HOST` | `0.0.0.0` | Bind host. |
| `PORT` | `8000` | Bind port. |
| `WORKERS` | `4` | Gunicorn worker count (container). |
| `CORS_ORIGINS` | `["http://localhost:3000","http://localhost:8080"]` | Allowed CORS origins (comma or JSON list). |

### Database and Redis

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/agentforge` | Async SQLAlchemy URL. |
| `DATABASE_POOL_SIZE` | `10` | Connection pool size. |
| `DATABASE_MAX_OVERFLOW` | `20` | Max pool overflow. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker/backend/cache URL. |
| `REDIS_TOKEN_CACHE_TTL` | `300` | TTL for cached JSON entries (seconds). |
| `REDIS_WEBHOOK_TTL` | `86400` | TTL for webhook dedup keys (seconds). |

### Crypto and auth

| Variable | Default | Description |
| --- | --- | --- |
| `ENCRYPTION_KEY` | *(empty)* | Fernet-compatible key for credential encryption. In production an empty key fails fast at startup. In dev/test a deterministic fallback key is derived. |
| `ENCRYPTION_KEY_PREVIOUS` | *(empty)* | Comma-separated previous keys used during rotation; decrypts data under prior keys and supports re-encryption. |
| `CREDENTIAL_HASH_SALT` | *(empty)* | PBKDF2 salt for credential hashing. |
| `JWT_SECRET` | `change-me-in-production` | HS256 signing secret for access/refresh tokens. Change in production. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime. |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime. |

### Rate limiting

| Variable | Default | Description |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | Master switch for slowapi. |
| `RATE_LIMIT_DEFAULT` | `60/minute` | Default per-client limit. |
| `RATE_LIMIT_WEBHOOK` | `120/minute` | Webhook receive limit. |
| `RATE_LIMIT_OAUTH` | `10/minute` | OAuth endpoints limit. |

### Observability

| Variable | Default | Description |
| --- | --- | --- |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry SDK. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint. |
| `OTEL_SERVICE_NAME` | `agentforge-integrations` | OpenTelemetry service name. |
| `OTEL_TRACES_SAMPLE_RATIO` | `0.1` | Trace sampling ratio. |

### OAuth redirects

| Variable | Default | Description |
| --- | --- | --- |
| `OAUTH_REDIRECT_BASE_URL` | `http://localhost:8000` | Base used to build per-provider callback URIs. |
| `FRONTEND_URL` | `http://localhost:3000` | Where the OAuth callback redirects the browser after success/error. |

### Per-provider client credentials (grouped by provider)

| Provider | Variables |
| --- | --- |
| Google (Gmail, Drive, Calendar) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_API_KEY`, `GOOGLE_SCOPES` |
| Slack | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`, `SLACK_SCOPES` |
| GitHub | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_SCOPES` |
| Notion | `NOTION_CLIENT_ID`, `NOTION_CLIENT_SECRET`, `NOTION_SCOPES` |
| Discord | `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_SCOPES` |
| Jira | `JIRA_CLIENT_ID`, `JIRA_CLIENT_SECRET`, `JIRA_API_TOKEN`, `JIRA_SITE_URL`, `JIRA_SCOPES` |
| Trello | `TRELLO_API_KEY`, `TRELLO_API_TOKEN` |
| Airtable | `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID` |
| HubSpot | `HUBSPOT_CLIENT_ID`, `HUBSPOT_CLIENT_SECRET`, `HUBSPOT_SCOPES` |
| Salesforce | `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET`, `SALESFORCE_INSTANCE_URL`, `SALESFORCE_API_VERSION` |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY`, `TWILIO_API_SECRET`, `TWILIO_PHONE_NUMBER`, `TWILIO_MESSAGING_SERVICE_SID`, `TWILIO_VERIFY_SERVICE_SID`, `TWILIO_WEBHOOK_SECRET` |
| SendGrid | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SENDGRID_FROM_NAME` |
| Supabase | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| AWS S3 | `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `AWS_REGION`, `AWS_S3_BUCKET` |
| Dropbox | `DROPBOX_CLIENT_ID`, `DROPBOX_CLIENT_SECRET`, `DROPBOX_REFRESH_TOKEN` |
| OneDrive | `ONEDRIVE_CLIENT_ID`, `ONEDRIVE_CLIENT_SECRET`, `ONEDRIVE_TENANT_ID`, `ONEDRIVE_SCOPES` |
| MongoDB | `MONGODB_URI`, `MONGODB_DB_NAME` |
| Webhooks (outbound default) | `WEBHOOK_DEFAULT_SECRET`, `WEBHOOK_RETRY_MAX`, `WEBHOOK_RETRY_BACKOFF_BASE`, `WEBHOOK_POLL_INTERVAL_SECONDS` |

## API overview

Base URL: `http://localhost:8000/api/v1`. Authenticated endpoints require `Authorization: Bearer <access-token>`.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | none | Liveness + DB/Redis readiness. |
| GET | `/health/live` | none | Kubernetes liveness probe. |
| GET | `/health/ready` | none | Kubernetes readiness probe. |
| GET | `/oauth/providers` | none | List OAuth-enabled providers with auth metadata. |
| GET | `/oauth/connect/{provider}` | none | Generate OAuth authorization URL (query `workspace_id`). |
| GET | `/oauth/callback/{provider}` | none | Exchange auth code and store tokens, redirect to frontend. |
| POST | `/oauth/disconnect/{provider}` | optional | Revoke + disconnect a provider (query `workspace_id`). |
| GET | `/integrations` | none | List all providers with capability summaries. |
| GET | `/integrations/{provider}` | none | Metadata for one provider. |
| GET | `/integrations/{provider}/capabilities` | none | Executable capabilities for a provider. |
| GET | `/integrations/connections` | bearer | List connections for the resolved workspace. |
| POST | `/integrations/{provider}/execute` | bearer | Execute an action against a connected provider. |
| POST | `/integrations/{provider}/validate` | bearer | Validate a stored connection. |
| POST | `/integrations/{provider}/disconnect` | bearer | Deactivate a connection (no token revoke). |
| POST | `/credentials` | bearer | Store encrypted provider credentials. |
| PATCH | `/credentials/{provider}` | bearer | Update stored credentials. |
| GET | `/credentials` | bearer | List masked credential summaries. |
| DELETE | `/credentials/{provider}` | bearer | Delete stored credentials. |
| POST | `/webhooks/{provider}` | none* | Receive an inbound provider webhook (`X-Workspace-Id` header). |
| POST | `/webhooks/register` | bearer | Register a subscriber URL for verified events. |
| GET | `/webhooks/subscriptions` | bearer | List webhook subscriptions. |
| GET | `/webhooks/events` | bearer | List persisted webhook events (paginated). |
| DELETE | `/webhooks/{webhook_id}` | bearer | Deactivate a webhook subscription. |
| POST | `/webhooks/dispatch/{event_id}` | bearer | Manually re-dispatch a persisted event. |
| GET | `/admin/integrations` | admin | List connections across all workspaces. |
| GET | `/admin/webhooks` | admin | List webhook subscriptions across all workspaces. |
| GET | `/admin/logs` | admin | List audit log entries. |
| GET | `/admin/stats` | admin | Aggregate operational counters. |

`*` Inbound webhook receive requires the `X-Workspace-Id` header to select the owning workspace and is protected by provider signature verification.

## Connecting a provider (OAuth)

1. Generate an authorization URL for a workspace:

```sh
curl "http://localhost:8000/api/v1/oauth/connect/slack?workspace_id=ws_123"
```

Returns `{"data": {"authorization_url": "...", "state": "..."}}`.

2. Open the `authorization_url` in a browser, approve, and the user is redirected back to `{FRONTEND_URL}/integrations/{provider}?connected=1`.

3. List and use the connection:

```sh
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/integrations/connections?workspace_id=ws_123"

curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"send_message","payload":{"channel":"general","text":"hi"}}' \
  "http://localhost:8000/api/v1/integrations/slack/execute?workspace_id=ws_123"
```

## Webhooks

Providers that support webhooks receive events at `POST /api/v1/webhooks/{provider}` (see `docs/webhooks.md`).

To subscribe to verified events:

```sh
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"stripe","target_url":"https://example.com/hooks/stripe","secret":"my-webhook-secret","events":["payment_intent.succeeded"]}' \
  "http://localhost:8000/api/v1/webhooks/register"
```

Inbound events are signature-verified (per-provider headers), deduplicated, and persisted, then delivered to matching subscriptions with an HMAC-SHA256 signature in the `X-AgentForge-Signature` header. Failed deliveries are retried with exponential backoff (`WEBHOOK_RETRY_MAX`, `WEBHOOK_RETRY_BACKOFF_BASE`) until dead-lettered.

## Project structure

```
.
├── src/
│   ├── main.py               # FastAPI entrypoint, lifespan, rate limiter
│   ├── config.py             # Pydantic settings from env
│   ├── api/                  # health, auth(oauth), integrations, credentials, webhooks, admin
│   ├── providers/            # 23 provider packages + base contract + registry
│   ├── services/             # oauth, webhook dispatcher, encryption, credentials, etc.
│   ├── tasks/                # Celery app (tasks.celery_app) + token/webhook/maintenance tasks
│   ├── database/             # async SQLAlchemy engine, session, Base
│   ├── models/               # SQLAlchemy ORM models
│   ├── schemas/              # pydantic request/response models
│   ├── telemetry/            # OpenTelemetry + metrics
│   └── utils/                # retry, circuit breaker, security, context
├── tests/                    # api, unit, providers, integration
├── alembic/                  # migrations (env.py, script.py.mako, versions/)
├── docker/                   # run.sh entrypoint
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── alembic.ini
```

## Development

| Command | Description |
| --- | --- |
| `make install` | Install editable package (`dev` + `prod` extras). |
| `make dev` | Run uvicorn with reload (`PYTHONPATH=src`). |
| `make test` | Run pytest (`tests/`). |
| `make lint` | Run ruff check. |
| `make type` | Run mypy on `src`. |
| `make format` | Format with black + ruff --fix. |
| `make docker-up` / `make docker-down` | Start/stop the full compose stack. |
| `make migrate` | Run `alembic upgrade head`. |
| `make revision revision=<name>` | Autogenerate an Alembic migration. |

## Migrations

Migrations are managed with Alembic:

```sh
PYTHONPATH=src python -m alembic upgrade head
```

`alembic/env.py` builds the engine from `settings.database_url` and uses the ORM `Base.metadata` for autogenerate. The initial migration is `a24639ca1c27_initial`. In production, run `alembic upgrade head` before starting the API (or let the compose `migrate` job do it).

## Operations

### Celery tasks and beat schedule

Celery app: `tasks.celery_app` (broker/backend = Redis).

| Beat entry | Task | Schedule |
| --- | --- | --- |
| `refresh-oauth-tokens-hourly` | `tasks.token_tasks.refresh_ending_tokens_task` | hourly (minute 5) |
| `retry-failed-webhooks-every-2m` | `tasks.webhook_tasks.retry_webhooks_task` | every 120s |
| `dead-letter-overflow-hourly` | `tasks.webhook_tasks.dead_letter_task` | hourly (minute 35) |
| `cleanup-expired-oauth-states-daily` | `tasks.maintenance_tasks.cleanup_expired_states_task` | every 6h |
| `rotate-expired-credentials-daily` | `tasks.maintenance_tasks.rotate_expired_credentials_task` | every 24h |

Additional tasks: `agentforge.refresh_single_token`, `agentforge.dispatch_webhook`, `agentforge.cleanup_expired_credentials`.

### Health and admin

- Health: `GET /api/v1/health`, `GET /api/v1/health/live`, `GET /api/v1/health/ready`.
- Admin: `GET /api/v1/admin/stats` (connections, webhook subscriptions, events, audit logs), `GET /api/v1/admin/integrations`, `GET /api/v1/admin/webhooks`, `GET /api/v1/admin/logs`. Admin routes require the `admin` role on the bearer token.

## Docs index

- [Architecture](docs/architecture.md)
- [OAuth](docs/oauth.md)
- [Webhooks](docs/webhooks.md)
- [Adding providers](docs/providers.md)
- [Deployment](docs/deployment.md)
- [Operations](docs/operations.md)
- [Security](docs/security.md)
