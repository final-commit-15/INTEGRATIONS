# Deployment

## Docker Compose

`docker-compose.yml` defines the full stack:

| Service | Image / build | Notes |
| --- | --- | --- |
| `postgres` | `postgres:16-alpine` | Data in `postgres_data` volume, healthchecked with `pg_isready`. |
| `redis` | `redis:7-alpine` | AOF persistence in `redis_data` volume, healthchecked with `redis-cli ping`. |
| `migrate` | `Dockerfile` | Runs `alembic upgrade head`, depends on healthy Postgres, exits. |
| `api` | `Dockerfile` | Gunicorn + uvicorn worker via `docker/run.sh`, ports `${API_PORT:-8000}:8000`. |
| `worker` | `Dockerfile` | `celery -A tasks.celery_app worker --concurrency=4`. |
| `beat` | `Dockerfile` | `celery -A tasks.celery_app beat`. |

Start everything:

```sh
cp .env.example .env
docker compose up --build -d
```

- The `api` service depends on healthy Postgres and Redis and restarts on failure.
- Named volumes `postgres_data` and `redis_data` persist data across restarts.
- `Makefile` wrappers: `make docker-up`, `make docker-down`, `make docker-build`.

## Dockerfile

Multi-stage build (`Dockerfile`):
- Build stage installs the package into a venv (`.[prod]` includes gunicorn).
- Runtime stage installs `libpq5` (needed by asyncpg), drops to a non-root user (`uid 1001`), copies `src/` to `/app/src` (`PYTHONPATH=/app/src`), and runs `docker/run.sh`.
- `docker/run.sh` reads `WORKERS` (default 4) and `PORT` (default 8000), starts gunicorn with the async `UvicornWorker`.

## Production hardening

- **Secrets via the environment, not files**: pass `ENCRYPTION_KEY` and `JWT_SECRET` as secrets (e.g. Docker/Kubernetes secrets, or your orchestrator's secret management). Never commit `.env`.
- **`ENVIRONMENT=production`**:
  - Disables `/docs`, `/redoc`, and `/openapi.json` (`docs_url=None`, etc. in `src/main.py`).
  - Disables automatic table creation (`init_db` is only called outside production) — rely on Alembic.
  - An unset `ENCRYPTION_KEY` fails fast at startup instead of using the dev fallback.
  - Health endpoint reports `down` when any dependency is down (instead of `degraded`).
- **Gunicorn workers**: `WORKERS` (default 4) with the uvicorn async worker; tune to CPU count.
- **Security-sensitive settings**: set `CORS_ORIGINS`, `JWT_SECRET`, `CREDENTIAL_HASH_SALT`, per-provider secrets, and webhook secrets to real values.

## Migrations before deploy

Run migrations before starting the API:

```sh
# from the host:
PYTHONPATH=src python -m alembic upgrade head
# or via the compose migrate one-shot job:
docker compose up migrate
# or via make:
make migrate
```

`alembic/env.py` builds the engine from `settings.database_url` and uses `Base.metadata` for autogenerate. Revisions live in `alembic/versions/` (initial: `a24639ca1c27_initial`).

## Health checks

Container healthcheck (in `Dockerfile`) polls `GET /api/v1/health` for the API image. The compose `api` service also depends on healthy Postgres and Redis. Use these probes externally:

- `GET /api/v1/health` — liveness + dependency readiness.
- `GET /api/v1/health/live` — Kubernetes liveness.
- `GET /api/v1/health/ready` — Kubernetes readiness (DB + Redis).

## Scaling worker and beat

- Run `worker` on as many replicas as needed; each runs `celery -A tasks.celery_app worker`. Redis is the broker, so workers share the queue.
- Run exactly **one** `beat` process to avoid duplicate scheduled tasks.
- Task concurrency is set with `--concurrency` (compose uses 4). `task_acks_late=True` and `task_reject_on_worker_lost=True` reduce message loss.
- Tune `WORKERS` on the API and `webhook_retry_max`/backoff for delivery load.
