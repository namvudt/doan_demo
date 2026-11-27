# Backend branch scope

The branch is based directly on `origin/main` at
`2e26ed70a1d78ba6f9c96179dd5f70276da4c1cb`. Backend changes were copied into
a separate worktree. The existing `fe` commit and evidence feature commit are
not ancestors introduced by this branch; backend source was reviewed by path.
The original worktree, its branch, index and unrelated local files are preserved.

## Included changes

- Evidence/recognition/clarification workflow, source ingestion and evaluation.
- Database catalog, accounts, conversations, favorites, editorial content/media.
- Public retrieval caching, retention and durable completed-node recovery.
- Backend tests, migrations, operator scripts, Postman contracts and documentation.

Necessary shared changes are limited to backend CI with an isolated PostgreSQL
service, the environment template's profile flags, Docker build identity/media
configuration, ignore rules for operator-provided catalog media, root Compose
profile/build/health settings, backend architecture and usage documentation,
and backend test fixtures. Existing dependency files
already provide the required packages and stay unchanged.

`frontend/**`, `ui/**`, `ui_app.py`, changes to `tests/test_ui.py`, and new UI/map
design documents/screenshots are excluded. Baseline UI files already on `main`
remain unchanged. Shared backend modules can expose new API/result fields without
including a frontend implementation. Unrelated user files and runtime data are
not staged or removed.

Three UI-specific tests from the new mixed test modules are omitted:
`test_remote_adapter_preserves_evidence_and_continues_pending_run`,
`test_ui_guided_mode_is_explicit_and_invalidates_blind_result`, and
`test_remote_adapter_preserves_recognition_and_hint`. Their original copies
remain in the frontend worktree; existing tests already on `main` are unchanged.

## Media and cleanup

Catalog media uses `API_CATALOG_MEDIA_DIR`, defaulting to `catalog-media/`,
instead of depending on frontend assets. Images are externally provisioned;
the seven seed filenames and read-only Docker mounting are documented in
[CATALOG_DATABASE.md](CATALOG_DATABASE.md). Seed `--dry-run` fails before any
database/migration writes when required files or fields are missing.

No source files were deleted: reference review found no backend implementation
proven redundant. Generated artifacts, caches, local databases, reports and
credentials remain excluded by ignore rules. Frontend artifacts
and unrelated untracked files are preserved in the original worktree.

## Validation

Validation on 2026-11-16 used Python 3.12 in the isolated worktree:

- Offline pytest: 352 passed. The two subsequently added deployment-route
  regression tests also passed separately; the final collection has 354 tests.
- Ruff lint and formatting: passed for all 150 Python files.
- Real HTTP contract runner: 165/165 cases passed, covering all 81 OpenAPI
  operations. Its UUID-scoped temporary media directory contains a generated
  synthetic JPEG; no frontend image or operator data is required.
- Docker build: passed from this backend-only tree, with no frontend COPY.
- Alembic: one head, `0009_runtime_state`. SQLite and PostgreSQL test fixtures
  apply the merged migration history to isolated databases/schemas.
- PostgreSQL 17 CI selection: 91 tests passed on the first Linux-container
  run. The remaining legacy Streamlit/HTTP integration test initially could
  not write its default log directory in the read-only source mount; it passed
  with `API_LOG_DIR` directed to writable temporary storage, without code edits.
  The Windows psycopg binary was blocked by host application-control policy,
  so PostgreSQL checks ran in disposable Linux containers instead.
- Repository index check: 182 tracked files passed artifact/recognized-key
  scanning; additional private-key/GitHub-token/AWS-key pattern checks were clean.
- Scope: 71 added files, 46 modified files, no deleted files; no changed
  frontend/UI paths and no frontend commit in the new branch history.
- Preservation: SHA-256 verification of all 323 Git-visible original files and
  the original Git index found no changes or added Git-visible files.

The test databases, schemas, credentials and media are synthetic and isolated
from existing deployments. Paid model calls and live deployment/restore
operations were not run. Software tests do not establish historical accuracy
or convert the draft evaluation data into human-reviewed gold labels.
