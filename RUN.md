## Terminal 1 — Backend

```powershell
.\.venv\Scripts\Activate.ps1
$env:API_CATALOG_MEDIA_DIR = "catalog-media"
python -m scripts.serve_api --port 8001
```

## Terminal 2 — Frontend

```powershell
cd frontend
$env:VITE_FRONTEND_MODE = "api"
$env:VITE_ALLOW_LIVE_MODEL_CALLS = "true"
npm run dev
```

## Địa chỉ truy cập

- Frontend: http://127.0.0.1:5173
- Backend Swagger: http://127.0.0.1:8001/docs
