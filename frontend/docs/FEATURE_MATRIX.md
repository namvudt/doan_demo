# Route, role, and feature matrix

Current backend: **81 operations**, Swagger **1.2.0**, result schema **2** and
migration head **0009_runtime_state**. This matrix separates delivered backend
REST, currently integrated React flows, Preview fixtures and future work.

## Identity and route access

| Frontend route | UI Preview | Current API behavior |
| --- | --- | --- |
| /login | Isolated fixture identity | Guest token flow or real account password login |
| /register | Simulated registration | Real POST /accounts; server grants user only |
| /forgot-password, /reset-password | Clearly simulated | Email/reset-token endpoints remain unavailable |
| /profile | Fixture profile | Guest metadata or account profile/name and explicit session refresh |
| /chat | Shared Preview state | Guest/account-owned runs and real conversation selection, opt-in memory |
| /chat/runs/:runId | Own fixture runs | Owner-protected result/evidence/crop/clarification |
| /heritages and detail | Fixture catalog | Published DB catalog/media/context |
| /map | Fixture coordinates | Same DB catalog IDs/coordinates; verification labels retained |
| /favorites | Preview favorites | Account heritage favorites and owner-scoped saved runs, kept distinct |
| /admin and children | Preview admin fixtures | Full web CMS/admin workspace remains unavailable; backend editorial REST exists |
| Unknown route | 404 | 404 |

Preview role switches are presentation-only. Real accounts have user/editor/
admin roles verified in the DB. Stable account ownership survives new login
sessions; guest ownership remains session-scoped. Editorial REST accepts an
authorized account token without exposing operations secrets in the browser.

## Implemented feature-to-contract matrix

Paths use /api/v1 except /health. The source routers/OpenAPI are authoritative.

| Feature | Existing contract | Authorization | Current UI status |
| --- | --- | --- | --- |
| Mode/config discovery | GET capabilities, health/live, health/ready | Public | Integrated |
| Guest access | POST sessions; GET/DELETE sessions/me | Guest bearer; optional bootstrap for issue | Integrated |
| Accounts | POST accounts/auth/sessions/auth/refresh; DELETE auth/sessions/current | Public issue/refresh with DB limits; current account for logout | Login/register/refresh integrated |
| Profile/password | GET/PATCH users/me; POST users/me/password | Account; version/current-password checked | Profile/name integrated; password-management REST available |
| Roles/status | PUT operations/accounts/{account_id}/role | Admin or server operations; expected version | Backend/API + operator tools; not a complete admin user-list UI |
| Image input | Assets CRUD/read PNG, sample-to-owned asset, catalog-photo bridge | Owner for assets; public catalog image | Integrated |
| Run workflow | POST/list/read runs, cancel/retry/review | Owner, idempotency and model-mode gate | Integrated |
| Evidence/recognition | Result/evidence/regions/crop with status/provenance | Owner | Integrated |
| Clarification | GET/POST runs/{id}/clarification, awaiting_input | Owner, pending revision and budgets | Integrated; explicit submit only |
| Conversation history | Conversations CRUD and GET messages | Owner; version/active-turn checks | Selection/create/history integrated |
| Bounded memory | GET/DELETE conversation memory; run conversation_id | Owner, opt-in and provenance | Toggle/forget integrated |
| Favorites | GET/PUT/DELETE users/me/heritage-favorites | Account | Integrated; separate from run bookmark |
| Catalog read/map | List/detail/media/context/published sources | Public, published only | List/detail/map integrated |
| Metadata editing | POST/PUT operations/heritages | Editor/admin or operations | REST delivered; CMS forms still Preview |
| Source publication | Source/version/review/publish/withdraw APIs | Editor/admin or operations, explicit review and versions | REST/Swagger/operator tools; full CMS future |
| Media management | Upload/replace/delete media and archive heritage | Editor/admin or operations, version checked | REST delivered; full CMS future |
| Canonical binding/audit | Entity binding and editorial audit APIs | Editor/admin or operations | REST delivered |
| SSE/history/export | Stage events/cursors, JSON/Markdown, metrics | Owner | Integrated; no token stream |
| Tool trace | Bounded tool_calls and attempts in evidence/result/metrics | Owner; sanitized public artifacts | Evidence/processing views integrated |
| Durable node replay | GET recovery; POST resume plus bounded lease recovery | Owner, lease/signature/budget checks | Backend API; general recovery-control UI future |
| Run soft deletion/retention | DELETE runs/{id}; plan/apply purge CLI | Owner for deletion; operator for purge | Backend/API tools; no automatic browser purge |
| Retrieval cache | Bounded shared source cache, revision invalidation | Internal service | No separate user action required |
| Operations metrics | GET operations/metrics | Server operations token | Operator tooling only |

## Limits and future work

Backend editorial REST is delivered; /admin fixture pages do not become a real
CMS merely because those routes exist. UI should enable flows only when their
client implementation and capability flag are present. Missing routes stay
honest unavailable states and never fall back to Preview after HTTP errors.

Remaining features include reset-email/OIDC/email verification, the full web
CMS/moderation workspace, optional vector indexing, general geocoding/routing,
token-by-token answer streaming and arbitrary in-flight graph persistence.
Completed-node replay is available; a provider call interrupted mid-node may
repeat within budget. Real sources and the gold set still need human review;
automatic evidence checks and seeded coordinates retain their limitations.
