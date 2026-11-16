# Dev integration

`dev` combines the independently published frontend and backend branches:

| Source | Commit | Scope |
| --- | --- | --- |
| `main` | `2e26ed7` | Shared starting point |
| `fe` | `8c2826e` | React product/API integration, maps, AI chat, frontend tests and design notes |
| `be/evidence-product-platform` | `06f44d4` | Evidence workflow, 81 API operations, accounts/content/catalog, persistence and backend tests |

Both feature branches were merged with merge commits. Neither merge required
conflict resolution. Backend implementation was not added to the new frontend
commit, and the backend branch remains independently usable.

The combined tree also receives the legacy Streamlit presentation/HTTP-adapter
changes in `ui/`, `ui_app.py` and `tests/test_ui.py`. They need the new backend
evidence fields and therefore belong to this integration. Two remote-adapter
regressions live in `tests/test_ui_remote_evidence.py`, separate from backend
workflow tests. They preserve evidence/recognition, provenance and clarification
when the UI calls a real in-process API with a fake model.

## Running the combined application

Preview needs only the frontend:

```powershell
Set-Location frontend
npm ci
$env:VITE_FRONTEND_MODE = "preview"
npm run dev
```

For the local demo API, run these commands from the repository root:

```powershell
docker compose -f frontend/docker/compose.demo.yaml build api
docker compose -f frontend/docker/compose.demo.yaml up -d --no-build --pull never
docker compose -f frontend/docker/compose.demo.yaml exec -T api python -m scripts.seed_catalog
```

The frontend-specific Dockerfile provisions its bundled catalog photos and sets
`API_CATALOG_MEDIA_DIR`. This differs from the backend-only root deployment,
which expects operator-provisioned media as described in
[CATALOG_DATABASE.md](CATALOG_DATABASE.md). Seeding adds missing records; replacing
existing content requires the separate explicit `--replace` option.

Start the browser UI in another terminal:

```powershell
Set-Location frontend
$env:VITE_FRONTEND_MODE = "api"
npm run dev
```

The Vite proxy uses the demo API at `127.0.0.1:8001`. The API advertises its
actual capabilities and model mode; the frontend does not enable missing
features or silently substitute Preview records after an API failure.

## Verification

Fresh merged-tree verification on 16 November 2026:

| Check | Result |
| --- | --- |
| Complete offline Python suite | 360 passed, including legacy UI and both remote-adapter regressions |
| Python lint/format | Ruff passed; 164 files formatted |
| Fresh frontend install | `npm ci` passed using the committed lockfile |
| Frontend typecheck/lint/unit/build | Passed; 60 unit tests across 10 files |
| Browser Preview | 7/7 passed; optional API/live/provider suites disabled |
| Actual HTTP demo contract | 165/165 cases, 81/81 operations, no paid calls; isolated temporary SQLite/API/worker |
| Dependency audit | Production: 0 vulnerabilities; npm reports 7 moderate development advisories |
| Combined Docker packaging | Frontend Dockerfile build passed under separate tag `heritage-dev-integration:20261116` |
| Packaged catalog seed | Network-disabled dry-run passed: 8 records, 7 published |

The dependency lockfile was preserved; no automatic dependency upgrades were
applied. The HTTP runner and Preview server stopped their owned processes.
Historical deployment observations in
[frontend validation](../frontend/docs/VALIDATION.md) retain their original
scope. The earlier 16-case Docker UI set and paid-model acceptance were not
rerun by this merge check. No production-hosting or historical-accuracy claim
is made from the offline/demo test results.

No paid model calls or existing-stack redeployment are part of this merge
verification. Credentials, local `.env` files, `.api-demo`, databases, dependency
directories and request traces are excluded from the published commits.
Human historical review, provider quota availability, full CMS screens and
email recovery remain separate from software/merge acceptance.
