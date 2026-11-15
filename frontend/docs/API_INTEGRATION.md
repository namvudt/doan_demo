# Existing API integration

This document describes the API that exists in this repository at branch
**fe**, revision **2e26ed7**. The implementation in api/main.py, api/schemas.py,
api/store.py, api/runtime.py, and api/worker.py is authoritative. The inherited
proposed frontend contract has been retired: API_CONTRACT.md now points here,
and the stale frontend-generated openapi.json has been removed.

## Two deliberately separate frontend modes

| Product mode | Current selector | Data source | Required behavior |
| --- | --- | --- | --- |
| UI Preview | VITE_FRONTEND_MODE=preview | Deterministic browser-only fixtures | Always show “UI Preview — Dữ liệu mô phỏng, chưa lưu lên backend”. Never issue a real guest token or imply server persistence. |
| API integration | VITE_FRONTEND_MODE=api | The FastAPI server below | Read model_mode from GET /api/v1/capabilities. Default to demo-only; live additionally requires VITE_ALLOW_LIVE_MODEL_CALLS=true, configured models and tab-local consent. Unsupported product features remain unavailable. |

The frontend selector does not change the backend. Backend demo mode is an
independent server setting and is proved only by the capabilities response.

The application must never switch to Preview because an HTTP request failed.
Preview identities, IDs, uploads, caches, and permissions must be isolated from
API-mode state. Switching mode clears or separates incompatible state.

## API address

VITE_API_BASE_URL defaults to /api/v1. In local development the Vite proxy
forwards it to the API server. For a direct cross-origin connection it may be
an absolute value such as http://127.0.0.1:8001/api/v1. Health endpoints are
under /health while application endpoints are under /api/v1.

If VITE_API_BASE_URL includes /api/v1, the HTTP adapter must still derive
/health/live and /health/ready from the server origin. Bearer tokens may be
attached only to that configured origin.

## Authentication and ownership

The existing backend has guest sessions, not email/password accounts.

1. Read GET /api/v1/capabilities.
2. If session_bootstrap_required is false, POST /api/v1/sessions with a short
   label.
3. Store the returned access_token in memory and send
   Authorization: Bearer &lt;token&gt; on protected requests.
4. If session_bootstrap_required is true, do not request or bundle the
   bootstrap token. Ask the operator for a pre-issued guest access token.
5. GET /api/v1/sessions/me validates the token.
6. DELETE /api/v1/sessions/me revokes it and requests cancellation of active
   owned runs.

The raw access token is returned only when the session is created. There is no
refresh endpoint, cookie login contract, account identity, role, or real admin
permission. Missing auth returns authentication_required; an expired, revoked,
or invalid token returns invalid_token. A resource owned by another session is
hidden behind 404 not_found.

The X-Bootstrap-Token and API_OPERATIONS_TOKEN values are server/operator
secrets. They must never appear in frontend configuration, source, logs,
screenshots, URLs, or VITE_* variables.

## Endpoint inventory

### Public system operations

| Method and path | Request | Success response | Notes |
| --- | --- | --- | --- |
| GET /health/live | None | 200 with status=ok | Process liveness only. |
| GET /health/ready | None | 200 or 503 with database and worker readiness | Does not validate model quality or quota. |
| GET /api/v1/capabilities | None | CapabilitiesView | Authoritative model_mode and upload limits. |
| GET /api/v1/samples | None | items containing sample_id and title | Samples are images, not heritage catalog records. |
| POST /api/v1/sessions | SessionCreate | 201 SessionCreated | May require operator-only X-Bootstrap-Token. |

CapabilitiesView contains api_version, config_hash, model_mode, model_configured,
missing_roles, max_upload_bytes, max_image_pixels, max_question_characters,
profiles, and session_bootstrap_required. model_configured reports configuration
readiness; it does not prove provider quota or successful generation.

SessionCreate accepts label from 1 to 80 characters. SessionCreated contains
session_id, access_token, token_type=bearer, and expires_at.

Protected session operations:

| Method and path | Response | Behavior |
| --- | --- | --- |
| GET /api/v1/sessions/me | session_id, label, expires_at | Validates and describes the current guest session. |
| DELETE /api/v1/sessions/me | 204 | Revokes the token and requests cancellation of queued/running owned runs. |

### Protected configuration and assets

| Method and path | Request | Success response | Important behavior |
| --- | --- | --- | --- |
| GET /api/v1/workflow | Bearer | version, stages, Mermaid diagram | Stage definitions are not individual model calls. |
| POST /api/v1/preflight | PreflightBody + Bearer | PreflightView | Readiness failures are normally HTTP 200 with ready=false. |
| POST /api/v1/assets | multipart file + Bearer | 201 AssetView | JPEG, PNG, or WebP content is normalized to PNG. |
| GET /api/v1/assets | limit, offset + Bearer | AssetView array | Bare array; no total count. |
| GET /api/v1/assets/{asset_id} | Bearer | AssetView | Owner-scoped. |
| GET /api/v1/assets/{asset_id}/content | Bearer | image/png | Fetch as an authorized Blob; a plain img URL has no Bearer header. |
| DELETE /api/v1/assets/{asset_id} | Bearer | 204 | Returns asset_in_use once any run references it. |
| POST /api/v1/samples/{sample_id}/assets | Bearer | 201 AssetView | Creates a new owner-scoped asset copy. |

AssetView contains asset_id, sha256, size_bytes, width, height, media_type,
created_at, and content_url.

PreflightBody accepts one to six roles from coordinator, visual, knowledge,
generation, aggregator, and judge, plus force. It checks model metadata and
credentials without generating content. It does not verify generation quota.

### Run lifecycle

| Method and path | Request | Success response | Idempotency |
| --- | --- | --- | --- |
| POST /api/v1/runs | RunCreate + Bearer | 202 RunView and Location | Idempotency-Key optional, strongly recommended. |
| GET /api/v1/runs | limit, offset, saved_only, execution_status | RunPage | Read-only. |
| GET /api/v1/runs/{run_id} | Bearer | RunView | Read-only. |
| POST /api/v1/runs/{run_id}/cancel | Bearer, no body | RunView | Repeat-safe; does not create a new run. |
| POST /api/v1/runs/{run_id}/retry | Bearer, no body | 202 child RunView and Location | Idempotency-Key required. Parent must be terminal. |
| POST /api/v1/runs/{run_id}/review | Bearer, no body | 202 review child RunView and Location | Idempotency-Key required. Reuses artifacts and executes Judge only. |

RunCreate is exactly:

~~~json
{
  "asset_id": "uuid",
  "question": "1 to 4000 characters",
  "audience": "tourist",
  "profile": "default",
  "parent_run_id": null
}
~~~

audience is tourist or student. profile currently accepts only default. Do not
send messages, conversation_id, heritage_id, account fields, or arbitrary
profile values.

parent_run_id is ownership-checked metadata. The full workflow does not use it
as conversational memory. Retry and Judge-only review create new run IDs and
preserve the original run.

RunView contains run_id, run_kind, request_id, trace_id, asset_id,
parent_run_id, question, audience, model_mode, execution_status, result_status,
bookmarked, event_count, error_type, timestamps, events_url, and result_url.

Execution status is one of queued, running, cancel_requested, succeeded, failed,
or cancelled. Result status is a separate content/evidence outcome: reviewed,
unverified, insufficient_evidence, out_of_scope, or failed. A successfully
executed workflow can still have an unverified, insufficient-evidence, or
out-of-scope result.

### Events

| Method and path | Request | Response |
| --- | --- | --- |
| GET /api/v1/runs/{run_id}/events/history | after, limit, include_draft + Bearer | EventPage JSON |
| GET /api/v1/runs/{run_id}/events | after, include_draft, optional Last-Event-ID + Bearer | text/event-stream |

EventPage contains run_id, items, next_after, and terminal. after is an
exclusive sequence cursor; limit is 1 to 500.

The SSE cursor is max(after, Last-Event-ID). Each persisted event frame has a
numeric id, an event name, and JSON data containing the EventView. Persisted
names include:

- run.queued, run.running, run.cancel_requested, run.cancelled, run.succeeded,
  and run.failed
- stage.running, stage.completed, stage.failed, and stage.skipped

Heartbeat frames are comments. If the session expires during a stream, the
server sends event=session.expired with an empty data object and closes.

Use authenticated fetch streaming, not native EventSource. The parser must:

- preserve partial UTF-8 and fragmented lines across chunks;
- ignore comment heartbeats;
- order and deduplicate by numeric sequence;
- reconnect with the last processed sequence;
- handle the session.expired control event;
- stop subscriptions when navigating or logging out;
- confirm terminal state from RunView/EventPage rather than treating EOF as
  success.

Reconnecting must not create a run. Closing a subscription does not cancel the
job. The stream contains workflow events, not token-by-token answer deltas.

Aggregate draft content is hidden by default. include_draft=true exposes it.
Other public stage artifacts can still be present. Do not reconstruct hidden
prompts or reasoning.

### Results and evidence

| Method and path | Request | Response |
| --- | --- | --- |
| GET /api/v1/runs/{run_id}/result | include_intermediate + Bearer | ResultView |
| GET /api/v1/runs/{run_id}/sources | Bearer | SourcesView |
| GET /api/v1/runs/{run_id}/steps | include_draft + Bearer | StepsView |
| GET /api/v1/runs/{run_id}/metrics | Bearer | MetricsView |
| GET /api/v1/runs/{run_id}/export | format=json or markdown, include_intermediate + Bearer | Attachment |

/result and /export return run_not_finished while active and result_unavailable
when a terminal run has no stored result. /sources, /steps, and /metrics can be
read before completion.

ResultView contains the projected answer, sources, plan, review, errors,
duration, token usage, and optional intermediate draft/stage snapshots. It does
not expose raw config, prompts, credentials, arbitrary graph state, or hidden
reasoning.

Sources contain source_id, title, safe HTTP(S) URL, type, snippet, retrieval
metadata, display number, and cited flag. They are run evidence, not editable
content-source records. Map-type navigation links are not verified locations.

StepsView.items is a dictionary keyed by workflow node. It is not an array of
LLM/tool calls. MetricsView.calls contains durable model attempts when
available, including role, provider, model, attempt status, retry/fallback,
timing, sanitized error diagnostics, and numeric usage. The backend exposes no
tool-call trace endpoint or call input/output artifacts.

### Saved runs and feedback

| Method and path | Request | Response |
| --- | --- | --- |
| PUT /api/v1/runs/{run_id}/bookmark | saved boolean + Bearer | RunView |
| POST or PUT /api/v1/runs/{run_id}/feedback | FeedbackBody + Bearer | FeedbackBody |
| GET /api/v1/runs/{run_id}/feedback | Bearer | FeedbackBody |

Feedback rating is helpful, needs_review, or unrated. note is at most 1500
characters. A missing record reads as unrated with an empty note.

A run bookmark is not a heritage favorite. The backend has no server-side
heritage favorite operation.

### Operations metrics

GET /api/v1/operations/metrics returns Prometheus text only when the server has
API_OPERATIONS_TOKEN configured and the caller supplies that separate
Operations Bearer value. It returns operations_disabled when not configured and
operations_unauthorized for missing or wrong credentials. A guest token does
not grant access. This endpoint is for server monitoring and must not be called
from the product frontend.

## Idempotency

Idempotency keys are owner-wide across all run operations, not scoped to a
single endpoint. The key length is 1 to 128 characters.

- Replaying the same key with the same normalized request returns the original
  run, including if it is already terminal.
- Reusing the key with a different request or run kind returns
  idempotency_conflict.
- A review key cannot be reused for a full retry.
- Preserve a key while retransmitting one intended mutation.
- Generate a new key for an explicit new run, retry, or review.
- Session creation, upload, and sample-to-asset creation are not idempotent.

## Error handling

Application errors use:

~~~json
{
  "error": {
    "code": "machine_readable_code",
    "message": "Safe message",
    "request_id": "uuid",
    "details": {}
  }
}
~~~

details is optional. X-Request-ID is present on responses and should be shown
in diagnostic UI without logging credentials or private content.

Important codes include:

- authentication_required, invalid_token, bootstrap_required, session_limit
- body_too_large, image_too_large, normalized_image_too_large, invalid_image,
  asset_limit, asset_missing, asset_in_use, sample_not_found
- not_found, validation_error, idempotency_conflict, daily_limit, queue_limit
- run_active, mode_mismatch, review_artifacts_missing
- run_not_finished, result_unavailable
- model_not_configured, credential_invalid, permission_denied,
  model_not_found, provider_unavailable

Preserve user drafts on recoverable failures. There is no Retry-After header,
so do not implement blind retry loops.

## Security requirements

- Keep guest tokens in memory. If tab persistence is deliberately added,
  document the exposure and clear it on logout.
- Never persist passwords; the backend has no password contract.
- Never put Bearer, bootstrap, operations, provider, or database credentials in
  query strings or VITE_* variables.
- Attach Authorization only to the configured API origin.
- Render answer Markdown without raw HTML execution.
- Open external source links with safe schemes and rel=noopener noreferrer.
- Fetch protected asset content as a Blob and revoke object URLs when no longer
  needed.
- Respect explicit CORS origins. Do not change backend security to work around
  a frontend configuration error.
- /api/v1/operations/metrics is operator-only and is not an admin frontend API.

## Backend demo safety

The launcher argument --demo changes only API_MODEL_MODE for that process. It
does not isolate the database, assets, or queue. Each stored run retains its
own model_mode and config snapshot, and the worker executes that stored mode.
Use the isolated environment in TESTING.md. Never point a demo integration test
at an existing database, asset directory, worker queue, or production volume.
