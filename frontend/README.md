# Di sản Việt Nam — frontend

Vietnamese-first React frontend for the repository’s Heritage VQA backend. It
supports the real owner-scoped guest/run API and an explicitly isolated UI
Preview for product journeys that the backend does not implement.

This directory is frontend-only. It does not add account, catalog, map,
administration, or RAG endpoints to the Python backend.

## Modes

| Mode | Environment | Purpose |
| --- | --- | --- |
| UI Preview | VITE_FRONTEND_MODE=preview | Deterministic browser fixtures for account, heritage, favorites, map, and admin journeys. |
| API integration | VITE_FRONTEND_MODE=api | Actual FastAPI guest sessions, assets, samples, runs, progress, results, evidence, retry/review, bookmarks, feedback, and export. |

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
| /login, /register | Preview accounts and real API guest-access entry |
| /forgot-password, /reset-password | Complete Preview states; unavailable honestly in API mode |
| /profile | Preview profile or API guest-session metadata/logout |
| /chat | Image/sample selection and question workspace |
| /chat/runs/:runId | Run status, answer, evidence, stages, model attempts, actions |
| /heritages, /heritages/:heritageId | Shared Preview catalog; honest unavailable state in API mode |
| /map | Preview list/map synchronization and list-only fallback |
| /favorites | Heritage favorites and saved runs as separate resource types |
| /admin | Preview dashboard |
| /admin/users | Preview user/role/status management |
| /admin/heritages | Preview heritage CRUD using the shared catalog |
| /admin/sources | Preview source metadata; never claims RAG ingestion |
| /admin/runs | Preview-only run monitoring; API owner history stays under /chat |
| /admin/feedback | Preview feedback review |

Preview admin routes require the visible Preview admin role. API mode has no
real admin principal or RBAC, so real administration remains unavailable.
Frontend route guards are presentation controls only.

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

Accounts, heritage catalog/coordinates, heritage favorites and admin APIs are
not implemented by the current backend. Their integration tests are explicitly
skipped; their UI journeys remain available in Preview.

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
or shipped with this frontend; the offline view is a separate coordinate diagram.

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
  against an already-running isolated demo API.

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

- Guest Bearer tokens are kept in memory and attached only to the configured
  API origin/prefix.
- Protected asset images are fetched as authorized Blobs.
- SSE uses authenticated fetch streaming with sequence replay; native
  EventSource cannot supply the required Authorization header.
- Stream disconnect does not cancel a run and does not prove success.
- Idempotency keys are stable for retransmission and new for explicit new
  actions.
- Generated Markdown is rendered without raw HTML execution.
- External links use safe schemes and opener isolation.
- Browser geolocation is requested only after an explicit user action.
- Paid map credentials and hidden geocoding calls are not used.

## Backend boundaries

The current backend provides guest sessions, capabilities/workflow, assets,
sample images, owner-scoped runs, SSE/history, results, sources, workflow-stage
snapshots, model attempts, cancellation, full retry, Judge-only review, run
bookmarks, feedback, and export.

It does not provide email/password accounts, account roles, a heritage catalog,
verified coordinates, heritage favorites, conversation memory, admin APIs,
source/RAG management, tool-call traces, or cross-user monitoring. UI Preview
may simulate these features but never claims backend persistence.

## Documentation

- [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) — implemented backend
  contract, auth, SSE, errors, modes, and security.
- [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) — route, role, endpoint, and
  support-status matrix.
- [docs/MISSING_BACKEND_CAPABILITIES.md](docs/MISSING_BACKEND_CAPABILITIES.md) —
  clearly labeled PROPOSED contracts that are not implemented.
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
