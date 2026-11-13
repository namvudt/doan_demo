# Backend API và Swagger UI

Backend dùng FastAPI, gọi cùng `RunService`/LangGraph của Streamlit và CLI.
Swagger có 31 HTTP operations, chia theo Health, Sessions, Configuration, Assets,
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
