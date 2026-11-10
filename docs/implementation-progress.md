# Đợt 1: LangGraph và sửa các lỗi ưu tiên cao

## Hoàn thiện observability — 10/11/2026

- JSON logs UTC dùng chung API/worker; metadata allowlist, safe error frames,
  không log body/prompt/credential/raw URL hoặc thông báo lỗi thô từ SDK.
- Request ID lưu vào run; context liên kết API → worker → graph → model và
  LangSmith. Có lifecycle, SSE cursor/duration/count, warning outage rate limit.
- Migration `0002_observability` giữ dữ liệu cũ; ghi model attempt trước/sau
  request, giữ dấu vết khi mất worker; per-run metrics đọc cả attempt chưa hoàn tất.
- Thêm `/api/v1/operations/metrics` dùng token vận hành riêng; tổng hợp DB bằng
  SQL, histogram HTTP và SSE process-local. Không tăng dependency ứng dụng.
- Docker logs có rotation; optional Prometheus LTS overlay, retention, 6 alert rules.
- Kiểm tra: 113 tests offline; HTTP thật 73/73 cases trên 31/31 operations;
  Prometheus native 10/10 checks và 6 alert tests. Docker Compose config hợp lệ,
  chưa chạy container vì Docker Engine chưa hoạt động. Không gọi model trả phí.

[Kế hoạch](observability-plan.md), [hướng dẫn vận hành](observability.md),
[kết quả API](api-test-results.md).

## Bổ sung backend API — 04/11/2026

- FastAPI với 30 HTTP operations và Swagger `/docs`, ReDoc, OpenAPI có schema,
  multipart upload, Bearer Authorize và hướng dẫn thử theo từng bước.
- Upload/samples, sessions, jobs/history, SSE và event replay dạng JSON, hủy/retry,
  kết quả/nguồn/steps/metrics/export, đánh dấu và feedback có ownership.
- SQLAlchemy + Alembic: SQLite local, PostgreSQL server; ảnh filesystem riêng,
  queue bền vững trong DB, atomic claim, heartbeat/lease và chính sách WorkerLost.
- Dockerfile và Compose cho PostgreSQL/API/worker riêng; cấu hình proxy SSE.
- Streamlit tùy chọn gọi HTTP backend qua `HERITAGE_API_URL`; lõi local vẫn được
  dùng bởi UI/CLI, đồng thời hỗ trợ run ID được cấp trước và hủy hợp tác.
- Demo mode đi qua graph thật bằng dữ liệu mô phỏng; không gọi model hoặc gửi
  trace ra LangSmith. Live mode giữ nguyên provider/key/model đã cấu hình.
- Kiểm tra: **100 tests passed** trên bộ mặc định; **17 API tests passed** trên
  PostgreSQL thật. Docker build và HTTP smoke qua Compose PostgreSQL + worker
  riêng thành công. Swagger 30 operations và Try it out được kiểm tra bằng Edge.

API chưa có đăng nhập tài khoản/OIDC, catalog/news/events CRUD, comparison job
hoặc tự resume từ LangGraph checkpoint sau crash. Hủy request SDK đang chạy chờ
timeout; job mất worker được kết thúc có lỗi, giữ bằng chứng và cho retry chủ động.

Hướng dẫn triển khai và frontend: [api-server.md](api-server.md).

Kiểm thử HTTP theo từng endpoint ngày 04/11/2026: **30/30 operations**, **69/69
tình huống đạt**, API và worker chạy ở hai tiến trình riêng với SQLite riêng,
demo mode và không gọi model trả phí. Bảng kết quả gồm mã HTTP, response tóm tắt
và thời gian từng request: [api-test-results.md](api-test-results.md).
Hướng dẫn thực hành: [api-swagger-walkthrough.md](api-swagger-walkthrough.md).
Runner tái lập: `python -m scripts.api_contract_report`.

## Bổ sung giao diện và trải nghiệm — 29/10/2026

- Giao diện khám phá với theme, nhập ảnh mẫu/upload/camera, xoay ảnh, câu hỏi gợi
  ý và câu hỏi tiếp theo; cache ảnh riêng theo phiên.
- RunEvent có lifecycle và artifact thật; nguồn được phát trước khi Knowledge
  gọi model, được giữ khi model lỗi. Thẻ tiến độ, chi tiết từng giai đoạn, bản
  nháp opt-in, thư viện nguồn, liên kết bản đồ, tiêu chí đánh giá và biểu đồ thời gian.
- Lịch sử tám lượt, đánh dấu, phản hồi cá nhân, bộ lọc nguồn và xuất JSON/Markdown
  có tùy chọn kèm nội dung trung gian. Các thao tác trình bày không gọi thêm model.
- Kiểm tra: **83 tests passed**; Edge/Playwright desktop và mobile không có lỗi
  JavaScript hoặc tràn ngang. Browser dùng dữ liệu giả lập; chưa gọi model thật.

Thiết kế và hướng dẫn: [experience-design.md](experience-design.md).

## Nền tảng đã triển khai

Ngày thực hiện: 29/10/2026. Nhánh: `feat/langgraph-core`, phát triển từ `101c033`.

Luồng chạy thực nằm ở [workflow/service.py](../workflow/service.py), được dùng bởi UI, CLI và chế độ so sánh. [langgraph.mmd](langgraph.mmd) được xuất từ graph đã compile, không gọi model.

| Phần | Đã triển khai |
| --- | --- |
| LangGraph | Scope → Coordinator → Visual/Knowledge song song → Generation tùy chọn sau expert → Aggregator → Judge → Finish |
| Trạng thái | State có ảnh chuẩn hóa dạng bytes, reducer cho kết quả/lỗi song song, metadata node và run ID |
| Kết quả | `reviewed`, `unverified`, `insufficient_evidence`, `out_of_scope`, `failed`; bản nháp tách riêng |
| Schema | ExecutionPlan, nguồn thực, tiêu chí Judge và run result qua Pydantic; JSON lỗi không tạo điểm/PASS |
| Nguồn | ID nguồn từ code, snippet/revision/thời điểm lấy; lỗi tìm kiếm có trạng thái; Maps tách thành navigation |
| Kiểm tra | Judge nhận ảnh gốc và nguồn đã lấy; chỉ được trích source ID có trong run; URL tự sinh bị từ chối |
| Provider | Gemini mặc định, role/provider/key/model tường minh; fallback opt-in có metadata từng attempt |
| Ngân sách | Giới hạn tổng lượt gọi model, timeout SDK, admission deadline và giới hạn retry; usage thiếu là null |
| UI | Các mốc xử lý thực, không stream draft công khai, không giữ kết quả khi đầu vào/cấu hình đổi |
| So sánh | Chỉ trình bày đầu ra, thời gian, calls và lỗi; chưa chấm correctness hoặc kết luận thắng |
| Môi trường | Python 3.12, pyproject/uv.lock, requirements xuất từ lock, suite offline và workflow CI Windows/Linux |
| LangSmith | Root trace theo run ID, graph/node song song, model attempts/retry/fallback/token thực và search spans; lọc nội dung trước khi gửi, không chặn workflow khi telemetry lỗi |

Các lỗi FIX-01/02/03/05/06/07 đã có regression tương ứng. FIX-04 có routing, readiness và metadata nhưng chưa có thao tác preflight model/capability qua API thật. FIX-08 có lockfile, CI definition và kiểm tra local; chưa chạy CI trên GitHub. CORE-02/03/08 đã có phần nền, cần tiếp tục các tiêu chí còn lại của kế hoạch.

## Kiểm tra

Kết quả local ngày 29/10/2026 sau khi thêm LangSmith: **68 tests passed**, Ruff check/format, `uv lock --check`, `uv pip check`, CLI help và import legacy smoke đều đạt. Chưa chạy workflow CI trên GitHub hoặc live model smoke.

LangSmith đã xác thực HTTP 200 và gửi/đọc lại trace graph tổng hợp thành công trong
project `heritage-vqa-dev`, xác nhận nội dung input/output mẫu đã được che. Lần kiểm
tra này không gọi model. Cấu hình key chỉ nằm trong `.env` bị Git bỏ qua.
Xem [langsmith.md](langsmith.md) để bật/tắt, đổi project/region và chạy lại smoke.

```powershell
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m scripts.export_graph
uv run --locked python benchmark_run.py --help
```

Suite có fixture model/search, chặn kết nối ra ngoài. Windows asyncio được phép tạo loopback socketpair. Các kiểm tra gồm parallel barrier/fan-in, lỗi node, checkpoint serialization, schema và nguồn giả, metadata fallback, stream gián đoạn, provider capabilities, SDK request construction và UI AppTest.

## Phạm vi cần làm tiếp

- Entity catalog/resolve nhiều ứng viên, corpus được tuyển chọn, retrieval theo câu hỏi và tool registry.
- Kiểm chứng theo từng claim và kiểm tra sau diễn đạt đầy đủ; cơ chế hiện tại vẫn là đánh giá tự động của một model.
- Dataset có gold evidence và evaluator độc lập. Baseline ReAct hiện được ghi rõ là mô phỏng, chưa có tool loop thật.
- Debate có chọn lọc và vòng kiểm chứng lại; chưa có vòng debate trong graph đợt này.
- Checkpoint bền vững, resume sau restart, cancel, tổng tool budget và API/worker. `InMemorySaver` chỉ là tùy chọn được kiểm tra trong test, không phải persistence production.
- GPU có cấu hình provider/endpoint nhưng chưa được probe hoặc đo chất lượng. Capabilities hiện là khai báo được kiểm tra tính tương thích, chưa phải kết quả đo model.

Không có phép đo chất lượng Gemini hoặc chi phí API thật trong đợt này. Deadline ứng dụng chặn lượt model mới; request đang chạy tuân timeout SDK, không có cam kết hủy tức thời request đang xử lý.
