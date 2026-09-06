# Webhooks

AgentForge Integrations provides an inbound webhook engine (receive, verify, dedupe, persist, dispatch) and an outbound delivery system (HMAC-sign, retry, dead-letter). The engine lives in `src/services/webhook_dispatcher.py`; HTTP routes are in `src/api/webhooks.py`.

## Subscription model

A subscriber registers a target URL for a provider and event set:

```sh
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "provider": "stripe",
    "target_url": "https://example.com/hooks/stripe",
    "secret": "my-webhook-secret",
    "events": ["payment_intent.succeeded"],
    "max_retries": 5
  }' \
  "http://localhost:8000/api/v1/webhooks/register"
```

- The `secret` is used to HMAC-sign outbound deliveries. If omitted, `WEBHOOK_DEFAULT_SECRET` (or a per-registration random token when unset) is used.
- Subscriptions are workspace-scoped and filtered by `provider` and `is_active`.
- List: `GET /api/v1/webhooks/subscriptions`. Deactivate: `DELETE /api/v1/webhooks/{webhook_id}`.

## Event pipeline

Inbound events arrive at `POST /api/v1/webhooks/{provider}` with an `X-Workspace-Id` header selecting the owning workspace.

```
 provider  ->  POST /webhooks/{provider}
                    |
                    v
            verify_signature        (per-provider)
                    |
                    v
               dedup (Redis)        (unique event id)
                    |
                    v
             persist event          (webhook_events)
                    |
                    v
             dispatch_event         (match active subscriptions)
                    |
                    v
        HMAC-sign + POST target     (X-AgentForge-Signature)
                    |
            +-------+--------+
            |                |
        2xx -> delivered   >=400 / error -> failed
```

Pipeline stages (`WebhookDispatcher`):

1. **Verify** — `verify_and_store` rejects providers that do not declare `supports_webhooks`, then calls the provider's `verify_signature(headers, payload)`. Providers claiming webhook support must implement signature verification (see Security below).
2. **Store** — the event is deduplicated and persisted to `webhook_events` with raw payload, filtered headers, event type, and a dedup key. Sensitive headers (`authorization`, `cookie`, `x-hub-signature`) are stripped before storage.
3. **Dispatch** — `dispatch_event` finds matching active subscriptions and delivers to each.
4. **Retry** — failed deliveries are retried by the Celery task `retry_webhooks_task` (beat: `retry-failed-webhooks-every-2m`) while `attempts < WEBHOOK_RETRY_MAX`.
5. **Dead-letter** — events that exceed the retry budget are marked `dead_lettered` by `dead_letter_task` (beat: `dead-letter-overflow-hourly`).

## Signature verification

- Inbound: each webhook-capable provider implements `verify_signature` (e.g. via `SignatureMixin.hmac_sha256`) and reads the provider-specific headers (`X-Hub-Signature`, `X-Stripe-Signature`, Twilio signature timestamp, etc.). Verification order is handled in `_assert_signature`; the provider may skip verification by leaving the method as a no-op, but production providers must override it.
- Outbound: every delivery is signed with HMAC-SHA256 over the exact JSON body using the subscription secret, and sent in:

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `X-AgentForge-Signature` | `sha256=<hex hmac>` |
| `X-AgentForge-Event` | the provider key |
| `X-AgentForge-Hook-Id` | the subscription id |

Subscribers should verify the `X-AgentForge-Signature` against the shared secret.

## Retry and backoff

- `WEBHOOK_RETRY_MAX` (default 5): maximum delivery attempts before dead-lettering.
- `WEBHOOK_RETRY_BACKOFF_BASE` (default 2): backoff base for spaced retries. Failed events are reprocessed by the beat task within the retry budget.
- A delivery is `successful` when the target returns a status `< 400`; otherwise it is a failure. `webhook_deliveries` records each attempt (status code, response body, success).

## Deduplication

- Redis (`WebhookDedup` with `webhook:dedup` namespace, TTL `REDIS_WEBHOOK_TTL`) detects duplicate events via a dedup key derived from provider-specific event id headers (`X-Hub-Zoom-Event-Id`, `X-GitHub-Event`, `X-Request-Id`, `X-Stripe-Trace-Id`, Twilio signature timestamp) or a `provider:event_type:id` fallback.
- The key is also unique in `webhook_events.dedup_key`.

## Operations

- List persisted events for the workspace: `GET /api/v1/webhooks/events?provider=...&limit=50&offset=0`.
- Manually re-dispatch a stored event to its subscribers: `POST /api/v1/webhooks/dispatch/{event_id}`. This replays the event regardless of its prior status.
- Admin views: `GET /api/v1/admin/webhooks` (subscriptions across all workspaces), `GET /api/v1/admin/stats` (event counts).
- Outbound Redis queue items can be pushed via `redis_service.enqueue` for worker consumption; scheduling is managed by Celery.
