# Frontend verification

This document gives reproducible, secret-free commands for Preview and the
explicit API suites. Run them from a fresh terminal. Do not print, copy, rename, or modify
the repository root .env.

The frontend changes after baseline `6d614e3` depend on
`be/evidence-product-platform` at `06f44d4` for the new API journeys (81 OpenAPI
operations, migration head `0009_runtime_state`). The `dev` integration
combines both branches. Fresh merged-tree checks are recorded in
[DEV_INTEGRATION.md](../../docs/DEV_INTEGRATION.md); the earlier 16-case UI
deployment record retains its original scope in [VALIDATION.md](VALIDATION.md).
Preview needs no backend. New product actions require the matching capability
flags and do not fall back to Preview data on older servers.

## Prerequisites

- Python 3.12
- uv
- Node.js 22.12 or newer
- npm
- A matching Playwright Chromium or installed Chrome/Edge for browser tests

Install locked dependencies:

~~~powershell
# Repository root
uv sync --locked --group dev

Set-Location frontend
npm ci
Set-Location ..
~~~

The committed package-lock.json matches the current dependency manifest.

## Track A — isolated API demo

The --demo switch prevents paid model calls, but by itself it does not isolate
the database, assets, or queue. The following environment creates a new
temporary SQLite database and asset directory for this terminal.

### Terminal 1: start the isolated backend

Run from the repository root:

~~~powershell
$ApiTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("heritage-fe-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $ApiTestRoot | Out-Null

$ApiDbFile = (Join-Path $ApiTestRoot "api.sqlite").Replace("\", "/")
$env:API_ENV = "development"
$env:API_MODEL_MODE = "demo"
$env:API_EMBEDDED_WORKER = "true"
$env:DATABASE_URL = "sqlite:///$ApiDbFile"
$env:API_DATA_DIR = Join-Path $ApiTestRoot "data"
$env:API_CORS_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174"
$env:API_BOOTSTRAP_TOKEN = ""
$env:API_OPERATIONS_TOKEN = ""

$env:LANGSMITH_TRACING = "false"
$env:LANGSMITH_CAPTURE_CONTENT = "false"
$env:LANGSMITH_API_KEY = ""
$env:GEMINI_API_KEY = ""
$env:OPENAI_API_KEY = ""
$env:KNOWLEDGE_API_KEY = ""
$env:JUDGE_API_KEY = ""

uv run --locked python -m scripts.serve_api --demo --port 8001
~~~

Keep that terminal open. It must report the API at port 8001. The temporary
path is intentionally outside the repository and is unique per run. Do not
attach another API/worker process to its database.

### Terminal 2: prove mode and readiness

~~~powershell
$Capabilities = Invoke-RestMethod "http://127.0.0.1:8001/api/v1/capabilities"
if ($Capabilities.model_mode -ne "demo") {
  throw "Refusing integration test: backend model_mode is not demo."
}

$Ready = Invoke-WebRequest "http://127.0.0.1:8001/health/ready" -SkipHttpErrorCheck
if ($Ready.StatusCode -ne 200) {
  throw "Backend worker is not ready."
}
~~~

Do not infer mode from port 8001. The capabilities response is the proof.

Run the repository’s HTTP smoke test:

~~~powershell
uv run --locked python -m scripts.api_smoke --url http://127.0.0.1:8001
~~~

The smoke test creates an ephemeral guest session and verifies sample asset,
run creation, progress, result, sources, feedback, SSE, and session revocation.
It refuses a live backend unless an explicit paid-call flag is passed; do not
pass that flag for frontend verification.

### Terminal 3: start frontend in API integration mode

~~~powershell
Set-Location frontend
$env:VITE_FRONTEND_MODE = "api"
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001/api/v1"
$env:VITE_API_TIMEOUT_MS = "30000"
npm run dev
~~~

Open http://127.0.0.1:5173. The frontend must:

- read capabilities and visibly identify backend demo output;
- offer guest access and capability-gated real account registration/login;
- keep account access/refresh credentials in tab memory and support explicit
  refresh/logout without migrating Preview or guest data into an account;
- refuse run-producing actions unless the model-mode gate permits them
  (the demo suites require model_mode=demo and disable live calls);
- never switch to Preview fixtures after an HTTP error;
- fetch protected images with Bearer authorization;
- follow new IDs returned by retry and Judge-only review;
- keep run bookmarks distinct from heritage favorites.

With the isolated API still running, exercise that path through the real
frontend transport and UI:

~~~powershell
Set-Location frontend
$env:RUN_API_INTEGRATION = "1"
$env:VITE_API_BASE_URL = "/api/v1"
npm run test:e2e
Remove-Item Env:RUN_API_INTEGRATION
~~~

The API browser test creates and revokes its own guest session, selects a genuine
backend sample, runs the demo workflow, reads the protected asset and result,
and verifies stages, model attempts, bookmarking, feedback, and JSON export.
RUN_API_INTEGRATION=1 selects only api-live.spec.ts and forces API mode.
RUN_CATALOG_API=1, RUN_EVIDENCE_API=1 and RUN_PRODUCT_API=1 select their own
API suites. Choose one explicit flag at a time and clear it after the run.
With no suite flag the configuration selects app.spec.ts and forces Preview.
With a direct API URL, its CORS origins must include http://127.0.0.1:5174.

If session_bootstrap_required is true, stop. Do not place the bootstrap secret
in the browser. Restart the isolated development API without a bootstrap token
or use an operator-issued guest token.

### API integration checklist

Verify in one owner session:

1. Session creation or validation and GET /sessions/me.
2. Genuine samples and image upload validation.
3. Authorized image preview.
4. One run created with a stable Idempotency-Key.
5. Event history and authenticated SSE reconnect from a saved sequence.
6. No duplicate run after reconnect or retransmission.
7. queued, running, cancel_requested, succeeded, failed, and cancelled UI
   handling, using targeted fixtures for states not naturally reached.
8. Final answer, separate result/evidence status, sources, stages, and model
   attempts.
9. Bookmark, saved-run list, feedback, and JSON/Markdown export.
10. Full retry and Judge-only review as separate child runs.
11. Session expiration/revocation, subscription cleanup, and loss of access to
    owned history.
12. Missing account/conversation/favorite capabilities show honest unavailable
    states; catalog capability failures do not use fixtures. React admin/CMS
    pages remain Preview-only even though authorized editorial REST exists.

Also verify these failures without switching data source:

- malformed or oversized upload;
- blank/overlong question;
- 401 expired token;
- 404 cross-owner or missing resource;
- 409 active run, unfinished result, idempotency conflict, or asset in use;
- 429 quota response;
- 503 readiness/provider configuration response;
- network loss and fragmented SSE chunks.

The 429 and provider error views may be covered with typed adapter/component
fixtures rather than changing backend quotas or contacting a provider.

### Persisted catalog against Docker PostgreSQL

Deploy and seed the local stack using
[CATALOG_DATABASE.md](../../docs/CATALOG_DATABASE.md), then run:

~~~powershell
Set-Location frontend
$env:RUN_CATALOG_API = "1"
npm run test:e2e
Remove-Item Env:RUN_CATALOG_API
~~~

This suite reads the actual API catalog and image bytes, verifies one record's
identity across list/detail/map, checks filter state after reload, and imports
a catalog photo into an ephemeral guest composer. It revokes that session,
blocks non-local traffic and asserts no run was submitted. Map tiles use the
offline schematic, so this does not measure a map provider.

The temporary SQLite setup above starts with an empty catalog unless seeded.
Backend catalog tests in tests/test_catalog.py cover persistence after creating
a fresh application instance, draft/public visibility, operations auth and
version conflict, coordinate proof validation, safe media paths, bridge
ownership and repeatable seed behavior.

### Product and evidence suites against the matching demo backend

Use the deployed and seeded matching backend, with a ready worker and
`model_mode=demo`. The product suite also requires the accounts, conversations
and heritage_favorites flags; the evidence suite requires the evidence profile
and public catalog. Run separately from `frontend/`:

~~~powershell
$env:RUN_PRODUCT_API = "1"
npm run test:e2e
Remove-Item Env:RUN_PRODUCT_API

$env:RUN_EVIDENCE_API = "1"
npm run test:e2e
Remove-Item Env:RUN_EVIDENCE_API
~~~

Product tests exercise synthetic account registration, refresh, logout/login,
persisted heritage favorites and conversations. Guest conversation coverage
opts into memory, explicitly submits one demo run, reads history and forgets
future memory without erasing messages. Creating/selecting a conversation or
favorite never silently creates an AI run. Tests block non-local traffic and
revoke test sessions. Account IDs only are recorded in the ignored QA cleanup
manifest; an operator may disable those exact synthetic accounts afterwards.
Bearer traces are disabled for these suites.

Evidence tests exercise actual API evidence and crop bytes. The pending-state
UI case is explicitly a fixture; it does not prove a live model generated a
clarification. Neither suite invokes paid providers. Full CMS screens, email
reset/verification and human approval of gold cases remain separate work.

## Track B — UI Preview

UI Preview needs no server and must not collect real credentials.

~~~powershell
Set-Location frontend
$env:VITE_FRONTEND_MODE = "preview"
$env:VITE_API_BASE_URL = "/api/v1"
$env:VITE_MAP_TILE_URL = ""
npm run dev
~~~

Open http://127.0.0.1:5173 and confirm the persistent banner:

> UI Preview — Dữ liệu mô phỏng, chưa lưu lên backend

Preview checklist:

1. Register, login, intended-route redirect, profile, and logout.
2. Forgot/reset-password messages state that no email/account is real.
3. Guest, user, and admin navigation.
4. Direct access to protected/admin routes and 403 handling.
5. Heritage search, filtering, detail, favorite, map selection, and Chat
   navigation.
6. Shared Preview catalog consistency after admin create/edit/delete.
7. Stable illustrative IDs and visible provenance/coordinate quality.
8. Missing coordinates, no results, tile failure, and list-only map fallback.
9. Browser geolocation only after an explicit click; denial is handled.
10. Preview runs, bookmarks, feedback, and export never claim server storage.
11. Loading, empty, invalid input, session expiry fixture, 403, 404, and server
    failure views.
12. Switching Preview/API mode does not reuse identities, tokens, IDs, uploads,
    records, or caches.

## Static, unit, build, and browser commands

Run from frontend:

~~~powershell
$env:VITE_FRONTEND_MODE = "preview"
$env:VITE_API_BASE_URL = "/api/v1"
$env:VITE_MAP_TILE_URL = ""

npm run typecheck
npm run lint
npx prettier --check "src/**/*.{ts,tsx,css}" "tests/**/*.{ts,tsx}" "*.ts"
npm test
npm run build
~~~

ESLint is the semantic lint check. The additional Prettier command checks
formatting and must not be reported as a substitute for ESLint.

Run browser tests:

~~~powershell
Remove-Item Env:RUN_API_INTEGRATION -ErrorAction SilentlyContinue
Remove-Item Env:RUN_CATALOG_API -ErrorAction SilentlyContinue
Remove-Item Env:RUN_EVIDENCE_API -ErrorAction SilentlyContinue
Remove-Item Env:RUN_PRODUCT_API -ErrorAction SilentlyContinue
Remove-Item Env:RUN_LIVE_UI -ErrorAction SilentlyContinue
Remove-Item Env:RUN_MAP_PERF -ErrorAction SilentlyContinue
Remove-Item Env:RUN_SCROLL_PERF -ErrorAction SilentlyContinue
Remove-Item Env:RUN_MAPBOX_UI -ErrorAction SilentlyContinue
Remove-Item Env:RUN_CHAT_UI -ErrorAction SilentlyContinue
npm run test:e2e
~~~

Playwright selects only app.spec.ts and forces Preview mode, even when
VITE_FRONTEND_MODE was previously set to api. It starts and stops its own
Vite server at http://127.0.0.1:5174 with server reuse disabled. Keep port
5174 free; a development server on port 5173 can remain running.

Browser resolution tries an explicit PLAYWRIGHT_CHROMIUM_EXECUTABLE, matching
bundled Chromium, then installed Chrome/Edge. The explicit path is optional.
If no browser is available, run npx playwright install chromium and retry.
CI can install that matching browser before running the suite.

Fixture HTTP tests do not prove compatibility with the real FastAPI process.

Run backend contract regression tests from the repository root:

~~~powershell
uv run --locked pytest tests/test_api.py tests/test_catalog.py tests/test_review_recovery.py tests/test_postman_export.py
~~~

After merging both branches, the legacy Streamlit HTTP adapter regressions
are isolated from backend tests in a frontend-owned module:

~~~powershell
uv run --locked pytest tests/test_ui.py tests/test_ui_remote_evidence.py
~~~

These tests use fake model responses and an in-process TestClient with
MockTransport. They require the matching backend Python code but no running
server or provider credentials. Do not report them as browser or deployed
HTTP verification.

Run the complete repository suite when time permits:

~~~powershell
uv run --locked pytest
~~~

## Production build and deep-link check

~~~powershell
Set-Location frontend
$env:VITE_FRONTEND_MODE = "preview"
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
~~~

Open direct deep links such as:

- http://127.0.0.1:4173/chat
- http://127.0.0.1:4173/heritages
- http://127.0.0.1:4173/map
- a known /chat/runs/{runId} route
- /admin and an admin child route in Preview
- an unknown path

The Vite preview server is only a local check. Production hosting must provide
SPA fallback to index.html while preserving API and asset paths.

## Test result reporting

Record each command, exit code, environment mode, and date. For integration
tests, record the capabilities model_mode and isolated temporary-data path but
never the session token or request Authorization header.

Only claim:

- browser testing when Playwright actually ran;
- screenshots when the stated viewport was captured;
- API integration when a real isolated FastAPI process was exercised;
- security checks that were explicitly performed;
- lint when an actual linter, not only TypeScript or Prettier, ran.

Compilation and a production build do not prove API integration, authorization,
SSE recovery, or real RBAC.
