#!/usr/bin/env sh
set -e

# Entrypoint for the API image. Reads WORKERS/PORT (or falls back to defaults)
# and starts gunicorn with the async Uvicorn worker on the app `main:app`.

WORKERS="${WORKERS:-4}"
PORT="${PORT:-8000}"

if [ "$1" = "alembic" ]; then
    shift
    exec alembic "$@"
fi

exec gunicorn main:app \
    --workers "${WORKERS}" \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT}" \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    --graceful-timeout 30
