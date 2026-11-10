# Kế hoạch hoàn thiện logging và giám sát

Phạm vi: API FastAPI, worker, LangGraph, model attempts, SSE và vận hành Docker.
Không ghi credential, body request/response, prompt, ảnh, câu hỏi hoặc đoạn nguồn
vào log vận hành. Kết quả nghiệp vụ vẫn ở API có xác thực và database.

| Ưu tiên | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| P0 | JSON logging dùng chung, UTC, mức log, stack frame an toàn | API và worker dùng cùng schema; không có dữ liệu nhạy cảm |
| P0 | Liên kết request → run → worker → LangSmith | Request ID lưu bền qua queue; trace ID bằng run ID; context không lẫn giữa luồng |
| P0 | Lifecycle API, worker, stage, model, SSE | Có duration, status/error type, sequence/cursor; không log heartbeat từng tick |
| P0 | Lưu từng model attempt ngay khi bắt đầu/kết thúc | Worker chết vẫn giữ attempt đang chạy; không tự gọi lại model do lỗi telemetry |
| P1 | Endpoint metrics vận hành có token riêng | Tổng hợp DB dùng chung giữa worker/API; HTTP và SSE process-local được ghi rõ |
| P1 | Rotation/retention và cảnh báo | Docker giới hạn log; local file riêng mỗi process; cấu hình Prometheus + alert rules |
| P1 | Hướng dẫn chạy và điều tra lỗi | Có cách lọc request/run, cấu hình, giới hạn và ví dụ Swagger |
| P0 | Kiểm thử và chạy HTTP thật chế độ demo | Kiểm tra isolation, redaction, migration, lỗi, cancel, SSE replay và metrics auth |

Thực hiện theo thứ tự bảng. Không thêm broker hoặc bắt buộc dịch vụ giám sát vào
đường xử lý. JSON stderr là mặc định; file rotation và Prometheus là tùy chọn.
Không tự xóa lịch sử run/model attempts trong DB vì đây là dữ liệu phục vụ đánh
giá đồ án; retention của log kỹ thuật được cấu hình riêng.

Trạng thái: đã triển khai các hạng mục trong bảng. Hướng dẫn cấu hình và giới hạn:
[observability.md](observability.md). Kết quả xác minh:

- 113 tests offline: API/core/UI, safe logging, migration giữ dữ liệu, retry,
  lỗi telemetry, lease loss, cancellation, SSE disconnect/replay và context isolation.
- HTTP thật: 31/31 operations, 73/73 tình huống đạt, API và worker tách tiến trình;
  xác minh log correlation qua DB queue. [Bảng kết quả](api-test-results.md).
- Prometheus LTS 3.13.5 native Windows: scrape có auth, metrics/run/attempts,
  exposition, alert evaluation và privacy: 10/10 checks đạt; 6 alert rule tests đạt.
- Docker Compose overlay đã kiểm tra cấu hình. Docker Engine chưa chạy trên máy,
  chưa chạy stack container trong đợt này. Alertmanager/receiver thông báo chưa
  cấu hình vì phụ thuộc kênh vận hành của môi trường triển khai.
- Demo/mock không gọi Gemini/GPU trả phí; chưa benchmark tải production.
