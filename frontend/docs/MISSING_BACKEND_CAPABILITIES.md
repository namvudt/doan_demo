# Missing backend capabilities and proposed contracts

## Important status

Everything under **PROPOSED** in this document is a design candidate. None of
these routes, request bodies, response fields, permissions, tables, or side
effects exists in the current backend.

The working HTTP adapter must not call these paths. API mode must show an
unavailable state until the backend implements the operation, publishes it in
OpenAPI, enforces authorization, and passes integration tests. UI Preview may
simulate the journeys only inside its isolated store and must keep the
persistent Preview banner visible.

The current implemented contract is documented in API_INTEGRATION.md.

## Confirmed gaps

The current backend does not provide:

- email/password or OIDC accounts, refresh, password reset, or account profile;
- user/admin roles or server-side RBAC;
- heritage catalog, detail, media, coordinates, search, or CRUD;
- heritage favorites;
- chat conversations, turns, or conversational memory;
- verified geocoding, map search, or routing;
- editable content-source records or a curated RAG corpus;
- ingestion, embedding, reindexing, or corpus status;
- admin summaries, cross-user run monitoring, user administration, or feedback
  moderation;
- tool/API-call traces or call input/output artifacts;
- token-by-token answer streaming;
- run deletion or durable workflow-node resume.

## Proposal principles

Any future implementation should:

1. keep existing guest sessions and account sessions distinguishable;
2. enforce ownership and roles on the server;
3. preserve the existing error envelope and X-Request-ID behavior;
4. publish capability flags so the frontend can enable features explicitly;
5. use cursor or stable offset pagination consistently;
6. require idempotency keys for retried mutations;
7. never expose provider keys, operations tokens, prompts, hidden reasoning, or
   arbitrary internal logs;
8. keep heritage favorites, run bookmarks, retrieved evidence, and RAG records
   as separate resource types;
9. record provenance and verification state for historical facts and
   coordinates;
10. define deletion, audit, retention, and concurrency behavior before launch.

## PROPOSED — Capability discovery

Extend GET /api/v1/capabilities with a versioned feature object rather than
making the frontend probe nonexistent endpoints.

~~~json
{
  "features": {
    "accounts": false,
    "heritage_catalog": false,
    "heritage_favorites": false,
    "verified_locations": false,
    "admin_users": false,
    "admin_heritages": false,
    "admin_sources": false,
    "admin_runs": false,
    "admin_feedback": false,
    "model_call_details": false,
    "tool_call_details": false
  }
}
~~~

This object is **PROPOSED**. Absence must be treated as unsupported.

## PROPOSED — Accounts and RBAC

Candidate operations:

| Method and proposed path | Purpose | Minimum authorization |
| --- | --- | --- |
| POST /api/v1/accounts | Public registration | Public; never accepts a role |
| POST /api/v1/auth/sessions | Account login | Public with rate limiting |
| DELETE /api/v1/auth/sessions/current | Account logout/revocation | Signed-in account |
| POST /api/v1/password-reset-requests | Request reset email | Public, non-enumerating response |
| POST /api/v1/password-resets | Consume single-use reset token | Public with valid reset token |
| GET /api/v1/users/me | Read account profile and effective roles | Signed-in account |
| PATCH /api/v1/users/me | Update allowed profile fields | Signed-in account |
| GET /api/v1/admin/users | Paginated user administration | Server-verified admin |
| GET/PATCH /api/v1/admin/users/{user_id} | Read/update role or status | Server-verified admin |

Proposed registration body:

~~~json
{
  "name": "Nguyễn Văn A",
  "email": "user@example.test",
  "password": "handled only over HTTPS"
}
~~~

The server, not the browser, must hash passwords, enforce uniqueness and policy,
rate-limit login/reset, revoke sessions, and audit role changes. Registration
must ignore or reject any client-supplied role.

A proposed principal response should make authentication kind explicit:

~~~json
{
  "principal_id": "uuid",
  "principal_type": "account",
  "display_name": "Nguyễn Văn A",
  "email": "user@example.test",
  "roles": ["user"],
  "expires_at": "date-time"
}
~~~

Whether real accounts use short-lived Bearer tokens plus rotation, secure
HttpOnly cookies plus CSRF, or external OIDC is an unresolved backend/security
decision. Frontend route guards remain presentation controls in every option.

## PROPOSED — Heritage catalog

Candidate operations:

| Method and proposed path | Purpose | Authorization |
| --- | --- | --- |
| GET /api/v1/heritages | Search, filter, paginate | Public or signed-in, policy decision |
| GET /api/v1/heritages/{heritage_id} | Public detail | Public or signed-in |
| POST /api/v1/heritages | Create record | Server-verified editor/admin |
| PATCH /api/v1/heritages/{heritage_id} | Update with concurrency check | Server-verified editor/admin |
| DELETE /api/v1/heritages/{heritage_id} | Delete/archive | Server-verified admin |
| POST /api/v1/heritages/{heritage_id}/media | Add media metadata/upload | Server-verified editor/admin |
| DELETE /api/v1/heritages/{heritage_id}/media/{media_id} | Remove media | Server-verified editor/admin |

Proposed list query:

- q
- category
- province
- verification_status
- has_location
- limit
- cursor or offset
- sort

Proposed record shape:

~~~json
{
  "heritage_id": "uuid",
  "name": "string",
  "slug": "string",
  "summary": "string or null",
  "historical_information": "string or null",
  "cultural_information": "string or null",
  "address": "string or null",
  "category": "controlled value",
  "province": "string or null",
  "location": {
    "latitude": 21.0287,
    "longitude": 105.8522,
    "verification_status": "verified",
    "source_id": "uuid or null",
    "verified_at": "date-time or null"
  },
  "media": [],
  "information_sources": [],
  "content_status": "draft",
  "version": 1,
  "created_at": "date-time",
  "updated_at": "date-time"
}
~~~

Coordinates must be optional, range-validated, provenance-linked, and clearly
marked illustrative, unverified, or verified. A place name or map-search URL
must never be converted into a verified coordinate automatically.

Update semantics should use an ETag, version, or If-Match precondition and
return a specific conflict when an editor overwrites stale data. Delete versus
archive, media storage, moderation, and public draft visibility remain backend
decisions.

## PROPOSED — Heritage favorites

Candidate operations:

| Method and proposed path | Purpose |
| --- | --- |
| GET /api/v1/users/me/heritage-favorites | Paginated synchronized favorites |
| PUT /api/v1/users/me/heritage-favorites/{heritage_id} | Idempotently favorite |
| DELETE /api/v1/users/me/heritage-favorites/{heritage_id} | Idempotently remove |

These require a real account principal. They must not reuse
PUT /runs/{run_id}/bookmark, and a device-local favorite must not be migrated
silently without user consent and conflict rules.

## PROPOSED — Catalog-to-chat context

The current RunCreate requires asset_id and does not accept heritage_id. A
future integration needs an explicit, provenance-aware contract.

Two candidate designs are:

1. provide an operation that creates an owned image asset from a selected,
   permitted heritage media object, then continue using the existing RunCreate;
2. version RunCreate with a structured heritage context reference whose
   server-side authorization and snapshot semantics are defined.

Example of the second design, **not currently accepted**:

~~~json
{
  "asset_id": "uuid",
  "question": "string",
  "audience": "tourist",
  "profile": "default",
  "context": {
    "heritage_id": "uuid",
    "heritage_version": 7
  }
}
~~~

The backend must specify whether that context affects retrieval, is merely
display metadata, or is captured as immutable evidence. Until then, the
frontend must send only the current RunCreate fields.

## PROPOSED — Conversations

If persistent multi-turn chat is required, define it separately from
api_sessions, which currently represent authentication/ownership.

Candidate operations:

| Method and proposed path | Purpose |
| --- | --- |
| POST /api/v1/conversations | Create a named conversation |
| GET /api/v1/conversations | List the current principal’s conversations |
| GET/PATCH/DELETE /api/v1/conversations/{conversation_id} | Read, rename, or delete |
| GET /api/v1/conversations/{conversation_id}/turns | Paginated turn history |
| POST /api/v1/conversations/{conversation_id}/runs | Create a run with defined memory rules |

The contract must define which prior turns enter model context, consent and
retention, token limits, deletion effects, attachment ownership, and whether a
retry changes conversation state. parent_run_id alone is not this feature.

## PROPOSED — Map search

If the heritage list endpoint supports verified coordinates, the map may query
the same catalog with:

- bbox=west,south,east,north;
- q, category, and province;
- has_location=true;
- a documented maximum result count or clustering contract.

A separate geocoding or routing service is not necessary for the basic map.
If later added, it must have an explicit provider, attribution, quotas, privacy
policy, and server-side credential handling. Browser code must not contain paid
provider keys.

## PROPOSED — Content sources and RAG operations

Source metadata is distinct from evidence retrieved for a run.

Candidate metadata operations:

| Method and proposed path | Purpose | Authorization |
| --- | --- | --- |
| GET /api/v1/admin/content-sources | List managed source metadata | Admin/editor |
| POST /api/v1/admin/content-sources | Create metadata record | Admin/editor |
| GET/PATCH/DELETE /api/v1/admin/content-sources/{source_id} | Manage record | Admin/editor |

Minimum metadata might include source_id, title, canonical_url, publisher,
license, language, content type, verification status, review timestamp, and
version.

Ingestion/indexing must be a separate job resource rather than an implied side
effect of editing metadata:

- POST /api/v1/admin/index-jobs
- GET /api/v1/admin/index-jobs/{job_id}
- GET /api/v1/admin/index-jobs/{job_id}/events

These job routes are also **PROPOSED**. A metadata update must never report that
embedding or reindexing occurred unless a supported job actually completed.

## PROPOSED — Administration

Every proposed admin operation requires a server-verified role. A frontend
role flag, guest token, bootstrap token, or operations token is insufficient.

Candidate operations:

| Method and proposed path | Purpose |
| --- | --- |
| GET /api/v1/admin/summary | Data-derived counts with scope and timestamp |
| GET /api/v1/admin/runs | Authorized cross-owner run monitoring |
| GET /api/v1/admin/runs/{run_id} | Sanitized operational detail |
| POST /api/v1/admin/runs/{run_id}/cancel | Policy-controlled cancellation |
| GET /api/v1/admin/feedback | Paginated feedback review |
| PATCH /api/v1/admin/feedback/{feedback_id} | Moderation state, if required |

Admin responses must omit access tokens, prompts, provider payloads, hidden
reasoning, private uploaded content unless explicitly authorized, and arbitrary
application logs. /api/v1/operations/metrics is not a substitute for these
contracts.

## PROPOSED — Model and tool call visibility

The current /metrics endpoint supplies model-attempt metadata. If product
requirements later need more granularity, expose separate sanitized resources:

- GET /api/v1/runs/{run_id}/model-calls
- GET /api/v1/runs/{run_id}/tool-calls

Possible public fields include call_id, stage_id, role/tool name, status,
started_at, finished_at, duration, model/provider, safe error classification,
usage, and references to already-public artifacts. Inputs/outputs should be
explicitly allow-listed. Prompts, chain-of-thought, credentials, provider
request bodies, and raw internal logs must remain excluded.

## Proposed delivery order

1. Capability flags and a real principal/RBAC model.
2. Heritage catalog with provenance-aware optional coordinates.
3. Heritage favorites and catalog-to-chat asset/context behavior.
4. Heritage admin CRUD and source metadata.
5. Admin users/runs/feedback.
6. Conversations only if genuine multi-turn memory is a confirmed requirement.
7. RAG indexing jobs and detailed call/tool views only after security and
   observability requirements are approved.

No item advances from Preview-only or Blocked to API-supported until its
implementation, authorization, migrations, tests, and OpenAPI contract exist.
