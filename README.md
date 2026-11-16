# Heritage VQA — Di sản Việt Nam qua ảnh

Ứng dụng hỏi đáp bằng ảnh với LangGraph multi-agent, ưu tiên Gemini và cấu hình
provider/model theo từng vai trò. Streamlit, CLI và FastAPI dùng chung workflow.

## Cài đặt

Yêu cầu Python 3.12 và uv.

```powershell
uv sync --locked --group dev
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Chỉ sao chép `.env.example` khi chưa có `.env`. Điền `GEMINI_API_KEY` để gọi model
thật; giữ credential trong `.env` hoặc secret của môi trường triển khai.

## Chạy ứng dụng

```powershell
# API demo: không gọi model trả phí
uv run --locked python -m scripts.serve_api --demo --port 8001

# API dùng model đã cấu hình
uv run --locked python -m scripts.serve_api --port 8000

# Giao diện Streamlit
uv run --locked streamlit run app.py
```

Swagger: <http://127.0.0.1:8001/docs> trong demo, hoặc port 8000 khi chạy live.
Các lệnh server chạy riêng ở từng terminal. Hướng dẫn triển khai PostgreSQL,
worker, Docker và frontend: [API server](docs/api-server.md).

Postman: import [Collection](postman/heritage-vqa.postman_collection.json) và
[Demo environment](postman/heritage-vqa-demo.postman_environment.json), rồi chọn
môi trường trong Postman. Bộ **81 operations / 84 requests** hỗ trợ tài khoản,
hội thoại, biên tập nguồn/media, recovery và SSE. Các thao tác ghi/model/xóa
mặc định tắt, cần bật cờ tương ứng.
[Hướng dẫn Postman](docs/postman.md) · [Thử từng API bằng Swagger](docs/api-swagger-walkthrough.md).

## Deploy Docker trên cổng 8000

Yêu cầu Docker Desktop đang chạy với Linux containers và Docker Compose. Chạy các
lệnh PowerShell từ thư mục `doan_demo`, nơi chứa `compose.yaml`. Khi dùng Docker,
không cần cài Python hoặc uv trên máy host.

Nếu chưa có `.env`, tạo từ mẫu:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Điền cấu hình provider/model và các biến sau trong `.env` trước lần deploy đầu:

- `POSTGRES_PASSWORD`: mật khẩu ngẫu nhiên dạng hex để dùng trong URL kết nối.
- `API_BOOTSTRAP_TOKEN`: token ngẫu nhiên ít nhất 32 ký tự để cấp session.
- `API_MODEL_MODE=live`: dùng model thật; đặt `demo` để thử workflow với dữ liệu mô phỏng.

Giữ nguyên credential đã có khi deploy lại; không commit `.env` vào Git. Compose
cấu hình production với PostgreSQL, API và worker riêng; dữ liệu database và ảnh
được lưu trong Docker volumes.

```powershell
# Kiểm tra cấu hình, build image và chạy các dịch vụ
docker compose config --quiet
docker compose up -d --build --wait

# Kiểm tra container và database/worker readiness
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Readiness thành công trả `status=ready`, `database=true` và `worker=true`.
Swagger: <http://127.0.0.1:8000/docs>. Trong Swagger, nhập `API_BOOTSTRAP_TOKEN`
qua **Authorize** cho header `X-Bootstrap-Token` để tạo session; sau đó dùng
`access_token` của session trong **HTTPBearer**. Health check không gọi model;
tạo run ở chế độ `live` có thể phát sinh phí.

### Cloudflare Tunnel

API được publish tại `127.0.0.1:8000`. Với `cloudflared` chạy trực tiếp trên Windows
cùng máy Docker Desktop, thêm route cho hostname muốn dùng trong Cloudflare Tunnel
và đặt Service URL là `http://127.0.0.1:8000` (HTTP). Sau khi lưu route, mở
`https://<hostname>/docs` hoặc kiểm tra `https://<hostname>/health/ready`.
Tunnel kết nối thành công vẫn cần route này để chuyển request đến API.

### Vận hành và cập nhật

```powershell
# Xem log API và worker; Ctrl+C để thoát xem, server vẫn chạy
docker compose logs -f api worker

# Deploy lại sau khi cập nhật code hoặc .env
docker compose up -d --build --wait

# Dừng và chạy lại các container đã tạo
docker compose stop
docker compose start
```

`docker compose down` gỡ container và network, giữ named volumes. Chỉ thêm `-v`
khi chủ động muốn xóa cả dữ liệu database và ảnh trong volumes.
Chi tiết PostgreSQL, worker, SSE và tích hợp frontend: [API server](docs/api-server.md).

## Workflow và cấu hình

Profile mới tập trung độ chính xác và trải nghiệm: [hanoi-evidence](docs/accuracy-profile.md).
Có nhận định kèm bằng chứng/vùng ảnh, OCR có giới hạn, câu trả lời một phần và hỏi bổ sung
qua API. Thử riêng: `uv run --locked python -m scripts.serve_api --demo --profile hanoi-evidence --port 8001`.
Luồng mặc định được giữ để so sánh; chỉ bật profile mới cho production sau đánh giá pilot.

Kiểm tra đầu vào → điều phối → Visual/Knowledge song song → tổng hợp → đánh giá.
Giao diện có báo cáo trung gian, nguồn trích dẫn, lịch sử phiên và export.
Generation tùy chọn, mặc định tắt. `reviewed` là đánh giá tự động, không bảo đảm
mọi dữ kiện đều chính xác. [Kiến trúc](ARCHITECTURE.md) · [Sơ đồ](docs/langgraph.mmd).

- Cấu hình: [config/default.yaml](config/default.yaml); đổi provider/model/role,
  timeout, token budget, retry và concurrency tại đây hoặc qua biến môi trường.
- LangSmith: đặt `LANGSMITH_TRACING=true`; bật `LANGSMITH_CAPTURE_CONTENT=true`
  để xem prompt/response đã lọc credential. [Hướng dẫn](docs/langsmith.md).
- Log JSON, model diagnostics, metrics và Prometheus: [Observability](docs/observability.md).
- CLI nghiên cứu: `uv run --locked python benchmark_run.py --help`.

## Kiểm tra và tạo lại artifact

```powershell
uv run --locked ruff check .
uv run --locked python -m scripts.check_repo
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m scripts.api_contract_report
uv run --locked python -m scripts.export_postman
```

Tests mặc định dùng mock, chặn mạng ngoài và không cần API key. HTTP report chạy
API/worker demo riêng, tạo bảng và JSON ở `reports/api-contract/results.md` và
`reports/api-contract/results.json`. Các báo cáo theo lượt chạy không commit.
OpenAPI luôn có ở `/openapi.json`; xuất file tùy chọn bằng
`uv run --locked python -m scripts.export_postman --include-openapi`.

## Cấu trúc repository

| Thư mục | Nội dung |
| --- | --- |
| `agents/`, `core/`, `workflow/` | Agent, provider gateway, graph và hợp đồng dữ liệu |
| `api/`, `migrations/` | API, queue, worker và migration SQLite/PostgreSQL |
| `ui/`, `ui_app.py`, `app.py` | Giao diện Streamlit |
| `tests/`, `scripts/` | Regression tests và lệnh vận hành/kiểm tra |
| `docs/`, `deploy/`, `monitoring/` | Tài liệu hiện hành và cấu hình triển khai |
| `postman/`, `samples/` | Collection/environment mẫu và bốn ảnh di sản |

Giữ mã nguồn, tests, migrations, lockfile, cấu hình và tài liệu dùng chung trong
Git. `.env`, dữ liệu người dùng, log, báo cáo chạy thử, virtualenv và công cụ tải
tạm được Git/Docker bỏ qua. Dependency gốc ở `pyproject.toml`; `uv.lock` dùng cho
uv/CI, `requirements.txt` dùng cho pip/Docker.

Catalog di sản cung cấp API danh sách, chi tiết, ảnh và tọa độ từ DB;
xem [triển khai catalog](docs/CATALOG_DATABASE.md). Dữ liệu seed và tọa độ vẫn
là minh họa, không tự trở thành tư liệu đã kiểm chứng. Ảnh catalog do người vận
hành cung cấp qua `API_CATALOG_MEDIA_DIR`; nhánh backend không đóng gói ảnh frontend.

Backend hiện có tài khoản email/password, refresh rotation, user/editor/admin,
hội thoại/lượt chat, memory có giới hạn và yêu thích di tích. REST biên tập hỗ
trợ nguồn có phiên bản draft/reviewed/published, ảnh catalog, entity binding và
audit; giao diện CMS web đầy đủ vẫn chưa được triển khai. Cache retrieval dùng
chung giữa các tiến trình, có giới hạn/TTL và thay đổi revision khi nguồn thay
đổi. API lưu các node đã hoàn tất để replay sau mất worker với kiểm tra lease,
input/build/config/source và ngân sách; không khôi phục giữa một lời gọi model.

API dùng Swagger **1.2.0**, tiền tố `/api/v1`, evidence result schema **2** và
migration head `0009_runtime_state`. Xem [hợp đồng API](docs/api-server.md),
[backend sản phẩm](docs/PRODUCT_PLATFORM_DEPLOYMENT.md) và
[phạm vi nhánh backend](docs/BACKEND_ISOLATION.md).

Giới hạn còn lại: password reset qua email/OIDC/email verification, CMS web,
vector index nếu quy mô cần, streaming từng token và geocoding/routing. Corpus
và bộ gold thực tế vẫn cần người duyệt; quote/evidence ID hợp lệ và test phần
mềm không tự chứng minh độ đúng lịch sử. Maps URL trong kết quả AI là liên kết
tìm kiếm, không phải tọa độ đã xác minh. Công cụ đánh giá không lấy verdict của
model làm ground truth.
