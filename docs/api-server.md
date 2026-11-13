# Backend API và Swagger UI

Backend dùng FastAPI, gọi cùng `RunService`/LangGraph của Streamlit và CLI.
Swagger có 33 HTTP operations, chia theo Health, Sessions, Configuration, Assets,
Runs, Events, Results, Feedback và Operations. OpenAPI có schema, Bearer Authorize, multipart
upload và ví dụ để thử nhanh.

Hướng dẫn thao tác chi tiết từng endpoint và cách đọc response:
[api-swagger-walkthrough.md](api-swagger-walkthrough.md).
Bảng kết quả HTTP được sinh local bằng `python -m scripts.api_contract_report`,
ghi tại `reports/api-contract/results.md` và `results.json`, không commit.
Log JSON, durable model attempts, metrics có token riêng và cấu hình Prometheus:
[observability.md](observability.md).

Bộ JSON import Postman (collection, demo/local environments và OpenAPI schema):
[hướng dẫn Postman](postman.md).

## Chạy local

Tại thư mục `doan_demo`, dùng Python 3.12 và dependency đã khóa:

```powershell
uv sync --locked --group dev
uv run --locked python -m scripts.serve_api
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

Mặc định là **live**: dùng key/model trong `.env`, có thể phát sinh phí khi tạo
run. Khởi động server, mở Swagger và kiểm tra cấu hình không tự gọi model.

Thử toàn bộ workflow bằng dữ liệu mô phỏng, không cần key:

```powershell
uv run --locked python -m scripts.serve_api --demo
```

Demo đi qua graph thật với provider và nguồn giả lập có nhãn DEMO, không đánh giá
chất lượng thực. Demo tắt trace nội dung ra LangSmith. `/capabilities`, run và
result đều trả `model_mode`. CLI `--demo` ghi đè mode trong `.env` cho tiến trình.

Local dùng SQLite tại `data/api.sqlite`, ảnh chuẩn hóa ở `data/assets` và một
worker nền trong tiến trình API. Các thư mục dữ liệu được Git/Docker build bỏ qua.
Thêm `--port 8001` khi cần đổi cổng; `--reload` chỉ dùng trong phát triển.

## Thử bằng Swagger

1. Mở `GET /api/v1/capabilities`: kiểm tra `model_mode`, giới hạn và
   `model_configured`. Trường này chỉ kiểm tra cấu hình, không xác thực kết nối model.
2. Mở `POST /api/v1/sessions`, chọn **Try it out**, nhập label rồi **Execute**.
   Nếu server yêu cầu bootstrap, nhập `X-Bootstrap-Token` qua Authorize trước.
3. Sao chép `access_token`. Nhấn **Authorize** ở đầu trang, dán token vào mục
   **HTTPBearer**, không thêm chữ `Bearer`.
4. Upload ảnh qua `POST /api/v1/assets`, hoặc dùng
   `POST /api/v1/samples/chua_mot_cot/assets`. Ghi lại `asset_id`.
5. Gọi `POST /api/v1/runs`:

```json
{
  "asset_id": "UUID của ảnh",
  "question": "Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?",
  "audience": "tourist",
  "profile": "default"
}
```

6. API trả HTTP 202 và `run_id`. Đọc `GET /runs/{id}` và
   `GET /runs/{id}/events/history` để quan sát. Các đường dẫn này có tiền tố
   `/api/v1` đầy đủ trên Swagger.
7. Đọc `/result` khi có kết quả. Bật `include_intermediate=true` để lấy bản nháp
   và báo cáo từng bước; `/steps`, `/sources`, `/metrics` xem dữ liệu riêng.
8. Thử `/bookmark`, `/feedback` và `/export?format=markdown` hoặc `json`.

Gửi `Idempotency-Key` khi tạo run: cùng chủ sở hữu, cùng key và body trả lại run
cũ; body khác trả 409. Endpoint `/retry` bắt buộc key và chỉ chấp nhận run đã kết
thúc. Retry tạo run mới, dùng cấu hình hiện tại và có thể phát sinh phí.

`/events` là kết nối SSE; Swagger có thể chờ đến khi kết nối đóng. Dùng
`/events/history` để thử bằng JSON. Mở lại trang hay kết nối SSE không tạo run mới.

## Danh mục endpoint

### Kiểm tra model và phục hồi Judge

Sau khi Authorize, gọi `POST /api/v1/preflight` với:

```json
{"roles":["coordinator","visual","aggregator","judge"],"force":false}
```

HTTP 200 chứa `ready` và kết quả từng role: provider/model, mã lỗi,
`error_category`, `retryable`, `provider_status_code`, `provider_reason`, `cached`.
`ready=false` là kiểm tra không đạt dù request kiểm tra trả 200. Request chỉ đọc
metadata model, không sinh nội dung; `generation_verified=false` vì chưa kiểm tra
quota hay khả năng sinh câu trả lời. `/capabilities` vẫn chỉ kiểm tra có cấu hình.

Trước run đầy đủ, hệ thống tự kiểm tra coordinator/visual/aggregator/judge. Role
knowledge/generation được kiểm tra sau khi coordinator chọn, trước khi gọi experts.
Khi admission không đạt, `/runs` trả 503 với `error.code` và `error.details.roles`,
chưa thêm job vào hàng đợi. Worker kiểm tra lại khi bắt đầu thực thi.

Kết quả kiểm tra được cache theo provider/model/credential/endpoint trong từng
process. YAML `preflight_ttl_seconds` mặc định 300, lỗi cache tối đa 15 giây,
`preflight_timeout_seconds` mặc định 5 giây. `force=true` bỏ qua cache đã hoàn tất;
request trùng đang chạy được dùng chung. Thay credential/model sẽ đổi cache key.
Cache này không dùng chung giữa API và worker và không chứa key trong response/log.

Nếu đã có bản nháp, ảnh và bằng chứng, gọi:

```http
POST /api/v1/runs/{run_id}/review
Authorization: Bearer <session-token>
Idempotency-Key: <unique-review-key>
```

Không có body. HTTP 202 trả `run_kind=review`, `parent_run_id` và run ID mới.
Gọi `/runs/{new_id}/events` hoặc `/events/history`, `/result`, `/metrics` như run
thường. Chỉ Judge chạy lại; expert reports, plan, ảnh và draft giữ nguyên.
Stage dùng lại có `payload.reused=true`, `source_run_id`, duration bằng 0.
Metrics chỉ tính các model attempts của lần đánh giá mới; Judge vẫn có thể retry
theo budget nếu gặp lỗi tạm thời/truncation. Run gốc được giữ nguyên.

Thiếu `Idempotency-Key` trả 422, run đang hoạt động trả 409/`run_active`, thiếu
artifact hoặc nguồn bắt buộc trả 409/`review_artifacts_missing`, khác mode trả
409/`mode_mismatch`, sai chủ sở hữu trả 404. Repeated key cùng thao tác trả run con
cũ; dùng key đó cho full retry trả 409. Review dùng cấu hình Judge hiện tại và có
thể phát sinh phí model. `/retry` vẫn chạy lại toàn bộ workflow.

Trong UI, nút **Đánh giá lại** chỉ bật khi đủ dữ liệu. Lịch sử phiên giữ ảnh đã
chuẩn hóa trong bộ nhớ (tối đa 8 lượt, tổng ảnh 40 MB; ảnh cũ được giải phóng trước
khi vượt giới hạn), không dùng thumbnail để đánh giá. Lượt mới
hiện nhãn giai đoạn dùng lại, nguồn và liên kết run gốc. Lượt cũ từ trước bản cập
nhật có thể cần chạy lại đầy đủ để lưu ảnh phục vụ chức năng này.

Review lỗi giữ `status=unverified`, không đưa draft thành đáp án đã kiểm chứng:

| `error_category` | Ví dụ `error_code` | Xử lý |
| --- | --- | --- |
| `configuration` | `credential_invalid`, `permission_denied`, `model_not_found` | Sửa role credential/model, restart API và worker |
| `technical` | `provider_unavailable`, `output_token_limit` | Kiểm tra dịch vụ/budget; đánh giá lại khi sẵn sàng |
| `review_format` | `review_schema_invalid` | Đánh giá lại riêng Judge |
| `evidence` | `missing_evidence`, `unknown_citation`, `missing_citation`, `model_generated_url` | Kiểm tra/bổ sung nguồn; đánh giá lại không tự truy xuất nguồn mới |

`retryable` chỉ khả năng lỗi kỹ thuật/định dạng có thể hết khi thử lại, không
phải trạng thái nội dung bị bác bỏ. Nguồn và schema hợp lệ chưa chứng minh mọi
dữ kiện đều đúng; kết quả `INSUFFICIENT_EVIDENCE` vẫn được hiển thị đúng nhãn.

| Method | Đường dẫn | Chức năng |
| --- | --- | --- |
| GET | `/health/live`, `/health/ready` | Tiến trình, database và worker heartbeat |
| POST | `/api/v1/sessions` | Cấp token phiên, chỉ trả token thô một lần |
| GET, DELETE | `/api/v1/sessions/me` | Xem/thu hồi token; thu hồi yêu cầu hủy các run đang chờ/chạy |
| GET | `/api/v1/capabilities`, `/api/v1/workflow` | Giới hạn, mode, config hash và sơ đồ workflow |
| POST, GET | `/api/v1/assets` | Upload và liệt kê ảnh của phiên |
| GET, DELETE | `/api/v1/assets/{id}` | Metadata và xóa ảnh chưa được run sử dụng |
| GET | `/api/v1/assets/{id}/content` | Tải ảnh PNG đã bỏ EXIF |
| GET | `/api/v1/samples` | Danh sách ảnh mẫu |
| POST | `/api/v1/samples/{sample_id}/assets` | Tạo asset riêng từ ảnh mẫu |
| POST, GET | `/api/v1/runs` | Tạo run, liệt kê lịch sử có phân trang/lọc |
| GET | `/api/v1/runs/{id}` | Trạng thái thực thi và kết quả |
| POST | `/api/v1/runs/{id}/cancel`, `/retry` | Hủy hợp tác hoặc chủ động chạy lại |
| POST | `/api/v1/preflight` | Kiểm tra credential/model theo role, không sinh nội dung |
| POST | `/api/v1/runs/{id}/review` | Tạo run con, dùng lại ảnh/nguồn/bản nháp, chỉ chạy Judge |
| GET | `/api/v1/runs/{id}/events` | SSE, hỗ trợ `Last-Event-ID` và `after` |
| GET | `/api/v1/runs/{id}/events/history` | Lịch sử JSON có cursor và limit |
| GET | `/api/v1/runs/{id}/result`, `/steps`, `/sources`, `/metrics`, `/export` | Kết quả và bằng chứng |
| GET | `/api/v1/operations/metrics` | Prometheus metrics; cần operations token riêng |
| PUT | `/api/v1/runs/{id}/bookmark` | Đánh dấu hoặc bỏ đánh dấu |
| POST, PUT, GET | `/api/v1/runs/{id}/feedback` | Ghi và đọc phản hồi |

HTTP 401: token thiếu/hết hạn; 404: resource không tồn tại hoặc không thuộc phiên;
409: xung đột idempotency/ảnh đang dùng/kết quả chưa sẵn sàng; 413: quá dung lượng;
422: dữ liệu không hợp lệ; 429: quota; 503: cấu hình provider chưa đủ.
Lỗi có `error.code`, `error.message`, `error.request_id`; header có `X-Request-ID`.
Validation không phản chiếu nội dung câu hỏi, file hoặc credential vào lỗi.

## Tích hợp frontend

Frontend giữ access token phiên rồi gửi `Authorization: Bearer <token>`.
Token bootstrap chỉ dùng ở backend/Swagger của người vận hành, không nhúng vào
bundle frontend. Phiên hiện tại là guest session có quyền sở hữu, chưa phải hệ
thống tài khoản/password/OIDC. Có thể gắn hệ thống đăng nhập ở bước tiếp theo.

```javascript
const response = await fetch(`${baseUrl}/api/v1/runs`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${sessionToken}`,
    "Content-Type": "application/json",
    "Idempotency-Key": crypto.randomUUID()
  },
  body: JSON.stringify({ asset_id: assetId, question, audience: "tourist" })
});
const run = await response.json();
```

Theo dõi bằng fetch streaming hoặc polling `/events/history?after=N`; gộp theo
`sequence`. Native `EventSource` không cho đặt tùy ý Authorization header, vì vậy
frontend dùng Bearer nên chọn fetch streaming hoặc polling; không đưa token vào URL.
SSE có heartbeat, kiểm tra lại hạn token và `X-Accel-Buffering: no`. Ngắt kết nối
không hủy job. Sự kiện cuối trỏ đến result thay vì lặp lại toàn bộ dữ liệu nội bộ.

Backend ẩn draft trên events/steps mặc định; cần `include_draft=true` để lấy.
Result mặc định không trả config đầy đủ, expert reports, prompt hoặc credential.
Nguồn đã lấy vẫn có qua `/sources` khi model lỗi hoặc run bị gián đoạn.
Token/chi phí thiếu dữ liệu được giữ là unknown, không tự tạo số liệu.

Streamlit đã có HTTP adapter. Trong `.env` của tiến trình Streamlit:

```dotenv
HERITAGE_API_URL=http://127.0.0.1:8000
# HERITAGE_API_TOKEN=<access token đã cấp nếu muốn dùng một phiên có sẵn>
```

Nếu không đặt token, Streamlit tạo phiên riêng cho mỗi session trình duyệt; khi
server yêu cầu bootstrap, cấu hình secret đó ở server Streamlit. Chạy Streamlit
bình thường. Chế độ này upload và tạo job qua HTTP, hiển thị các bước/kết quả từ
API; UI không trực tiếp gọi Gemini. Lịch sử/feedback trên UI hiện vẫn là local
session; API cung cấp endpoints lưu bền để frontend mới tích hợp. Chế độ so sánh
nghiên cứu hiện chạy qua Streamlit local/CLI, chưa có job API riêng.

## Hàng đợi, worker và phục hồi

Hàng đợi nằm trong PostgreSQL/SQLite cùng giao dịch tạo run, tránh khoảng trống
giữa commit job và gửi broker. Worker polling và claim bằng conditional update;
nhiều worker không nhận cùng một job. PostgreSQL khóa admission và migration
bằng transaction advisory lock; SQLite local dùng write lock.

Worker ghi heartbeat ở luồng riêng khi chờ model và gia hạn heartbeat/lease cùng
transaction ghi tiến độ job. Timestamp được lấy sau khi có khóa ghi DB để tránh
commit heartbeat đã cũ khi DB bận. `/health/ready` vẫn trả 503 khi không có worker
với heartbeat còn hạn; embedded mode không bỏ qua điều kiện này.

Worker ghi heartbeat và lease. Job mất lease chuyển failed/WorkerLost, giữ các
sự kiện/bằng chứng đã lưu, không tự gọi lại model gây trùng phí. Job còn queued
vẫn được worker nhận sau restart. `/retry` là lựa chọn chạy lại rõ ràng.
Phiên bản API này chưa tự resume node từ checkpoint LangGraph; checkpointer
injectable của lõi vẫn có sẵn cho bước phát triển sau.

Hủy queued có hiệu lực ngay. Hủy running được kiểm tra giữa node và trước mỗi
model attempt; request SDK đang chạy tuân timeout rồi mới dừng. Session bị thu hồi
hoặc hết hạn cũng ngăn chạy tiếp. Giới hạn mặc định: ba active runs/phiên,
100 runs/24 giờ/phiên và 100 active runs toàn hàng đợi.

## PostgreSQL và Docker

Điền `POSTGRES_PASSWORD` và `API_BOOTSTRAP_TOKEN` ít nhất 32 ký tự trong `.env`.
Dùng mật khẩu ngẫu nhiên dạng hex để thuận tiện nhúng trong URL kết nối Compose.
Giữ `API_MODEL_MODE=demo` nếu đang kiểm tra hạ tầng mà chưa muốn gọi model thật.

```powershell
docker compose up --build -d
```

Compose chạy PostgreSQL 17, API và worker riêng, dùng chung volume ảnh. Schema
được Alembic migrate khi startup. API bind `127.0.0.1:8000`; publish qua reverse
proxy HTTPS. Ví dụ SSE proxy: [nginx.conf.example](../deploy/nginx.conf.example).

Chạy không Docker: đặt `DATABASE_URL=postgresql+psycopg://...`,
`API_EMBEDDED_WORKER=false` và khởi động worker ở terminal khác:

```powershell
uv run --locked python -m api.worker
```

Migration thủ công: `uv run --locked alembic upgrade head`.
Backup cả database và volume ảnh. Kho ảnh hiện là filesystem dùng chung; khi
scale nhiều máy cần thay adapter bằng object storage/shared storage.
Production bắt buộc PostgreSQL và bootstrap secret; CORS chỉ cho các origin
trong `API_CORS_ORIGINS`. Key Gemini/LangSmith giữ trong environment server.

## Kiểm thử

```powershell
uv run --locked pytest
uv run --locked python -m scripts.api_smoke
uv run --locked python -m scripts.api_contract_report
```

Smoke mặc định từ chối server live. Chỉ dùng `--allow-live` khi chủ động cho phép
gọi workflow trả phí. Smoke thử session → sample upload → job → events/result →
feedback → SSE. Không in access token hoặc header credential.

API tests mặc định dùng SQLite và chặn mạng ngoài. Để kiểm tra PostgreSQL trên
database test riêng, đặt `API_TEST_DATABASE_URL` rồi chạy `pytest tests/test_api.py`.
Mỗi test tạo một schema có tên ngẫu nhiên và chỉ xóa schema do nó tạo.

Tài liệu API tham khảo: [FastAPI upload](https://fastapi.tiangolo.com/tutorial/request-files/),
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[SQLAlchemy engines](https://docs.sqlalchemy.org/en/20/core/engines.html).
