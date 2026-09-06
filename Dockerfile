# syntax=docker/dockerfile:1.7
#
# Production multi-stage build for agentforge-integrations.
# Build runs as root; runtime drops to a non-root user.

# ---------- Build stage ----------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Copy project metadata and source. `src` must exist before installing the
# package because setuptools resolves package-dir = { "" = "src" }.
COPY pyproject.toml README.md ./
COPY src ./src

# Install build tooling + the package (with the `prod` extra -> gunicorn) into
# a venv prefix that the runtime stage reuses.
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install ".[prod]"

# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime OS deps (asyncpg). Kept minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN groupadd --gid 1001 app \
    && useradd --uid 1001 --gid app --shell /usr/sbin/nologin --create-home app

WORKDIR /app

# Copy the virtualenv from the build stage.
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source into /app/src (bare modules live here).
COPY --from=build /build/src /app/src

# Entrypoint scripts.
COPY docker/run.sh /docker/run.sh
RUN chmod +x /docker/run.sh

USER app

EXPOSE 8000

# WORKERS and PORT are read from the environment by run.sh (defaults below).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/opt/venv/bin/python", "-c", "import urllib.request,sys,os; r=urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/api/v1/health', timeout=5); sys.exit(0 if r.status < 500 else 1)"]

ENTRYPOINT ["/docker/run.sh"]
