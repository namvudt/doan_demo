# Frontend deployment

## Development topology

The default Vite development server is http://127.0.0.1:5173. Its proxy sends
both /api and /health to the isolated backend demo at
http://127.0.0.1:8001.

Start the backend with a fresh database and asset directory by following
[TESTING.md](TESTING.md). The supported launcher is:

~~~powershell
uv run --locked python -m scripts.serve_api --demo --port 8001
~~~

The --demo flag does not isolate existing data by itself.

Start the frontend:

~~~powershell
Set-Location frontend
$env:VITE_FRONTEND_MODE = "api"
$env:VITE_API_BASE_URL = "/api/v1"
npm run dev
~~~

For UI Preview, set VITE_FRONTEND_MODE=preview; no backend is required.

## Static build

~~~powershell
Set-Location frontend
npm run lint
npm run typecheck
npm test
npm run build
~~~

The output is dist/. VITE_* values are embedded at build time and are public.
Do not put guest tokens, bootstrap tokens, operations tokens, provider keys,
database credentials, or passwords in them.

Set VITE_API_BASE_URL=/api/v1 for a same-origin production deployment. Hosting
must return index.html for frontend deep links while leaving /api, /health, and
static assets untouched.

## Reverse proxy example

This Nginx example assumes the frontend and API share one HTTPS origin and the
API listens privately at 127.0.0.1:8000. Replace paths, hostname, certificates,
and limits for the actual deployment.

~~~nginx
server {
    listen 443 ssl http2;
    server_name heritage.example.org;

    root /var/www/heritage/frontend/dist;
    index index.html;
    client_max_body_size 12m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Required for timely SSE delivery.
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    location /health/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /assets/ {
        try_files $uri =404;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
~~~

The backend already returns X-Accel-Buffering: no for its SSE response. The
proxy must still disable response buffering.

## Cross-origin alternative

If the frontend and API use different origins:

- build with an absolute VITE_API_BASE_URL ending in /api/v1;
- list the exact frontend origin in API_CORS_ORIGINS;
- keep credentials out of the URL;
- allow and expose the headers documented in API_INTEGRATION.md;
- serve both origins over HTTPS;
- verify that Authorization is attached only to the configured API
  origin/prefix.

Do not configure wildcard origins. The existing backend uses Bearer guest
tokens, not browser cookies.

## Session bootstrap

Production requires an API bootstrap token to issue guest sessions. That token
must remain server/operator-side. The browser must receive only an
operator-issued guest access token or use a future authorized server flow.
Never expose X-Bootstrap-Token through VITE_* configuration.

API_OPERATIONS_TOKEN is also server-only. /api/v1/operations/metrics is not a
product admin endpoint.

## Map provider

The default tile URL is OpenStreetMap and requires network access. Confirm the
provider’s attribution, caching, and traffic policy before public deployment.
For an offline deployment, build with VITE_MAP_TILE_URL empty. The
application must retain its synchronized list and no-location/tile-failure
states.

No paid map credential or hidden geocoding call is required by this frontend.

## Deployment checklist

- Build mode is explicitly preview or api.
- API mode capabilities reports the expected backend mode.
- Production API and worker use the same configuration, database, and asset
  storage.
- Static hosting supports refresh/deep links for every frontend route.
- /api/v1/assets/{id}/content works through authenticated Blob fetch.
- SSE arrives incrementally, resumes by sequence, and is not cached.
- X-Request-ID and Location are exposed where cross-origin access is used.
- Unsupported account/catalog/map/admin features remain unavailable in API
  mode.
- Preview banner remains present in Preview builds.
- Source maps, logs, screenshots, and monitoring contain no tokens or private
  uploads.
- HTTPS, backups, retention, CORS, and provider/tile policies are reviewed by
  the deployment owner.
