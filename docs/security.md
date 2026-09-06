# Security

## Encryption at rest

- Credentials are encrypted with **Fernet** (AES-128-CBC + HMAC-SHA256) using `cryptography.fernet` (`src/services/encryption_service.py`).
- The current `ENCRYPTION_KEY` derives a Fernet key via PBKDF2-SHA256 (`CREDENTIAL_HASH_SALT`, 200k iterations). OAuth token pairs and API-key credentials are stored as encrypted JSON blobs in `integration_connections.encrypted_credentials` and `credentials.encrypted_blob`.
- In **production**, an unset `ENCRYPTION_KEY` fails fast at startup (`config.encryption_key_bytes`). In dev/test a deterministic fallback key keeps local runs working.
- Never store plaintext secrets in the database or logs.

## Key rotation

- `ENCRYPTION_KEY_PREVIOUS` accepts a comma-separated list of previous keys.
- Decryption tries the current key first, then previous keys in order. `re_encrypt` re-encrypts a token under the current key; `requires_rotation` detects tokens encrypted under an old key.
- Rotation procedure:
  1. Set the new key as `ENCRYPTION_KEY` and keep the old keys in `ENCRYPTION_KEY_PREVIOUS` so existing rows stay readable.
  2. Re-encrypt stored blobs under the new key (via `re_encrypt`) during a maintenance window.
  3. Remove `ENCRYPTION_KEY_PREVIOUS` entries once all data is migrated.
- Generate a key with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

## Credential masking

- API responses never return plaintext secrets. `mask_credentials` replaces sensitive values with a masked form (`***…last4`), applied to create/update/list credential endpoints.
- structlog redacts sensitive keys (`token`, `secret`, `password`, `authorization`, `api_key`, `cookie`, etc.) in all log output.

## JWT authentication

- Access and refresh tokens are HS256 JWTs signed with `JWT_SECRET` (default `change-me-in-production` — change it).
- Claims include `sub`, `ws` (workspace), `roles`, `type`, `iss`, and `aud` (both `APP_NAME`).
- `decode_token` enforces algorithm, issuer, audience, and token type. So `dependencies.get_principal` fails with `UnauthorizedError` on missing/invalid tokens.
- Normal endpoints require any authenticated principal; admin endpoints require the `admin` role.

## Rate limiting

- slowapi limits are enabled via `RATE_LIMIT_ENABLED` (default true). Keys are the authenticated principal or client IP (`dependencies.get_rate_limit_key`).
- Tiers: default (`RATE_LIMIT_DEFAULT`, `60/minute`), webhook (`120/minute`), OAuth (`10/minute`).
- Exceeding a limit returns HTTP 429 with an `ErrorResponse` body (`rate_limit_exceeded`).

## CORS

- Allowed origins come from `CORS_ORIGINS` (default `http://localhost:3000`, `http://localhost:8080`), parsed as a comma or JSON list. Set the real frontend origin(s) in production.

## Webhook signature verification

- **Inbound**: providers that set `supports_webhooks` must implement `verify_signature` (via `BaseWebhookProvider`/`SignatureMixin`) and read provider-specific headers. `BaseWebhookProvider.verify_signature` raises `NotImplementedError` by default, so providers cannot silently accept unsigned events.
- **Outbound**: every delivery is HMAC-SHA256 signed over the exact JSON body with the subscription secret and sent as `X-AgentForge-Signature: sha256=<hex>`. Subscribers independently recompute the HMAC and compare using a constant-time comparison.

## Secret handling guidance

- Never commit `.env`. `.gitignore` excludes `.env`, `.env.local`, `.env.production`, and `*.env` while keeping `.env.example`.
- `cp .env.example .env` locally; fill in production values through secrets management (Docker/Kubernetes secrets, vault, etc.).
- Rotate `JWT_SECRET`, provider client secrets, and webhook secrets regularly.
- Production must set `ENVIRONMENT=production` (disables `/docs`, `/redoc`, `/openapi.json`, and `init_db`) and a real `ENCRYPTION_KEY`; leaving the default JWT secret or empty encryption key in production is unsafe.
- Filter sensitive headers (e.g. `authorization`, `cookie`, `x-hub-signature`) before persisting webhook payloads/headers — the dispatcher already strips these.
