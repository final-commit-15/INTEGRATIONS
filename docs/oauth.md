# OAuth 2.0

AgentForge Integrations implements a universal OAuth2 manager (`src/services/oauth_service.py`) that serves every OAuth-enabled provider via the endpoint metadata declared on each provider class. It supports the authorization code grant with PKCE, state tokens, token storage and encryption, refresh, and revocation.

## Flow with PKCE

The browser redirect flow cannot carry a JWT, so `workspace_id` is a query parameter.

1. Request an authorization URL:

```sh
curl "http://localhost:8000/api/v1/oauth/connect/slack?workspace_id=ws_123"
```

```json
{
  "data": {
    "authorization_url": "https://slack.com/oauth/v2/authorize?client_id=...&state=...&code_challenge=...",
    "state": "…"
  }
}
```

- A random `state` token is generated and persisted in `oauth_states` along with the workspace, provider, scopes, PKCE `code_verifier`, redirect URI, and expiry.
- If the provider supports PKCE (`oauth_pkce`, default true), an S256 `code_challenge` derived from a `code_verifier` is added.
- `access_type=offline` and `prompt=consent` are appended so `refresh_token` is returned.

2. The user authorizes at the provider and the provider redirects to the callback:

```
{OAUTH_REDIRECT_BASE_URL}/oauth/callback/{provider}?code=...&state=...
```

3. `handle_callback` consumes the one-time `state`, exchanges the `code` for tokens (sending the `code_verifier` when PKCE is used), decrypts/encrypts credentials, and upserts an `integration_connections` row plus a `credentials` row. The browser is then redirected to:

```
{FRONTEND_URL}/integrations/{provider}?connected=1
```

On failure the browser is redirected to `{FRONTEND_URL}/integrations?error=1&reason=...`.

## State lifecycle

- `state` is a one-time token (`secrets.token_urlsafe(32)`), stored with a TTL of `OAUTH_STATE_TTL_SECONDS` (default 600).
- A state is only valid if it is unconsumed, unexpired, and matches the provider. `_consume_state` marks it consumed in the same request.
- Expired or consumed states are pruned by the Celery task `cleanup_expired_states_task` (beat: `cleanup-expired-oauth-states-daily`).

## Token storage and encryption

- Tokens are normalized into a common credential dict (access token, token type, expires in, scope, plus optional refresh token / id token), enriched by `oauth_enrich_token`.
- Credentials are encrypted with Fernet (`encryption_service.encrypt_credentials`) and stored in both `integration_connections.encrypted_credentials` and `credentials.encrypted_blob`.
- Decryption only succeeds under the current key or a listed previous key; failures raise `TokenExpired`.
- Redis caches JSON values under `REDIS_TOKEN_CACHE_TTL`.

## Refresh and rotation

- `refresh_access_token` reads the stored refresh token, performs a `grant_type=refresh_token` exchange, updates `access_token` (and optionally a new `refresh_token`), re-encrypts, and updates the connection expiry.
- The hourly beat task `refresh-oauth-tokens-hourly` (`refresh_ending_tokens_task`) refreshes active connections whose expiry is approaching or passed (batched, limit 200).
- A provider using `OAuthProviderMixin` gets a standard `refresh_token()` that calls the shared OAuth service.
- During execution, `IntegrationManager` catches `TokenExpired` on an action and transparently refreshes once before retrying.
- Credential rotation is handled by the daily `rotate-expired-credentials-daily` beat (`rotate_expired_credentials_task` → `credential_service.rotate_expired`).

## Revocation

`POST /api/v1/oauth/disconnect/{provider}?workspace_id=...` calls `revoke_token`:

- If the provider declares `oauth_revoke_url`, the access or refresh token is revoked remotely.
- Local tokens are always destroyed: the connection is marked `revoked`/inactive and `encrypted_credentials` is cleared.

To deactivate a connection without revoking the provider token, use `POST /api/v1/integrations/{provider}/disconnect` instead.

## Adding a new OAuth provider

See `docs/providers.md`. For OAuth, a provider class declares:

- `oauth_authorize_url` — authorization endpoint.
- `oauth_token_url` — token endpoint.
- `oauth_revoke_url` — optional revocation endpoint (empty = best-effort local revoke).
- `oauth_scopes` — default scope list.
- `oauth_pkce` — whether to use PKCE (default true).
- `oauth_token_header_auth` — send client credentials via HTTP basic auth (default true); when false they are sent in the request body.
- `oauth_enrich_token(token_response)` — optional hook to add provider-specific fields to stored credentials.

## Redirect URIs

- The default callback URI is `{OAUTH_REDIRECT_BASE_URL}/oauth/callback/{provider}`.
- A custom `redirect_uri` can be passed as a query param to `/oauth/connect/{provider}`; it is stored on the state and reused during token exchange.
- Register the exact callback URI in each provider's OAuth app console. `FRONTEND_URL` is where the browser is redirected after the exchange (not the provider redirect).
