# Local system validation

## Product-platform observations — 16 November 2026

The pre-merge product-platform worktree was verified against the real local
Docker demo backend. The frontend changes after baseline `6d614e3` require
`be/evidence-product-platform` at `06f44d4` (81 OpenAPI operations, migration
head `0009_runtime_state`). The target `dev` integration combines both branches;
its fresh verification is pending. No result below claims that the new merged
checkout has already been tested.

| Observed check | Result and scope |
| --- | --- |
| Frontend unit tests | 60/60 passed; transport, schemas, ownership-sensitive identity state, maps and model gates |
| Static/build checks | Typecheck, ESLint and production build passed; production dependency audit reported 0 vulnerabilities |
| Preview UI | 7/7 passed; fixture-only product/admin journeys and responsive layouts |
| API demo UI | 2/2 passed; actual sample/run/owner/evidence/feedback/export/retry/review flow |
| Catalog UI | 3/3 passed; actual catalog/media/map identity and photo bridge without an automatic run |
| Evidence UI | 2/2 passed; actual evidence/crop bytes and a clearly labelled pending-state UI fixture |
| Product UI | 2/2 passed; real account/refresh/logout/login, persisted favorites/conversations, explicit guest demo run and memory forgetting |

The five UI suites total **16/16 observed passes** at their final individual
runs against build `product-20261116-7f1b77dd55f9`. Product was rerun after the
checkbox/copy fixes. The later backend build `product-20261116-4a2f804ba27f`
changed provider backoff and was checked separately; the full 16-case UI set
was not rerun against that final image. No paid calls were made by these demo
UI suites. The synthetic QA accounts were disabled and their sessions revoked;
audit/history were preserved.

Detailed deployment, contract results, screenshot links, preservation checks
and the live-provider 429 limitation are recorded in
[PRODUCT_PLATFORM_DEPLOYMENT.md](../../docs/PRODUCT_PLATFORM_DEPLOYMENT.md).
The earlier successful live UI run below is historical and does not establish
that the new evidence clarification flow succeeded live. Human review of the
exported gold cases, full CMS/admin screens, email-based recovery/verification
and production hosting remain outside the observed acceptance.

Pending after branch integration: rerun static/unit/build checks, the isolated
Streamlit adapter module and selected real-demo UI suites on the merged `dev`
checkout. Record those new commands/results separately before updating this
section.

## Historical baseline — 15 November 2026

The following records describe the earlier branch `fe` baseline, Windows,
Node 24.13.1, Chrome and Docker Desktop. They are retained historical evidence,
not the current product-platform test count.
The backend ran in a dedicated `heritage-fe-local` Compose project using
PostgreSQL 17 and separate API/worker containers with demo-only volumes. This
stack does not load the repository `.env`. Capabilities confirmed
`model_mode=demo` for the initial integration track. A later, explicitly
authorized live-provider test used a separate stack and is recorded below.

Use [TESTING.md](TESTING.md) for exact commands and the two independent tracks:

1. UI Preview — account roles, catalog, favorites, map, admin, responsive
   routes, and simulated error states.
2. API integration — an actual FastAPI process in demo mode with a fresh
   database, asset directory, queue, guest session, assets, runs, SSE, results,
   retry/review, feedback, bookmarks, and export.

## Historical result record

These commands were actually run during the initial integration track. The
catalog update and current catalog regression results are recorded below and
in the linked database guide:

| Check | Command/evidence | Result |
| --- | --- | --- |
| ESLint | npm run lint | Pass, no warnings |
| TypeScript | npm run typecheck | Pass |
| Unit/transport/SSE/geometry/live gates | npm test | 33/33 pass |
| Production build | npm run build | Pass |
| Preview browser tests | npm run test:e2e | 7/7 pass |
| Docker API browser tests | RUN_API_INTEGRATION=1; npm run test:e2e | 2/2 pass |
| Live AI browser workflow | RUN_LIVE_UI=1; npm run test:e2e | 1/1 pass, actual Gemini inference |
| Isolated API smoke | Container scripts.api_smoke against port 8000 | Pass; 21 events, 1 evidence source |
| Readiness | GET /health/ready on host port 8001 | HTTP 200, database and worker ready |
| Workflow metadata | Authenticated GET /api/v1/workflow | HTTP 200, 7 stages |
| Production dependency audit | npm audit --omit=dev | 0 vulnerabilities |
| Desktop/mobile screenshots | 1440×1000 and 390×844 | Captured and visually inspected |

Record the date, command, exit code, browser/viewport, and backend
capabilities.model_mode. Do not record a guest token, Authorization header,
bootstrap/operations token, provider key, or private uploaded image.

## Interpretation limits

- A successful build does not prove API integration.
- Fixture HTTP tests do not prove the real backend contract.
- Frontend route guards do not prove RBAC.
- Preview CRUD does not prove server persistence.
- Stream EOF does not prove run success.
- A map-search URL does not prove a verified location.
- model_configured does not prove provider quota or a successful model call.
- “reviewed” is automated evaluation, not a guarantee that every historical
  claim is correct.

Only replace “Not run” with an observed result. Link failures and blockers
without overstating coverage.

## Historical guest integration scope

The browser exercised real guest session creation/validation/revocation,
backend sample selection and upload, authenticated image content, run creation
with idempotency, event history/SSE-backed completion, answer/evidence/stages/
model attempts, bookmarks/saved list, feedback persistence, actual JSON and
Markdown download contents, full retry and Judge-only review child runs.

Ownership checks confirmed anonymous image access returns 401, another guest
cannot access the owner's resource (404), and a hard reload discards browser
credentials. Test-created sessions were revoked. No access tokens or provider
keys are recorded in this document or screenshots.

The first Docker pass exposed a missing `docs/langgraph.mmd` packaging artifact
behind `/workflow`. The Dockerfile now includes it; both browser journeys were
rerun successfully. Optional workflow label metadata no longer prevents an
otherwise available answer from rendering.

## Historical Preview and visual checks

- All 7 published heritage photos load from same-origin local files. A blocked
  image shows a friendly fallback; retry restores the image.
- Catalog tag/whitespace filtering carries through to the map.
- List and marker/schematic selection stay synchronized. Partial coordinate
  input is rejected rather than converting the empty value to zero.
- Real `tile.openstreetmap.de` PNG requests returned HTTP 200 in desktop/mobile
  Chrome. Zoom, fit and destination selection worked. DEV uses this provider
  when no tile URL is set; usage terms are linked in the README.
- `tile.openstreetmap.org` was unreachable from this machine. That actual
  failure switches to the clearly labeled interactive coordinate schematic.
  Retry and online/schematic recovery were also checked.
- Rapid selection, filtering, map/list remounts and route changes no longer
  leave a pending Leaflet zoom callback. The browser regression asserts no
  uncaught page errors after unmount.
- Desktop and mobile layouts were inspected without horizontal overflow.

Screenshots under `frontend/artifacts/screenshots/`:

- `catalog-improved-desktop.png`
- `map-online-desktop.png`, `map-online-mobile.png`
- `map-new-desktop.png`, `map-new-mobile.png` (offline schematic)
- `backend-connected.png`
- `api-docker-result.png`

## Catalog database update

The catalog gap recorded during the initial integration below has since been
implemented: persisted public list/detail/media/coordinates, operations writes
and the guest-owned image bridge. Current deployment, retained backups and
catalog verification are recorded in
[CATALOG_DATABASE.md](../../docs/CATALOG_DATABASE.md). Initial measurements and
the paid-model run below remain historical evidence for their original scope.

## Historical skipped backend capabilities — superseded

At the initial 15 November inspection the following resource families were
absent. This table is historical: the matching 16 November backend now
implements accounts/RBAC, favorites, conversations, editorial source/media
APIs and evidence/tool traces. Full CMS/admin dashboards and email recovery
remain gaps. Use [current capabilities](MISSING_BACKEND_CAPABILITIES.md) for
today's delivered contracts and remaining proposals.

| Capability | Integration status |
| --- | --- |
| Account login/registration/password recovery and roles/RBAC | Skipped — no implemented account endpoints |
| Account heritage favorites | Skipped — distinct from supported run bookmarks |
| Admin users/content/sources/cross-owner run moderation | Skipped — no admin endpoints or admin principal |
| RAG ingestion/reindexing and tool-call trace artifacts | Skipped — no published operation |

Demo workflow completion proves integration, not historical accuracy or live
model quality. Production hosting was not tested. One authorized live workflow
was subsequently tested as detailed below.
Docker can be stopped with `docker compose -f frontend/docker/compose.demo.yaml
down`; this preserves the dedicated data volumes. The existing user development
server on port 5173 was preserved.

## Historical explicitly authorized live inference — 15 November

After the user updated server configuration and authorized possible provider
charges, `heritage-fe-live` ran at `127.0.0.1:8002` with a separate PostgreSQL
database, assets and worker. Compose loaded credentials into the server only;
no root environment file or secret was copied into the image/browser/artifacts.
Tracing/content capture stayed disabled.

One UI test selected the public Chùa Một Cột image, passed real metadata
preflight, confirmed the live consent checkbox and created exactly one full
workflow. No child retry/review workflow was requested. The test passed:

- Run `71b3efea-ef15-4db6-badb-27a90fb7e5da` reached `succeeded` / `reviewed`.
- Gemini `gemini-3.5-flash` performed the actual inference.
- Execution took 66.264 seconds with 21 recorded events and two sources shown.
- Seven model attempts: five successful and two truncated responses recovered
  by bounded backend retries (knowledge and aggregator). No provider fallback.
- Public usage totals were 27,577 tokens, including errored attempts; this is
  usage metadata, not a billing estimate.
- No HTTP 5xx occurred in the scoped test window; the guest session was revoked.
- Automatic Playwright retries, request traces and video were disabled.

Evidence: [sanitized live report](../artifacts/ai-live-system-test-2026-11-15.json)
and [actual UI result](../artifacts/screenshots/ai-live-result.png).
The default frontend continues to block live inference unless build opt-in,
server capability/configuration and fresh tab-local consent all permit it.
