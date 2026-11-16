# Di sản Việt Nam — frontend

Vietnamese-first React frontend for the repository’s Heritage VQA backend. It
supports real guest/account identities, owner-scoped runs, conversations,
heritage favorites and a persisted catalog. UI Preview remains an explicitly
isolated fixture mode, including the full administration screens.

The matching Python backend provides evidence-v2, editorial source/media APIs,
server-enforced user/editor/admin roles and recovery/lifecycle operations.
These APIs do not imply that the React application has a complete web CMS.

The frontend changes after baseline `6d614e3` require the matching
`be/evidence-product-platform` backend (`06f44d4`, 81 OpenAPI operations,
migration head `0009_runtime_state`) for the new API journeys. The `dev`
integration combines the frontend and backend branches; verification of that
merged checkout is pending. Preview can run without a backend. Older servers
remain capability-gated and never trigger a fixture fallback.

## Modes

| Mode | Environment | Purpose |
| --- | --- | --- |
| UI Preview | VITE_FRONTEND_MODE=preview | Deterministic browser fixtures for account, heritage, favorites, map, and admin journeys. |
| API integration | VITE_FRONTEND_MODE=api | Actual FastAPI guest/account access, profile/refresh/logout, conversations/memory, heritage favorites, catalog/map, assets/samples, runs, evidence, retry/review/clarification, bookmarks, feedback, and export. |

Preview always displays:

> UI Preview — Dữ liệu mô phỏng, chưa lưu lên backend

An API failure never triggers a fixture fallback. Preview and API identities,
tokens, IDs, uploads, records, and caches are isolated. Switching mode clears
incompatible session state.

In API mode, the frontend reads model_mode from GET /api/v1/capabilities.
Run-producing actions default to demo-only. Live actions additionally require
`VITE_ALLOW_LIVE_MODEL_CALLS=true`, a configured live backend, and explicit
tab-local user consent. A frontend setting cannot change backend model mode.

## Routes

| Route | Purpose |
| --- | --- |
| /login, /register | Preview accounts; real API account registration/login or guest access |
| /forgot-password, /reset-password | Complete Preview states; unavailable honestly in API mode |
| /profile | Preview profile or API account profile/refresh/logout and guest-session metadata |
| /chat | Image/sample question workspace and owned conversation selection/history/memory controls |
| /chat/runs/:runId | Run status, answer, evidence, stages, model attempts, actions |
| /heritages, /heritages/:heritageId | Preview catalog or persisted public API catalog/detail/media |
| /map | Catalog list/map synchronization in both modes, with offline coordinate fallback |
| /favorites | Heritage favorites and saved runs as separate resource types |
| /admin | Preview dashboard |
| /admin/users | Preview user/role/status management |
| /admin/heritages | Preview heritage CRUD using the shared catalog |
| /admin/sources | Preview source metadata; never claims RAG ingestion |
| /admin/runs | Preview-only run monitoring; API owner history stays under /chat |
| /admin/feedback | Preview feedback review |

Preview admin routes require the visible Preview admin role and stay
Preview-only. The backend enforces real user/editor/admin permissions for
editorial and role operations; complete React CMS/admin screens remain future
work. Frontend route guards are presentation controls only.

## Local UI Preview

Requirements: Node.js 22.12 or newer and npm.

~~~powershell
Set-Location frontend
npm ci
$env:VITE_FRONTEND_MODE = "preview"
npm run dev
~~~

Open http://127.0.0.1:5173.

The committed lockfile matches the dependency manifest. Use `npm ci` for a
reproducible clean install; use `npm install` only when intentionally updating
dependencies and the lockfile together.

## API integration against the isolated backend demo

Docker local is the quickest complete setup (PostgreSQL, API, separate worker).
Run from the repository root:

~~~powershell
docker compose -f frontend/docker/compose.demo.yaml pull db
docker compose -f frontend/docker/compose.demo.yaml build api
docker compose -f frontend/docker/compose.demo.yaml up -d --no-build --pull never
~~~

The API is at http://127.0.0.1:8001/docs. This dedicated demo stack has its own
volumes, does not load the repository `.env`, and disables billable model calls.
Use the connection indicator in the app to check API/database/worker readiness.
To stop it while keeping demo data, run
`docker compose -f frontend/docker/compose.demo.yaml down`.

Run a direct HTTP smoke inside Docker:

~~~powershell
docker compose -f frontend/docker/compose.demo.yaml exec -T api python -m scripts.api_smoke --url http://127.0.0.1:8000
~~~

Then run the browser integration suite from `frontend/`:

~~~powershell
$env:RUN_API_INTEGRATION = "1"
npm run test:e2e
Remove-Item Env:RUN_API_INTEGRATION
~~~

The catalog requires the database seed in
[the catalog deployment guide](../docs/CATALOG_DATABASE.md). Run its dedicated
browser suite with `RUN_CATALOG_API=1`; it checks catalog/detail/media/map and
the guest-owned photo bridge without creating an AI run. Use
`RUN_PRODUCT_API=1` for account/conversation/favorite journeys and
`RUN_EVIDENCE_API=1` for evidence/crop/clarification UI coverage. Each flag runs
a separate demo-only suite. Account and guest credentials stay in tab memory;
reload requires a new login/session, while account data remains on the server.

### Python alternative

Start the backend from the repository root in a separate terminal:

~~~powershell
uv run --locked python -m scripts.serve_api --demo --port 8001
~~~

For verification, that command must also receive a fresh DATABASE_URL and
API_DATA_DIR. The --demo flag alone does not isolate an existing database,
asset directory, or worker queue. Use the complete safe PowerShell setup in
[docs/TESTING.md](docs/TESTING.md).

Then start the frontend:

~~~powershell
Set-Location frontend
$env:VITE_FRONTEND_MODE = "api"
$env:VITE_API_BASE_URL = "/api/v1"
npm run dev
~~~

The Vite development proxy sends /api and /health to
http://127.0.0.1:8001 by default.

### Explicit live AI test

This track makes real provider calls and may incur charges. It is never
selected by the normal test command. The existing server `.env` is loaded
only into the isolated live API/worker, while database/assets are separate
from the demo stack. Never print `docker compose config`, container environment
or a root `.env` when collecting evidence.

From the repository root, after the backend image has been built:

~~~powershell
docker compose -f frontend/docker/compose.live-test.yaml up -d --no-build --pull never
~~~

The live API listens only at http://127.0.0.1:8002. Run exactly one UI workflow:

~~~powershell
Set-Location frontend
$env:RUN_LIVE_UI = "1"
npm run test:e2e
Remove-Item Env:RUN_LIVE_UI
~~~

This test checks real preflight, confirms the live consent checkbox and creates
one full run using a public sample. It does not trigger child retry/review runs.
Playwright automatic retries, video and request traces are disabled for this
track. A preflight/provider failure is reported as a failure, not as a Preview
fallback or a skipped success.

For interactive use, run Vite with `VITE_FRONTEND_MODE=api`,
`VITE_ALLOW_LIVE_MODEL_CALLS=true` and server-only
`BACKEND_PROXY_TARGET=http://127.0.0.1:8002`. Consent is cleared on session
replacement/logout and mode changes. To stop the isolated live stack, run
`docker compose -f frontend/docker/compose.live-test.yaml down` from the root.

If capabilities reports session_bootstrap_required=false, the browser can
create a guest session. Otherwise use only an operator-issued guest access
token. Never place X-Bootstrap-Token or API_OPERATIONS_TOKEN in the browser.

## Environment

Copy values from .env.example into an ignored .env.local when persistent local
configuration is useful:

~~~dotenv
VITE_FRONTEND_MODE=preview
VITE_API_BASE_URL=/api/v1
VITE_API_TIMEOUT_MS=30000
VITE_MAP_TILE_URL=https://tile.openstreetmap.de/{z}/{x}/{y}.png
~~~

Set VITE_MAP_TILE_URL to an empty value for deterministic offline tests.
The map then shows an interactive coordinate schematic with
selection synchronized to the list. Missing or timed-out online tiles use the
same fallback and offer a retry; the diagram is not a navigation map.
OpenStreetMap attribution remains visible when its tiles are used.

Local development defaults to OSM Germany when no tile URL is configured;
production builds default to the standard OSM URL. The local demo provider
permits noncommercial/small web embedding and forbids bulk/offline tile
downloads. See its [usage policy](https://openstreetmap.de/germanstyle/).
Choose a suitable provider before commercial deployment. No tiles are cached
offline or shipped with this frontend; the offline view is a separate coordinate
diagram. Leaflet retains nearby tiles in memory during ordinary navigation.

The map supports a collapsible results pane, compact/expanded place details,
and an expanded workspace (Escape restores it). Switching to list-only mode
preserves the map viewport. On phones the results open as a bottom sheet.

For an opt-in Mapbox trial, put the following in an ignored
`frontend/.env.map.local` file, replacing the token on your own machine:

~~~dotenv
VITE_MAP_PROVIDER=mapbox
VITE_MAPBOX_ACCESS_TOKEN=YOUR_PUBLIC_PK_TOKEN
VITE_FRONTEND_MODE=preview
VITE_ALLOW_LIVE_MODEL_CALLS=false
~~~

Run `npm run dev -- --mode map --port 5175 --strictPort` from `frontend`.
Mapbox uses Streets v12 raster tiles at 512px with a zoom offset of -1,
including its logo and text attribution. Existing camera/marker retention
and offline fallback also apply. Only public `pk.` tokens are accepted;
the browser configuration must never contain a secret `sk.` token.
The trial stays separate from the normal development mode.

All seven published Preview records have local photos. Image loading uses a
placeholder animation, accessible error state and retry on detail pages.
Sources and licenses are listed at `/heritages/credits.html` (served as a static
page; distinct from the catalog's dynamic heritage routes).

Every VITE_* value is public bundle configuration. Never put guest tokens,
passwords, provider keys, database credentials, bootstrap tokens, or operations
tokens there.

## Commands

~~~powershell
npm run lint
npm run typecheck
npm test
npm run build
npm run preview
npm run test:e2e
~~~

- lint runs ESLint against application code, tests, and TypeScript config files.
- typecheck runs strict TypeScript without emitting JavaScript.
- test runs Vitest.
- build type-checks and creates dist/.
- test:e2e runs only app.spec.ts in Preview mode, regardless of a stale
  VITE_FRONTEND_MODE. Set RUN_API_INTEGRATION=1 to run only api-live.spec.ts
  against an already-running isolated demo API. Select only one explicit suite
  flag at a time; catalog, evidence and product flags select their own API
  suites. See [docs/TESTING.md](docs/TESTING.md) for commands and prerequisites.

The 16 November product-platform verification observed 60 unit tests and 16 UI
cases passing across Preview/API/catalog/evidence/product suites. These are
recorded results from that deployment, not a fresh run of the pending merged
`dev` checkout. Exact scope and historical results are in
[docs/VALIDATION.md](docs/VALIDATION.md).

Run the successful-tile map regression suite separately in PowerShell:

~~~powershell
$env:RUN_MAP_PERF='1'
npm run test:e2e
Remove-Item Env:RUN_MAP_PERF
~~~

This suite fulfills map tiles locally and checks drag/zoom, stable map and
marker nodes, retained camera position, resize, and responsive controls. It
does not call a map provider, backend, or AI model. See
[the map and layout review](../docs/MAP_LAYOUT_REVIEW.md) for the diagnosis.

For native scroll and image-loading feedback regressions:

~~~powershell
$env:RUN_SCROLL_PERF='1'
npm run test:e2e
Remove-Item Env:RUN_SCROLL_PERF
~~~

Both map and scroll regression flags isolate Preview from stale backend/live
test flags. The scroll profiler and its before/after data are documented in
[the scroll review](../docs/SCROLL_PERFORMANCE_REVIEW.md). A bounded MapTiler
experiment, including the current credential limitation, is documented in
[the provider experiment](../docs/MAP_PROVIDER_EXPERIMENT.md).

Set `RUN_MAPBOX_UI=1` for the dedicated Mapbox UI regression suite. It forces
`pk.fixture` and intercepts tiles locally; default, map and scroll suites clear
the Mapbox token and use their own tile configuration. Real provider tests
are separate, explicitly invoked benchmark commands from the provider report.

The AI question workspace uses a compact shared image/question composer,
on-demand history, and an answer-first result page with expandable processing
details. Preview and API retain distinct data/model modes. See
[the chat UI redesign](../docs/CHAT_UI_REDESIGN.md) for screenshots and validation.

~~~powershell
$env:RUN_CHAT_UI='1'
npm run test:e2e
Remove-Item Env:RUN_CHAT_UI
~~~

This suite checks image selection/drop/removal, drafts, history, source context,
and desktop/mobile layouts without backend or paid model requests.

Playwright owns a separate Vite server at http://127.0.0.1:5174 and never
reuses an existing server. You can leave your development server on port 5173
running; port 5174 must be free.

Browser selection uses PLAYWRIGHT_CHROMIUM_EXECUTABLE when supplied, then a
matching bundled Chromium, then installed Chrome/Edge. The explicit path is
optional. If none is available, install Chromium once:

~~~powershell
npx playwright install chromium
~~~

Do not describe fixture HTTP tests as real backend integration. Exact test
tracks and reporting rules are in [docs/TESTING.md](docs/TESTING.md).

## Security and transport

- Guest/account access tokens and account refresh tokens stay in tab memory.
  Bearer authorization is attached only to the configured API origin/prefix;
  refresh is explicit and rotates the device session credentials.
- Protected asset images are fetched as authorized Blobs.
- SSE uses authenticated fetch streaming with sequence replay; native
  EventSource cannot supply the required Authorization header.
- Stream disconnect does not cancel a run and does not prove success.
- Idempotency keys are stable for retransmission and new for explicit new
  actions.
- Generated Markdown is rendered without raw HTML execution.
- External links use safe schemes and opener isolation.
- Browser geolocation is requested only after an explicit user action.
- Mapbox is opt-in through an explicitly configured public token; no hidden
  geocoding calls are made.

## Backend boundaries

The matching 81-operation backend provides guest sessions and email/password
accounts, access/refresh rotation, profile/password update, server-checked
roles, owned conversations/turns/messages with optional bounded unverified
memory, and heritage favorites distinct from run bookmarks. React exposes
account login/register/profile/refresh/logout, conversation controls and
favorites when the corresponding capability flags are enabled.

It also provides capabilities/workflow, assets/samples, owner-scoped runs,
SSE/history, evidence/claims/image regions/tool traces, sources, stage snapshots,
model attempts, cancellation, retry/review/clarification, bookmarks, feedback,
export, soft deletion and bounded completed-node recovery.

It also provides a persisted public heritage catalog, local image content,
optional coordinates with explicit verification metadata, a catalog-photo
bridge into owned assets, plus versioned editorial source ingestion,
review/publication/withdrawal and media management. Editorial APIs accept
authorized editor/admin accounts or server operations credentials; role
assignment restricts account callers to admins. Operations secrets never
belong in the browser. The seed records remain illustrative; persistence and
automated evidence checks do not establish historical accuracy.

Email-based password recovery/verification, external SSO, complete web CMS and
cross-user moderation dashboards remain future work. Preview may simulate
those screens but never claims backend persistence. The user will review the
exported draft gold cases; model output is not a human-approved answer set.

## Documentation

- [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) — implemented backend
  contract, auth, SSE, errors, modes, and security.
- [../docs/CATALOG_DATABASE.md](../docs/CATALOG_DATABASE.md) — catalog schema,
  seed, Docker volumes, provenance and verification.
- [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) — route, role, endpoint, and
  support-status matrix.
- [docs/MISSING_BACKEND_CAPABILITIES.md](docs/MISSING_BACKEND_CAPABILITIES.md) —
  delivered backend features and clearly labeled remaining proposals.
- [../docs/PRODUCT_PLATFORM_DEPLOYMENT.md](../docs/PRODUCT_PLATFORM_DEPLOYMENT.md) —
  product API deployment, migrations, test evidence and current limits.
- [docs/TESTING.md](docs/TESTING.md) — isolated API demo, Preview, build, and
  browser verification.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — static hosting and reverse proxy.
- [docs/VALIDATION.md](docs/VALIDATION.md) — result-reporting template and
  known verification boundary.

The live backend publishes its authoritative OpenAPI document at
/openapi.json. No generated frontend OpenAPI file is committed because the
inherited ZIP contract was not authoritative.

## Structure

~~~text
src/
  api/          Actual FastAPI types, validation, HTTP transport, SSE parser
  app/          Mode/session/capability state and route guards
  layouts/      Shared application and admin layouts
  pages-v2/     Auth, chat, heritage, map, favorites, profile, admin pages
  preview/      Isolated fixtures, validation, roles, and shared Preview store
  ui/           Reusable controls, safe Markdown, Leaflet map
tests/          Unit/transport and Playwright tests
docs/           Integration, matrix, proposals, testing, deployment
~~~
