# Implemented capabilities and remaining proposals

This file records gaps **after** the product/content/recovery integration.
Current code has 81 OpenAPI operations, Swagger 1.2.0, Postman 84 requests and
migration head 0009_runtime_state. Delivered operations are not proposals.
OpenAPI and the router modules remain authoritative; check capabilities/build
identity to establish which code is actually running.

## IMPLEMENTED

| Area | Delivered contract and limits |
| --- | --- |
| Accounts | Email/password registration/login, hashed passwords/tokens, refresh rotation, profile/password update and per-session logout |
| Roles | User/editor/admin, DB-checked authorization; role assignment by admin or server operations; no client-supplied signup role |
| Conversations | Owned conversation CRUD, persisted turns/messages, optional bounded unverified memory and explicit forgetting |
| Heritage favorites | Account GET/PUT/DELETE favorites by heritage_id, separate from run bookmarks |
| Catalog | Persisted list/detail/media/coordinates; versioned editor/operations metadata writes, image management and archive |
| Structured run context | Optional heritage_id, conversation_id, location_hint and focus_box; catalog version/context snapshot with ownership and trust boundaries |
| Editorial sources | Draft ingestion, immutable text versions/hash, explicit reviewer/attestation, review/publication/withdraw and audit |
| Retrieval | Wikipedia, reviewed JSONL and published DB sources; canonical parent/component binding and shared source cache with revision invalidation |
| Evidence/tool trace | Claims/evidence, source IDs, image regions, bounded tool_calls and durable provider attempts |
| Lifecycle | Owner soft-delete, bounded completed-node replay/WorkerLost resume, retention/purge planning and backup tooling |

Editorial APIs live under /operations/content-sources and /operations/heritages.
They accept editor/admin account bearer or server operations bearer; role
assignment additionally restricts account callers to admin. Operator tokens
never belong in frontend configuration.

Metadata in the original heritage information_sources collection remains
not_indexed. The new source-document/version publication workflow is separate:
only approved/current publications enter retrieval. Source text is immutable
through editorial APIs; editing creates a new draft revision. Withdrawing a
publication or archiving its heritage removes it from public/retrieval reads.

POST /runs accepts heritage_id and conversation_id today. The catalog photo
bridge remains an owned-image import with no automatic run/model call. Catalog
selection is an unverified hint, not visual identification. Memory is opt-in,
bounded and provenance-labelled; previous model answers are not trusted sources.

Recovery stores completed node updates in DB and checks lease/owner/build/
config/input/source signatures and remaining budgets before replay. An
interrupted external call can be retried. It is not arbitrary persistence
inside a running node or an exactly-once guarantee for external providers.

## Confirmed remaining gaps

- Password reset via email, email verification and external OIDC/SSO.
- Full web CMS/editor screens and complete user-list/moderation/admin dashboards.
  Backend editorial REST exists; current /admin pages remain Preview fixtures.
- A corpus of real historical sources and an independent gold set already
  reviewed by people. The user will review the exported draft cases; test/model
  verdicts do not replace that review.
- Embedding/vector indexing if scale and retrieval evaluation justify it.
  Current lexical/passage retrieval and cache are implemented.
- General address geocoding, map-provider search/routing and bbox/clustering
  contracts. Existing optional catalog coordinates do not promise those.
- Token-by-token answer streaming; current SSE publishes persisted stage events.
- Arbitrary in-flight LangGraph checkpoint/restore. Completed-node replay is
  implemented and should not be described as missing.
- Optional self-service account deletion/export and broader moderation workflows
  if required by the final product scope.

## PROPOSED — Account recovery and verification

Future reset/verification contracts need single-use expiring tokens, abuse
limits, non-enumerating responses and server-side mail delivery. Candidate
routes such as POST /password-reset-requests and POST /password-resets are
**not implemented**. Existing authenticated password change is delivered at
POST /users/me/password and must not be confused with forgotten-password recovery.

## PROPOSED — Full web administration

Build editor/CMS screens over the existing source/media/version/role APIs with
real account authorization. Add user-list/moderation endpoints only when those
journeys are implemented and published in OpenAPI. The browser must use account
tokens; it must never receive operations/bootstrap/provider secrets. Preview
admin state and route guards are not evidence of server permissions.

## PROPOSED — Geographic and retrieval extensions

Geocoding, routes, geographic bounding-box queries or vector indexes need an
explicit measured use case, data/provider attribution and a published contract.
A map search link is navigation, not verified geography or historical evidence.
The current small corpus does not establish a need for extra agents/vector DB.

## Integration rules

Use capability flags; keep Preview/API state isolated; preserve the standard
error envelope and X-Request-ID; require ownership/RBAC and expected versions;
reuse idempotency keys only for replay of the same intended action. Deletion
and bulk purge have distinct consent/retention semantics. Do not expose private
checkpoint payloads, hidden reasoning, raw credentials or arbitrary logs.

[API integration](API_INTEGRATION.md), [feature matrix](FEATURE_MATRIX.md) and
[Postman](../../docs/postman.md) describe implemented operations and safe
defaults. The new operations must not be labelled missing just because a full
web CMS, human-reviewed corpus or external account recovery is still pending.
