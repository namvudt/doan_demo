# Import và thử API bằng Postman

Bộ JSON gồm **33 HTTP operations**, **36 requests** (thêm SSE replay, result kèm
intermediate và export Markdown). Có body mẫu, query parameters, auth, script tự
lưu token/ID và kiểm tra HTTP status. Mẫu không chứa credential hoặc ID của phiên
đã chạy trên máy người phát triển.

## 1. Import file

Trong Postman Desktop, chọn **Import → Files**:

1. [heritage-vqa.postman_collection.json](../postman/heritage-vqa.postman_collection.json).
2. Chọn một environment:
   - [Demo](../postman/heritage-vqa-demo.postman_environment.json): `http://127.0.0.1:8001`.
   - [Local API](../postman/heritage-vqa-local.postman_environment.json): `http://127.0.0.1:8000`.

Chọn environment vừa import ở góc trên bên phải. Collection tên **Heritage VQA -
Complete API** xuất hiện trong Collections. Không cần import cả hai environment
cùng lúc; có thể import cả hai để chuyển server bằng environment selector.

Schema OpenAPI có sẵn tại `/openapi.json`. Khi cần file để sinh client, chạy
`uv run --locked python -m scripts.export_postman --include-openapi` để tạo
`postman/heritage-vqa.openapi.json` local. Schema có thể sinh lại nên không commit;
collection ở bước 1 đã có đủ workflow và scripts để thử toàn bộ API.

## 2. Chạy backend demo

Từ thư mục `doan_demo`:

```powershell
uv run --locked python -m scripts.serve_api --demo --port 8001
```

Demo chạy LangGraph với model/nguồn mô phỏng, không gọi Gemini hoặc GPU. Giữ
terminal mở và chọn environment **Heritage VQA - Demo**. Với server đã triển
khai, đổi `base_url` sang địa chỉ server, không thêm `/api/v1` vào cuối.

## 3. Cách nhanh: Run Collection

Chọn collection → **Run** → chạy một iteration theo thứ tự mặc định. Có thể giữ
delay 0 vì request chờ run đã tự có khoảng nghỉ khi cần polling.

| Folder | Nội dung |
| --- | --- |
| 01 System | Liveness/readiness, capabilities, danh sách ảnh mẫu |
| 02 Session | Cấp phiên, tự lưu `access_token` và `session_id` |
| 03 Assets | Tạo asset từ mẫu, lưu `asset_id`, đọc metadata/PNG; upload tùy chọn |
| 04 Workflow | Danh sách giai đoạn, sơ đồ và preflight credential/model |
| 05 Runs | Tạo run, lưu `run_id`/request ID/trace ID, list và polling trạng thái |
| 06 Events | Lịch sử JSON, SSE, SSE replay với Last-Event-ID |
| 07 Results | Kết quả, intermediate, sources, steps, model usage, JSON/Markdown export |
| 08 Feedback | Bookmark, POST/PUT/GET feedback |
| 09 Operations | Prometheus metrics bằng token vận hành riêng |
| 10 Lifecycle actions | Hủy, đánh giá lại riêng Judge, retry, xóa asset và thu hồi phiên; mặc định bỏ qua |

Upload được bỏ qua khi `enable_upload=false`; API vẫn được thử bằng ảnh mẫu.
Operations được bỏ qua nếu `operations_token` trống. Folder 10 được bỏ qua khi
`run_lifecycle_actions=false`. Đây là các request đầy đủ trong collection; chỉ
cần cấu hình các biến tương ứng để chạy chúng.

`GET run` trong folder 05 tự lặp bằng `pm.execution.setNextRequest()` khi chạy
Runner/Newman. Mặc định nghỉ 1 giây, tối đa 120 lượt polling. Hết ngân sách hoặc
run thất bại/hủy thì có assertion báo lỗi và dừng chuỗi request. Tăng
`poll_max_attempts` nếu server/model thực tế cần lâu hơn.

## 4. Bấm Send từng API

Gọi theo thứ tự: **Create session → Create asset from sample → Create run**.
Các script tự lưu ID vào environment nên không cần sao chép thủ công. Sau đó
gọi status, events, steps hoặc result tùy mục đích.

Khi bấm **Send** riêng lẻ, `setNextRequest()` không tự gửi lại request; bạn có
thể bấm Send tiếp cho status hoặc dùng Runner. Result chưa sẵn sàng trả 409.
Readiness trả 503 khi chưa có worker/DB hoạt động; test của request này chấp nhận
200/503 để bạn đọc được trạng thái, không coi 503 là server đã sẵn sàng.

`Idempotency-Key` được tạo bằng GUID và giữ nguyên khi gửi lại Create run. Muốn
tạo run mới với cùng ảnh/câu hỏi, xóa giá trị `idempotency_key` trước khi Send.
Đổi body nhưng dùng key cũ có thể trả 409. Khi cấp phiên mới, script xóa token/ID
cũ và tạo ngữ cảnh mới cho workflow. Đổi sang asset khác không tự tạo run mới.

## 5. Những biến cần biết

| Biến | Giá trị/cách dùng |
| --- | --- |
| `base_url` | URL gốc, không có `/api/v1`; có thể đổi sang server |
| `bootstrap_token` | `API_BOOTSTRAP_TOKEN` của server, chỉ cần khi cấp phiên bị yêu cầu bootstrap |
| `operations_token` | `API_OPERATIONS_TOKEN`, riêng cho metrics, không thay guest token |
| `access_token`, `session_id`, `asset_id`, `run_id` | Tự lưu từ response |
| `sample_id` | Mặc định `chua_mot_cot`; xem danh sách ở folder 01 |
| `question`, `audience`, `profile` | Câu hỏi; audience `tourist`/`student`, profile `default` |
| `include_draft` | `true` để xem bản nháp tổng hợp trên events/steps |
| `include_intermediate` | `true` để kèm intermediate trong result/export; có request result riêng luôn bật |
| `history_after` | Cursor lịch sử JSON, tự cập nhật; đặt `0` để đọc lại từ đầu |
| `sse_after` | Cursor SSE, mặc định `0` |
| `last_event_id` | Tự lưu ID cuối sau stream; dùng trong request replay, đặt ID nhỏ hơn để xem phát lại |
| `poll_interval_ms`, `poll_max_attempts` | Khoảng nghỉ và số lượt polling trong Runner |
| `feedback_rating`, `feedback_note`, `bookmark_saved` | Feedback và bookmark mẫu |
| `enable_upload` | Bật `true` sau khi chọn file trong Body → form-data của request Upload |
| `run_lifecycle_actions` | Bật `true` để gửi các request folder 10 |
| `delete_asset_id` | Asset muốn xóa; để trống thì dùng asset hiện tại, có thể nhận 409 nếu đã gắn run |
| `retry_run_id` | Run con trả về từ Retry, không ghi đè run chính |
| `review_run_id` | Run con đánh giá lại riêng Judge; dùng `review_idempotency_key` riêng |

Nhập token vào biến môi trường của Postman, không thêm tiền tố `Bearer`.
Collection tự gắn Authorization; bootstrap chỉ gắn vào request cấp phiên.
Câu hỏi/feedback/session label được JSON-encode trong pre-request script để dấu
ngoặc kép hoặc xuống dòng không làm hỏng body. API key Gemini/LangSmith thuộc
backend, không cần điền vào Postman.

## 6. Quan sát streaming

Sau Create run, có thể mở **Stream stages SSE** trong tab khác ngay khi run đang
chạy. Postman hiển thị các sự kiện; kết nối đóng khi run terminal và phát hết
events. Các test/post-response script xử lý response sau khi stream đóng.

Runner đặt SSE sau request polling nên thường đọc lại lịch sử của run đã xong;
đây là cách tránh một stream dài chặn chuỗi test. Xem realtime bằng Send SSE khi
run còn running. Native API hiện stream theo giai đoạn, chưa stream từng token
của câu trả lời model trong workflow chính.

Request **Replay SSE using Last-Event-ID** gửi cursor đã lưu. Nếu cursor bằng ID
cuối thì response không có event mới là hợp lệ. Ngắt stream không hủy run;
muốn hủy dùng Cancel trong folder 10.

## 7. Lifecycle và upload

Upload: mở request **Upload image - optional**, chọn Body → form-data → `file`
→ Select Files; đặt `enable_upload=true`, rồi Send. Response 201 thay `asset_id`
bằng ảnh mới; tạo một run mới khi muốn xử lý ảnh này. Không tự gắn Content-Type
multipart để Postman tự sinh boundary.

Folder 10 cần `run_lifecycle_actions=true`. Cancel run đã hoàn tất trả lại trạng
thái hiện tại; Retry chỉ chấp nhận run terminal. Retry lưu `retry_run_id`, có
`retry_idempotency_key` riêng. Xóa ảnh đã dùng trong run trả 409, ảnh chưa dùng
trả 204. **Revoke session chạy cuối**: token mất hiệu lực, hãy tạo phiên mới để
tiếp tục thử. Muốn xem run retry, thay `run_id` bằng `retry_run_id` và đợi kết quả
trước khi thu hồi phiên. Chế độ live gọi model thực tế theo cấu hình backend.

## 8. Tạo lại JSON và kiểm tra

```powershell
uv run --locked python -m scripts.export_postman
uv run --locked pytest tests/test_postman_export.py
```

Generator kiểm tra danh sách operation khớp OpenAPI trước khi xuất, giúp phát
hiện API mới chưa được bổ sung. Có test đối chiếu JSON commit với contract hiện
tại. Các file mẫu chỉ có credential rỗng; không xuất token từ `.env` vào artifact.

Collection hiện tại được test đối chiếu toàn bộ **33 operations / 36 requests**
với OpenAPI. Runner HTTP độc lập `uv run --locked python -m scripts.api_contract_report`
đã kiểm tra **82/82 case**, phủ **33/33 operations**, bao gồm preflight và review
chỉ gọi Judge. Kết quả local ở `reports/api-contract/results.md` và `results.json`.
Không gọi model trả phí, không dùng server live.

Preflight nằm trong folder 04. Review nằm trong folder 10, cần
`run_lifecycle_actions=true`, lưu `review_run_id` và `review_idempotency_key` riêng.
Để xem kết quả review, gán `run_id=review_run_id`, reset `history_after=0`,
`sse_after=0`, `last_event_id=0`, sau đó gọi request Wait for run và folder 06–07
trước khi Revoke session. Review dùng draft/nguồn đã lưu; không tự lấy nguồn mới.

Nguồn định dạng và workflow:
[Postman schemas](https://schema.postman.com/),
[Collection Runner workflows](https://learning.postman.com/v11/docs/tests-and-scripts/running-collections/building-workflows/),
[SSE support](https://blog.postman.com/support-for-server-sent-events/).
