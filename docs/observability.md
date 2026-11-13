# Log và giám sát server

API và worker dùng JSON logging, lưu lịch sử stage và model attempts trong DB,
đồng thời có thể gửi trace đã lọc dữ liệu tới LangSmith. Tài liệu này mô tả cấu
hình hiện hành; kế hoạch cũ và báo cáo theo từng lượt chạy giữ ở local.

## Chạy local

Streamlit local và CLI nay cũng khởi tạo logger: `logs/streamlit-<pid>.jsonl`
và `logs/cli-<pid>.jsonl` theo mặc định, hoặc dùng `API_LOG_DIR` nếu đã đặt.
Logger được dùng lại giữa các lần rerun, không nhân số handler. UI local vẫn
không tạo job/DB API; dùng `HERITAGE_API_URL` nếu cần queue và lưu model attempts
vào DB. Xem [chế độ nội dung LangSmith](langsmith.md) để quan sát prompt/response;
JSONL trên máy chỉ ghi metadata.

Chạy từ thư mục `doan_demo`. Không cần thêm dependency hoặc dịch vụ ngoài để ghi log.

```powershell
$env:API_LOG_DIR = 'logs'
uv run --locked python -m scripts.serve_api --demo --port 8001
```

Mở <http://127.0.0.1:8001/docs>. JSON được ghi ra stderr và file
`logs/api-<pid>.jsonl`. Worker tách riêng dùng `logs/worker-<pid>.jsonl`:

```powershell
# Terminal API: tắt embedded worker trước khi khởi động.
$env:API_EMBEDDED_WORKER = 'false'
uv run --locked python -m scripts.serve_api --demo --port 8001

# Terminal worker: cùng database/data directory; demo để không gọi model thật.
$env:API_MODEL_MODE = 'demo'
$env:API_LOG_DIR = 'logs'
uv run --locked python -m api.worker
```

Mỗi terminal cần cùng các biến môi trường và `.env`. Bỏ `--demo`/đổi mode khi
chạy live. Khi thay code hoặc biến môi trường phải khởi động lại tiến trình.
Không chạy thêm worker embedded nếu chủ động chọn mô hình worker riêng.

## Theo dõi một request hoặc run

1. Tạo run trong Swagger. Lưu `X-Request-ID` của response và `run_id` trong JSON.
2. JSON run trả `request_id` của request tạo run và `trace_id` bằng `run_id`.
3. Lọc log theo một trong các ID. Worker đọc request ID từ DB, kể cả khi nhận job
   ở tiến trình khác hoặc sau restart. Run cũ trước migration có request ID null.
4. Trong LangSmith live mode, tìm trace theo run ID. Tracing chỉ hoạt động nếu
   `LANGSMITH_TRACING=true` và credential hợp lệ. Demo không gửi trace ra ngoài.

```powershell
$targetRun = '<run_id>'
Get-Content logs/*.jsonl |
  ForEach-Object { $_ | ConvertFrom-Json } |
  Where-Object { $_.run_id -eq $targetRun } |
  Sort-Object timestamp |
  Format-Table timestamp, level, event, node, agent_role, duration_ms, error_type
```

Ví dụ schema, ID và thời gian dưới đây chỉ minh họa:

```json
{
  "timestamp": "2026-11-10T03:00:00+00:00",
  "level": "INFO",
  "event": "model.success",
  "logger": "heritage",
  "pid": 1234,
  "request_id": "d2501034-10ad-4eb9-bbd0-a2b5d1c29115",
  "run_id": "801393ae-4f9e-445a-9b2f-39ac38f19412",
  "trace_id": "801393ae-4f9e-445a-9b2f-39ac38f19412",
  "worker_id": "d94bc6d4-c9f7-479e-820c-d73766b36752",
  "agent_role": "visual",
  "actual_provider": "gemini",
  "attempt": 2,
  "retry": 0,
  "fallback_used": false,
  "duration_ms": 1200.5
}
```

| Nhóm event | Ý nghĩa |
| --- | --- |
| `http.completed`, `http.error`, `http.rejected`, `http.validation_failed` | Route template, HTTP status, duration, request ID; không ghi raw URL/query |
| `api.starting`, `api.ready`, `api.stopping` | Lifecycle tiến trình API |
| `run.queued`, `run.replayed`, `run.running`, `run.retry`, `run.cancel` | Admission, idempotency, queue wait, thao tác retry/hủy |
| `run.succeeded`, `run.failed`, `run.cancelled` | Kết thúc run; kết quả kiểm chứng vẫn ở `result_status` qua API |
| `stage.running`, `stage.completed`, `stage.failed`, `stage.skipped` | Node, sequence, duration và loại lỗi nếu có |
| `model.started`, `model.success`, `model.error`, `model.cancelled` | Model attempt, provider/model, retry/fallback, usage khi có |
| `model.persistence_failed`, `model.reconciliation_failed` | Lỗi lưu telemetry, cần kiểm tra DB |
| `sse.opened`, `sse.closed`, `sse.error` | Cursor, sequence cuối, số event, duration và lý do đóng |
| `worker.started`, `worker.stopping`, `worker.heartbeat_failed`, `worker.poll_failed`, `worker.lease_lost` | Worker lifecycle và sự cố lease |
| `trace.*_failed` | Lỗi gửi/khởi tạo/flush LangSmith; không làm mất kết quả workflow |

Duration HTTP được tính đến lúc kết thúc response, kể cả SSE. SSE có log mở và
đóng riêng để biết đã bắt đầu stream trước khi request kết thúc. Không ghi mỗi
heartbeat/poll; cảnh báo heartbeat/poll lặp lại được giới hạn một lần/30 giây
cho từng loại lỗi trên mỗi worker. CORS preflight do middleware CORS ngoài cùng
xử lý không đi qua access logger của ứng dụng.

## Lưu model attempts và xử lý sự cố

Migration `0002_observability` thêm `api_runs.request_id` và `api_model_attempts`,
giữ nguyên bản ghi hiện có. Startup API/worker chạy migration bằng cơ chế khóa
đã có; nên sao lưu DB trước một đợt cập nhật production theo quy trình triển khai.

- Trước request model thật: commit attempt `running`. Nếu không lưu được, dừng
  trước khi gọi SDK để không có lượt trả phí không được ghi nhận.
- Khi model trả về/lỗi: lưu status, duration, retry/fallback, error type và numeric
  token usage. Lỗi telemetry sau model không tự gọi lại model; worker thử đối
  soát lại từ danh sách calls lúc hoàn tất run.
- Nếu worker bị kill: attempt bắt đầu vẫn còn. Khi phát hiện lease hết hạn, worker
  chuyển attempt còn `running` thành `interrupted` và run thành `WorkerLost`.
- Chưa biết usage được giữ là null/unknown. Worker chết trước khi nhận usage từ
  provider thì không thể suy ra số token hoặc chi phí chính xác.
- `GET /api/v1/runs/{id}/metrics` đọc attempts đã lưu ngay cả khi run đang chạy,
  thất bại hoặc bị gián đoạn; run cũ dùng dữ liệu calls trong result làm fallback.

Migration `0003_response_diagnostics` thêm JSON diagnostics vào model attempts.
API `/metrics` theo run trả finish reason, block reason, output limit, có text
hay không và HTTP provider status khi có, ngay cả khi response bị từ chối.
Model usage được đọc trước khi validate response, nên lỗi MAX_TOKENS/empty không
làm mất số token đã được provider báo về. Bộ lọc này không lưu text vào bảng
attempts; text chỉ có trong result nghiệp vụ hoặc LangSmith content mode.

DB lưu nội dung nghiệp vụ để API có xác thực trả kết quả trung gian; đây là dữ
liệu khác với log vận hành. File log chỉ chứa metadata. Formatter không ghi
arbitrary message của thư viện ngoài; chúng xuất hiện dưới event `external.log`
kèm logger/level và stack frame an toàn khi có exception.

## Metrics vận hành và xác thực

`GET /api/v1/operations/metrics` xuất Prometheus text và có trên Swagger trong
nhóm **Operations**. Endpoint dùng **token vận hành riêng**, không dùng access
token guest hoặc API key Gemini/LangSmith.

```dotenv
API_OPERATIONS_TOKEN=<secret-random-at-least-32-characters>
API_LOG_LEVEL=INFO
API_LOG_MAX_BYTES=10000000
API_LOG_BACKUPS=5
# API_LOG_DIR=logs
```

Khởi động lại API sau khi cấu hình. Token chưa cấu hình → 503; thiếu/sai/guest
token → 401. Trong Swagger Authorize, nhập operations token vào **OperationsBearer**;
**HTTPBearer** giữ access token của phiên để thử API nghiệp vụ. Không nhúng operations token
vào frontend. Endpoint không có label chứa run ID, session ID, câu hỏi hoặc URL nguồn.

| Metric | Phạm vi và cách đọc |
| --- | --- |
| `heritage_runs{status}` | Gauge số run trong DB theo trạng thái, dùng chung API/worker |
| `heritage_oldest_queued_seconds` | Thời gian chờ của job queued lâu nhất |
| `heritage_workers_alive` | Worker heartbeat còn hợp lệ |
| `heritage_worker_lost_runs` | Gauge tổng run có lỗi WorkerLost trong DB |
| `heritage_model_attempts{status}` | Gauge số attempt đã ghi: running/success/error/interrupted/cancelled |
| `heritage_model_tokens_observed{kind}` | Tổng token đã biết trong DB; không coi missing usage là đã đo được 0 |
| `heritage_model_attempts_unknown_usage` | Số attempt thiếu tổng token; đọc cùng metric token |
| `heritage_http_requests_total` | Counter theo method, route template, status; process-local |
| `heritage_http_request_duration_seconds` | Histogram HTTP duration; SSE dài làm tăng duration, nên lọc route khi xem latency API |
| `heritage_sse_active`, `heritage_sse_connections_total`, `heritage_sse_events_total` | Kết nối và event SSE; process-local |

Các truy vấn tổng hợp DB chạy bằng SQL, không tải toàn bộ lịch sử vào RAM. Metrics
DB là gauge, không dùng `rate()` như counter. HTTP/SSE reset khi process restart;
chạy một process Uvicorn mỗi container như Dockerfile hiện tại. Nếu scale API,
scrape riêng từng replica rồi cộng metrics process-local; metrics DB cùng DB
phải deduplicate theo cụm, không cộng lặp giữa các replica.

Ví dụ PromQL:

```promql
sum(rate(heritage_http_requests_total{route!~".*events|.*metrics"}[5m]))
histogram_quantile(0.95, sum by (le) (rate(heritage_http_request_duration_seconds_bucket{route="/api/v1/runs"}[5m])))
heritage_runs{status="queued"}
heritage_model_attempts_unknown_usage
```

## Docker, rotation và Prometheus

Compose chính giới hạn Docker logs **10 MB × 5 files/container**. Có thể xem log
API và worker chung, giữ JSON trong field `log` của Docker:

```powershell
docker compose logs --no-log-prefix --since 30m api worker
```

File rotation local cũng giới hạn kích thước và số backup **trên từng PID**;
không dùng chung một file giữa nhiều process. File của PID cũ không tự xóa theo
ngày. Production nên dùng stdout + rotation Docker; nếu bật file local lâu dài,
cần chính sách dọn file PID cũ theo môi trường lưu trữ. Không tự xóa run/events/
attempts trong DB vì đây là dữ liệu đánh giá đồ án.

Overlay [compose.monitoring.yaml](../compose.monitoring.yaml) thêm Prometheus,
giữ dữ liệu tối đa 15 ngày hoặc giới hạn 2 GB. Đã pin image LTS. Chuẩn bị file
`.secrets/operations_token` chỉ chứa đúng token đã cấu hình trong `.env` (không
thêm dấu ngoặc hoặc `Bearer`). Thư mục này bị Git và Docker build bỏ qua.

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml up -d --build
```

Mở <http://127.0.0.1:9090>, kiểm tra Targets → `heritage-api` UP, sau đó xem
Alerts và truy vấn các metric ở trên. Port chỉ bind loopback. Các rule có sẵn:
API không scrape được, worker mất heartbeat, queue chậm, HTTP 5xx tăng, mất lease
và nhiều model attempts lỗi. Chưa cấu hình receiver email/Slack; các cảnh báo
được hiển thị trong Prometheus, muốn gửi thông báo cần kết nối Alertmanager và
receiver của môi trường triển khai.

Nguồn cấu hình chính thức:
[Docker log rotation](https://docs.docker.com/engine/logging/drivers/json-file/),
[Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/),
[alert rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/),
[Prometheus releases](https://prometheus.io/download/).

## Kiểm thử

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m scripts.api_contract_report
```

Runner tạo API/worker/SQLite/log directory riêng, kiểm tra mọi OpenAPI operation,
operations auth, metrics và liên kết log qua hai tiến trình, rồi dừng tiến trình
do nó tạo. Không đổi `.env`, không gọi model thật hoặc chạm server live. Bảng
kết quả ở `reports/api-contract/results.md`. Log thô của runner ở thư mục
`.api-demo/contract-<uuid>/logs`, bị Git bỏ qua.

Để kiểm tra Prometheus thật mà không cần Docker, tải binary chính thức và xác
minh checksum từ trang release, rồi chạy (đường dẫn binary tùy máy):

```powershell
promtool check rules monitoring/alerts.yml
promtool test rules monitoring/alerts.test.yml
uv run --locked python -m scripts.monitoring_smoke --prometheus path/to/prometheus.exe --promtool path/to/promtool.exe
```

Smoke tạo API demo và Prometheus trên port 18513/19091 (đổi bằng `--api-port` và
`--prometheus-port`), kiểm tra scrape có auth, run/model attempts, HTTP counter,
unknown usage, 6 rule được evaluate, exposition hợp lệ và log không chứa dữ liệu
riêng tư. Tự dừng process do nó tạo, xóa file credential tạm; báo cáo ở
`reports/monitoring/results.json`. Không gửi notification hoặc gọi model trả phí.

Không có cam kết exactly-once billing: crash sau khi provider đã nhận request có
thể chỉ để lại attempt `running`/`interrupted`; hệ thống không tự replay model.
Việc lưu telemetry thêm một transaction nhỏ trước/sau mỗi attempt; đây là đánh
đổi có chủ đích để có dấu vết bền vững. Chưa có benchmark tải production hoặc
thử nghiệm lỗi hạ tầng trên nhiều server.
