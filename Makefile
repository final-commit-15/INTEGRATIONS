SHELL := /bin/sh

PYTHON ?= python
VENV ?= .venv
PYTHONPATH := src
PIP := $(PYTHON) -m pip

.DEFAULT_GOAL := help

.PHONY: help install dev test lint format type docker-up docker-down docker-build migrate revision seed clean

help:
	@echo "agentforge-integrations targets:"
	@echo "  install      Install the package in editable mode (dev + prod extras)"
	@echo "  dev          Run uvicorn with reload (PYTHONPATH=src)"
	@echo "  test         Run pytest"
	@echo "  lint         Run ruff check"
	@echo "  format       Format with black + ruff check --fix"
	@echo "  type         Run mypy on src"
	@echo "  docker-up    Start the full stack (compose up --build)"
	@echo "  docker-down  Stop the stack"
	@echo "  docker-build Build the api image only"
	@echo "  migrate      Run alembic upgrade head"
	@echo "  revision     Autogenerate an alembic revision (revision=<name>)"
	@echo "  seed         Placeholder seed target"
	@echo "  clean        Remove bytecode/cache artifacts"

install:
	$(PIP) install -e ".[dev,prod]"

dev:
	PYTHONPATH=$(PYTHONPATH) uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .
	$(PYTHON) -m ruff check . --fix

type:
	$(PYTHON) -m mypy src

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-build:
	docker compose build api

migrate:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m alembic upgrade head

revision:
	@test -n "$(revision)" || (echo "usage: make revision revision=<name>"; exit 1)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m alembic revision --autogenerate -m "$(revision)"

seed:
	@echo "Seed target placeholder - implement with a script in scripts/ when ready."

clean:
	$(PYTHON) -c "import shutil, os; [shutil.rmtree(p, ignore_errors=True) for p in ['build','dist','.mypy_cache','.pytest_cache','.ruff_cache','htmlcov']]; [os.remove(f) for f in ['.coverage','coverage.xml'] if os.path.exists(f)]"
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -type f -delete 2>/dev/null || true
