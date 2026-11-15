# API contract notice

The proposed contract inherited from heritage-frontend.zip is obsolete and is
not used by the working HTTP adapter.

Use:

- [API_INTEGRATION.md](API_INTEGRATION.md) for the backend operations that
  actually exist in this repository;
- [FEATURE_MATRIX.md](FEATURE_MATRIX.md) for supported, Preview-only, and
  blocked product features;
- [MISSING_BACKEND_CAPABILITIES.md](MISSING_BACKEND_CAPABILITIES.md) for
  clearly labeled PROPOSED future contracts.

The running FastAPI server publishes the authoritative machine-readable schema
at /openapi.json. The repository intentionally does not commit a second
frontend-generated OpenAPI file because it can drift from api/main.py and
api/schemas.py.

Do not add a proposed endpoint to src/api/contracts.ts or src/api/http.ts until
the backend implementation, authorization, OpenAPI operation, and integration
tests exist.
