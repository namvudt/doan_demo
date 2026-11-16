# Existing API integration

This document describes the implemented contract in the current fe workspace.
OpenAPI and the router modules in api/main.py, api/accounts.py,
api/conversations.py, api/catalog.py, api/content.py and api/lifecycle.py are
authoritative. The contract contains **81 operations**, Swagger **1.2.0** and
Postman **84 requests**. HTTP keeps the /api/v1 prefix; evidence results use
schema version 2 and older results remain readable as version 1. Database head
is 0009_runtime_state. Check X-Backend-Build/capabilities for the running image.

## Frontend modes and address

| Mode | Data and behavior |
| --- | --- |
| UI Preview | Isolated browser fixtures; permanent Preview label; never implies DB persistence or real roles |
| API | FastAPI data, real guest/account identity, capability discovery and server-enforced ownership |

VITE_API_BASE_URL defaults to /api/v1 through the Vite proxy. A direct
cross-origin URL may include that prefix; health URLs are derived from the
server origin. Bearer tokens must only go to the configured origin.

Backend model_mode is independent from the frontend mode selector. API failures
never switch to Preview or substitute fixture records. Provider/operations/
bootstrap secrets must not appear in VITE variables, URLs, screenshots or logs.

## Authentication and ownership

Guest sessions remain supported: POST /sessions issues one bearer token,
GET /sessions/me validates it and DELETE /sessions/me revokes it/cancels owned
guest work. If bootstrap is required, the browser uses an operator-issued guest
token; it never obtains or embeds X-Bootstrap-Token.

| Implemented account operation | Behavior |
| --- | --- |
| POST /accounts | Email/password/display_name registration; server grants user role only |
| POST /auth/sessions | Password login, opaque access and refresh tokens |
| POST /auth/refresh | Rotate refresh/access session tokens |
| DELETE /auth/sessions/current | Revoke the current account session |
| GET/PATCH /users/me | Account profile; PATCH requires expected version |
| POST /users/me/password | Change password using current password |
| PUT /operations/accounts/{account_id}/role | Existing admin bearer or server operations bearer; version checked |

Passwords use scrypt; tokens are stored as hashes. Login/registration have DB
rate limits. Account owner IDs remain stable across login sessions, so runs
and assets can be accessed after another login. Revoking one account session
does not revoke every device or convert the account owner into a guest.

React keeps access/refresh credentials in tab memory. Refresh is an explicit
supported operation; passwords/provider keys are not persisted in frontend
storage. Account profile/registration/login, conversation selection/memory and
heritage favorites have API UI flows. Full web CMS/admin workflows are separate
future UI work; a Preview role toggle is never server authorization.

Unowned resources are hidden behind 404. Editorial roles are checked against
the current account record, including disabled status. Editorial REST accepts
AccountBearer with editor/admin or OperationsBearer. Role assignment requires
admin or operations, and the server operations secret never belongs in a browser.

## Discovery and API inventory

GET /capabilities publishes model_mode, readiness/config hash, profiles,
accuracy policy, limits, bootstrap requirement and boolean features. Current
feature keys include heritage_catalog, heritage_coordinates, heritage_media,
heritage_asset_import, accounts, conversations, heritage_favorites,
content_editorial, run_retention and durable_node_recovery. Missing/false flags
are unsupported; configured models and healthy workers do not prove accuracy
or generation quota.

Paths below are relative to /api/v1 unless they start with /health.

| Group | Implemented surface |
| --- | --- |
| System | GET /health/live, /health/ready, /capabilities, /workflow, /samples; POST /preflight |
| Assets | POST/GET /assets; GET/DELETE /assets/{asset_id}; GET /assets/{asset_id}/content; POST /samples/{sample_id}/assets |
| Catalog | GET /heritages, /heritages/{id}, media content, /context, /sources; POST catalog media /assets bridge |
| Catalog metadata | POST /operations/heritages; PUT /operations/heritages/{id}, version checked |
| Runs | POST/GET /runs; GET/DELETE /runs/{id}; POST cancel/retry/review/clarification/resume |
| Run observation | GET result/sources/evidence/regions/{region_id}/image/clarification/steps/metrics/export/recovery/events/events/history |
| Feedback | PUT /runs/{id}/bookmark; POST/PUT/GET /runs/{id}/feedback |
| Conversations | POST/GET /conversations; GET/PATCH/DELETE /conversations/{id}; GET /messages and /memory; DELETE /memory |
| Heritage favorites | GET /users/me/heritage-favorites; PUT/DELETE /users/me/heritage-favorites/{heritage_id} |
| Source editorial | GET/POST /operations/content-sources; POST /ingest; GET /{source_id}; POST /{source_id}/versions; POST version /review, /publish, /withdraw |
| Catalog editorial | PUT entity-binding; GET audit; POST media; PUT/DELETE media/{media_id}; POST archive under /operations/heritages/{id} |
| Operator metrics | GET /operations/metrics with server operations bearer |

Source editorial and catalog media/editor APIs are available through REST;
the existing /admin pages are not a completed web CMS.

## Run inputs and state

RunCreate accepts asset_id, question, audience, profile, optional parent_run_id,
focus_box, location_hint, heritage_id and conversation_id. A bound asset must
belong to the principal. A selected heritage must be published; its canonical
binding/version and unverified hint are snapshotted server-side. Location hints
require the evidence profile and never become independent image evidence.

conversation_id links an owned conversation turn atomically with run admission.
Memory is opt-in and bounded to eight messages/4000 characters, with provenance;
prior answers and user assertions remain unverified context. Retry/review/
clarification ancestry is distinct from conversation history. GET messages is
paginated. DELETE memory resets future memory; deleting a conversation does not
silently delete its runs.

execution_status includes queued, running, cancel_requested, succeeded, failed,
cancelled and awaiting_input. run_kind includes full, review and clarification.
awaiting_input ends the current polling/SSE segment while retaining a partial
result and pending form; it is not success/failure. Clarification POST requires
pending ID/revision and Idempotency-Key, respects ownership/TTL/budgets, and
creates an immutable-parent child run.

Run-producing operations must retain the live gate: VITE_ALLOW_LIVE_MODEL_CALLS,
configured server models and current tab consent. Clients recheck capabilities
before create/retry/review/clarification/resume. Changing fields requires a new
idempotency key; retransmitting the same intended action reuses its key.

## Evidence, sources and media

Result/evidence include recognition, answer_status, requested slots, candidates,
claims, registered evidence, image quality, regions and bounded tool_calls.
Recognition has recognized/probable/ambiguous/unrecognized states. The pilot
profile caps recognition at probable; ID/quote validity is an automatic gate,
not human verification of historical truth.

Private crop images are fetched with owner authentication and displayed using
revocable blob URLs. Public catalog images remain public only while published.
The catalog photo bridge creates an owned asset and never creates a model run.

Source documents have immutable text versions, content hashes, reviewer and
review notes. Draft → reviewed → published/withdraw operations are revision
checked; only reviewed, published versions on visible sites enter DB retrieval.
Catalog source metadata marked not_indexed is distinct from these publications.
Entity binding preserves parent/component relations; all editorial mutations
are audited. Uploaded media uses a writable directory separate from bundled
assets; replacing/deleting metadata does not rewrite the bundled images.

## Streaming, recovery and retention

SSE is a persisted sequence of public stage events, not token-by-token answer
streaming. Replay uses after or Last-Event-ID, checks contiguous sequences and
does not duplicate already applied events. A disconnected stream does not cancel
the job. Raw hidden reasoning and private checkpoint payloads are not public API.

Queue/lease state and completed-node updates are durable. GET recovery exposes
completed node names/eligibility. Bounded lease-loss recovery and POST resume
can replay completed nodes when owner/lease/input/build/config/source signatures
and remaining budgets allow. An interrupted node/provider call may be retried;
this is not arbitrary in-flight LangGraph persistence or exactly-once billing.

DELETE run performs owner-scoped soft deletion after work settles. Retention/
purge tools plan before apply, protect active/referenced/account data and clean
eligible rows/files. Bulk purge and backup restore are operator CLI tasks, not
automatic browser actions. Source cache has TTL/capacity bounds and revision
invalidation; cached source artifacts never promote hints into verified facts.

## Errors, verification and remaining work

The standard error envelope and X-Request-ID apply. Handle 401/403/404, stale
version 409, validation 422 and rate-limit 429 without switching data modes.
Use safe internal redirects, cancel pending fetches on route change and keep
guest/account/Preview state separate.

[Postman](../../docs/postman.md) covers all 81 operations with opt-in mutations.
The isolated HTTP runner uses synthetic demo accounts/content and a labelled
WorkerLost fixture. Logic/API tests and demo outputs do not establish model
accuracy. A real corpus and human-reviewed gold are still required.

[Remaining capabilities](MISSING_BACKEND_CAPABILITIES.md) lists actual future
gaps; [feature matrix](FEATURE_MATRIX.md) distinguishes delivered REST from UI.
