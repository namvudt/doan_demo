# Route, role, and feature matrix

This matrix separates three states:

- **API-supported** — the current FastAPI backend has the required operation.
- **Preview-only** — the complete interaction uses isolated deterministic
  frontend state and is always labeled as UI Preview.
- **Blocked** — neither the current API nor an honest local-only behavior can
  deliver the claimed capability.

Frontend routes in this table do not imply matching backend routes.

## Roles and route access

| Frontend route | Preview guest | Preview user | Preview admin | API-mode guest session | Notes |
| --- | --- | --- | --- | --- | --- |
| /login | Yes | Redirect when signed in | Redirect when signed in | Yes, for guest access only | API mode has no email/password login. |
| /register | Yes | Redirect when signed in | Redirect when signed in | Screen visible; submission unavailable | Preview never creates a real account. |
| /forgot-password | Yes | Yes | Yes | Screen visible; submission unavailable | Preview sends no email. |
| /reset-password | Yes | Yes | Yes | Screen visible; submission unavailable | No reset-token API exists. |
| /profile | Guest-session view | Yes | Yes | Yes, session label/expiry only | API profile is not an account profile. |
| /chat | Yes | Yes | Yes | Yes | API mode requires an owner-scoped guest token. |
| /chat/runs/:runId | Own Preview data | Own Preview data | Own Preview data | Own session’s run only | Cross-owner resources return 404. |
| /heritages | Yes | Yes | Yes | Unavailable state plus genuine samples | No backend catalog exists. |
| /heritages/:heritageId | Yes | Yes | Yes | Unavailable | Preview illustrative record only. |
| /map | Yes | Yes | Yes | Honest no-location-data state | No backend coordinates exist. |
| /favorites | Read local/Preview state | Yes | Yes | Saved runs supported; heritage favorites local-only if offered | Keep saved-run and heritage sections distinct. |
| /admin and /admin/* | No, 403 | No, 403 | Yes | No real admin access | Preview role switch is visible only in Preview. |
| Unknown route | 404 | 404 | 404 | 404 | Route-level error UI required. |

Preview role guards are presentation controls. They do not prove server-side
authorization. API mode has one backend principal type: the owner of a guest
session. It has no user/admin role claim.

## Feature-to-contract matrix

| Feature | Frontend route | Existing endpoint | Existing request/response contract | Authentication/authorization | State |
| --- | --- | --- | --- | --- | --- |
| Read backend mode and limits | All API routes | GET /api/v1/capabilities | CapabilitiesView with model_mode, upload/image/question limits, profile, bootstrap flag | Public | API-supported |
| Guest-session access | /login, /chat | POST /api/v1/sessions | label → session_id, one-time access_token, expires_at; when bootstrap is required the browser uses a pre-issued token instead | Public; optional operator bootstrap | API-supported |
| Operator-issued guest access | /login | GET /api/v1/sessions/me | Bearer token → session metadata | Guest Bearer | API-supported |
| Email/password login | /login | None | No credential-login contract | None | Preview-only |
| Registration | /register | None | No account-creation contract | None | Preview-only |
| Forgot/reset password | /forgot-password, /reset-password | None | No email or reset-token contract | None | Preview-only |
| Preview account return redirect | Auth routes | Frontend behavior | Safe internal path only | Preview identity | Preview-only |
| Guest-access return redirect | /login | Existing guest-session endpoints | Safe internal path after session validation | Guest session | API-supported |
| Profile/account editing | /profile | None | GET /sessions/me is read-only session metadata | Guest Bearer | Preview-only |
| Logout/revoke guest session | /profile, shell | DELETE /api/v1/sessions/me | 204; revokes token and requests cancellation of active runs | Owning guest Bearer | API-supported |
| Preview logout | /profile, shell | None | Clears isolated Preview identity and state as designed | Preview role | Preview-only |
| List genuine sample images | /chat, /heritages | GET /api/v1/samples | items with sample_id and mechanically derived title | Public | API-supported |
| Convert sample to owned asset | /chat | POST /api/v1/samples/{sampleId}/assets | 201 AssetView | Guest Bearer | API-supported |
| Upload image | /chat | POST /api/v1/assets | multipart file → normalized PNG AssetView | Guest Bearer, owner-scoped | API-supported |
| List/select prior assets | /chat | GET /api/v1/assets | limit/offset → bare AssetView array | Guest Bearer, owner-scoped | API-supported |
| Display protected asset | /chat, run detail | GET /api/v1/assets/{assetId}/content | Authorized image/png | Guest Bearer, owner-scoped | API-supported |
| Delete unused asset | /chat, profile | DELETE /api/v1/assets/{assetId} | 204 or asset_in_use | Guest Bearer, owner-scoped | API-supported |
| Create image-question run | /chat | POST /api/v1/runs | asset_id, question, audience, profile → 202 RunView | Guest Bearer; demo by default, live only with explicit build opt-in + consent + configured capabilities | API-supported |
| Submit heritage_id to run | /heritages/:heritageId, /map | None | RunCreate does not accept heritage_id | None | Blocked |
| Ask about a Preview heritage | /heritages/:heritageId, /map, /chat | Preview adapter | Shared illustrative heritage plus a selected Preview asset | Preview identity | Preview-only |
| Ask backend about a selected image | /chat | Existing asset/run endpoints | User first selects or creates a real asset; RunCreate sends no catalog context | Guest Bearer | API-supported |
| Send heritage catalog context to a run | /heritages/:heritageId, /map, /chat | None | RunCreate has no heritage field or context object | None | Blocked |
| Run history | /chat | GET /api/v1/runs | paginated RunPage, filters for saved/status | Guest Bearer, owner-scoped | API-supported |
| Run status/detail | /chat/runs/:runId | GET /api/v1/runs/{runId} | RunView with execution and separate result status | Guest Bearer, owner-scoped | API-supported |
| Realtime progress | /chat/runs/:runId | GET /api/v1/runs/{runId}/events | Bearer SSE with sequence cursor and heartbeats | Guest Bearer, owner-scoped | API-supported |
| Progress polling/recovery | /chat/runs/:runId | GET /api/v1/runs/{runId}/events/history | EventPage with after/limit/next_after/terminal | Guest Bearer, owner-scoped | API-supported |
| Final answer | /chat/runs/:runId | GET /api/v1/runs/{runId}/result | ResultView; include_intermediate optional | Guest Bearer, owner-scoped | API-supported |
| Retrieved evidence | /chat/runs/:runId | GET /api/v1/runs/{runId}/sources | SourcesView with safe URLs and cited flags | Guest Bearer, owner-scoped | API-supported |
| Workflow stages | /chat/runs/:runId | GET /api/v1/runs/{runId}/steps | Dictionary of merged stage snapshots | Guest Bearer, owner-scoped | API-supported |
| Model attempts and token usage | /chat/runs/:runId | GET /api/v1/runs/{runId}/metrics | MetricsView with durable model attempts when available | Guest Bearer, owner-scoped | API-supported |
| Tool/API-call traces | /chat/runs/:runId | None | No tool-call trace or call-artifact endpoint | None | Blocked |
| Cancel run | /chat/runs/:runId | POST /api/v1/runs/{runId}/cancel | RunView; queued cancel is immediate, running becomes cancel_requested | Guest Bearer, owner-scoped | API-supported |
| Full retry | /chat/runs/:runId | POST /api/v1/runs/{runId}/retry | Required Idempotency-Key → new full child RunView | Guest Bearer; same demo/live opt-in gate as creation | API-supported |
| Judge-only review | /chat/runs/:runId | POST /api/v1/runs/{runId}/review | Required Idempotency-Key → new review child RunView | Guest Bearer; same demo/live opt-in gate as creation | API-supported |
| Export result | /chat/runs/:runId | GET /api/v1/runs/{runId}/export | JSON or Markdown attachment | Guest Bearer, owner-scoped | API-supported |
| Bookmark/save run | /favorites, run detail | PUT /api/v1/runs/{runId}/bookmark | saved boolean → updated RunView | Guest Bearer, owner-scoped | API-supported |
| List saved runs | /favorites | GET /api/v1/runs?saved_only=true | RunPage | Guest Bearer, owner-scoped | API-supported |
| Give answer feedback | /chat/runs/:runId | POST or PUT /api/v1/runs/{runId}/feedback | helpful, needs_review, or unrated plus note | Guest Bearer, owner-scoped | API-supported |
| Read own run feedback | /chat/runs/:runId | GET /api/v1/runs/{runId}/feedback | FeedbackBody | Guest Bearer, owner-scoped | API-supported |
| Chat conversations/turns | /chat | None | Runs have no editable conversation or message-memory contract | None | Preview-only |
| Heritage list/search/filter | /heritages | None | Samples are not heritage records | None | Preview-only |
| Heritage detail | /heritages/:heritageId | None | No catalog-detail contract | None | Preview-only |
| Heritage create/edit/delete | /admin/heritages | None | No heritage CRUD contract | None | Preview-only |
| Heritage favorite | /favorites | None | No synchronized favorite contract; any API-mode device save is explicitly local-only | None | Preview-only |
| Map list/markers/filter | /map | None | No catalog-coordinate contract | None | Preview-only |
| Browser geolocation | /map | Browser API | Explicit user action; permission may be denied; no backend persistence | Browser permission | Preview-only |
| Map tiles | /map | External tile provider | Configured URL and attribution; list-only fallback | No backend auth | Preview-only |
| Verified geocoding/routing | /map | None | Search URLs are not verified coordinates | None | Blocked |
| Preview admin dashboard | /admin | Shared Preview store | Counts derived from the active fixture state | Preview admin role | Preview-only |
| User list/role/status management | /admin/users | None | No account or RBAC contract | None | Preview-only |
| Admin heritage management | /admin/heritages | None | Shared fixture CRUD | Preview admin role | Preview-only |
| Content-source management | /admin/sources | None | Shared fixture source metadata only; no RAG ingestion | Preview admin role | Preview-only |
| Own-run inspection | /admin/runs | Existing run endpoints | Only runs owned by the current guest session; this is not an admin capability | Guest Bearer | API-supported |
| Global run monitoring | /admin/runs | None | No cross-owner/admin endpoint | None | Blocked |
| Feedback administration | /admin/feedback | None | No feedback list/moderation endpoint | None | Preview-only |
| Real admin workspace | /admin and children | None | No admin identity or server authorization | None | Blocked |
| Operations metrics in browser | None | GET /api/v1/operations/metrics | Requires a separate server operations token that must not enter the browser | Operator only | Blocked |

## Cross-page Preview consistency

Preview heritage list, detail, favorites, map, chat context, and admin heritage
forms must use the same store and stable record IDs. A create/edit/delete action
in Preview admin must immediately affect the public Preview catalog and map.
Preview success messages must say that data is simulated and not saved to the
backend.

## API-mode unavailable states

When API mode lacks a capability:

- keep the route navigable when it helps explain the limitation;
- name the missing server capability;
- provide the nearest supported action, such as genuine sample selection or
  owner-scoped saved runs;
- never substitute Preview fixtures after a failed request;
- never present a frontend role flag as real authorization.
