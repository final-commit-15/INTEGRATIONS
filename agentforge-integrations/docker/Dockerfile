FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.0

COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main --no-root

COPY src/ ./src/

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "agentforge_integrations.webhooks.receiver:app", "--host", "0.0.0.0", "--port", "8000"]