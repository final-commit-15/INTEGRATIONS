# AgentForge Integrations

This repository provides the **external‑world execution layer** for the AgentForge ecosystem.  
It exposes a unified, secure, and reliable interface for agents to interact with:

- GitHub
- Jira
- Slack
- Microsoft Teams
- Documentation repositories

## Features
- Pluggable integration framework with registry and manager.
- OAuth2 / API‑key authentication with token refresh.
- Incoming webhook reception, validation, and dispatching.
- Retry policies, rate limiting, and structured logging.
- Secret encryption and secure credential handling.
- Containerised deployment with health checks.

## Quick Start
1. Copy `.env.example` to `.env` and fill in your credentials.
2. Run `poetry install` to install dependencies.
3. Start the webhook receiver: `poetry run uvicorn agentforge_integrations.webhooks.receiver:app --reload`
4. Use `IntegrationManager` in your agents to call external APIs.

## Testing
```bash
poetry run pytest