# Import và thử API bằng Postman

Bộ JSON hiện có **81 HTTP operations / 84 requests**. Ba request bổ sung là
SSE replay, result kèm intermediate và export Markdown. Collection được sinh
từ OpenAPI và có test đối chiếu toàn bộ method/path, query, auth và cờ cho phép
ghi. Template không chứa password, token hoặc ID của dữ liệu đã chạy.

## Import và chọn server

Trong Postman Desktop, Import các file sau rồi chọn environment:

- [Collection](../postman/heritage-vqa.postman_collection.json).
- [Demo](../postman/heritage-vqa-demo.postman_environment.json): `http://127.0.0.1:8001`.
- [Local API](../postman/heritage-vqa-local.postman_environment.json): `http://127.0.0.1:8000`.

`base_url` là origin, không thêm `/api/v1`. Đọc Capabilities và Readiness trước
khi thử thao tác. `/api/v1` là tiền tố HTTP; Swagger và `X-Backend-Build` nhận
diện bản phần mềm đang phục vụ. Các key model/LangSmith thuộc cấu hình server.
Chỉ nhập token vào biến secret của Postman, không có tiền tố `Bearer`; không
đưa environment đang chứa credential vào Git.

## Mặc định và cờ cho phép

Model calls, đăng ký tài khoản, chỉnh sửa nguồn, duyệt/xuất bản, upload media,
đổi role và thao tác xóa đều mặc định tắt. Request thiếu ID/token phụ thuộc
được bỏ qua. Có thể đọc catalog và tạo phiên khách mà không tạo tài khoản
hoặc công bố dữ liệu.

| Biến | Khi nào bật hoặc điền |
| --- | --- |
| `enable_model_calls` | Cho phép tạo run demo hoặc kiểm tra quyền chạy live trước mutation |
| `allow_live_model_calls`, `live_model_consent` | Cả hai phải `true` mới cho phép model live có thể tính phí |
| `run_lifecycle_actions` | Cancel/retry/review/clarification/resume và teardown phiên khách |
| `enable_accounts` | Đăng ký, đăng nhập, refresh hoặc logout tài khoản |
| `enable_account_updates` | Sửa profile hoặc password |
| `enable_role_changes` | Gán role bằng operations hoặc admin token; đăng ký không tự cấp role |
| `enable_conversation_writes` | Tạo/sửa/xóa hội thoại hoặc quên memory |
| `enable_favorite_writes` | Thêm/xóa yêu thích di tích của tài khoản |
| `enable_catalog_writes`, `catalog_write_body` | POST/PUT catalog; body đầy đủ, PUT có version hiện tại |
| `enable_editorial_writes` | Tạo phiên bản nguồn hoặc sửa cấu trúc biên tập |
| `enable_remote_ingest` | Tải URL thuộc allowlist vào draft |
| `enable_source_review` | Gửi tuyên bố duyệt sau khi đã đọc và đối chiếu nguồn |
| `enable_source_publish` | Xuất bản phiên bản đã được duyệt |
| `enable_media_writes` | Upload/thay/xóa ảnh catalog bằng file được chọn |
| `enable_destructive_actions` | Bắt buộc riêng cho DELETE, archive và withdraw |

Mọi request tạo công việc model đọc lại capabilities bằng `pm.sendRequest`
trước khi gửi. Request dừng nếu không xác minh được chế độ hoặc thiếu hai cờ
đồng ý live. Các tác vụ folder 10/14 còn cần `run_lifecycle_actions=true`.
Tham chiếu: [sendRequest](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-send-request),
[skipRequest](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-execution).

## Các folder

| Folder | Nội dung |
| --- | --- |
| 01 System / Catalog | Health, capabilities, ảnh mẫu, di tích, ảnh, context và nguồn công bố |
| 02 Session | Cấp/đọc phiên khách, giữ riêng với session tài khoản |
| 03 Assets | Asset từ sample, PNG, upload và nhập ảnh catalog tùy chọn |
| 04 Workflow | Sơ đồ/giai đoạn và preflight metadata model |
| 05–08 | Run, SSE, bằng chứng, crop, kết quả, feedback và bookmark run |
| 09 Operations | Metrics và POST/PUT catalog |
| 10 Lifecycle | Clarification, cancel, Judge-only review, retry, xóa asset tùy chọn |
| 11 Accounts | Register/login/refresh, profile/password, gán role admin/operations |
| 12 Conversations | Hội thoại, lượt chat, memory và yêu thích di tích |
| 13 Editorial | Nguồn/phiên bản, review/publish/withdraw, binding, audit, media và archive |
| 14 Recovery | Checkpoint đã hoàn tất, resume WorkerLost, soft-delete run |
| 15 Session teardown | Thu hồi session tài khoản/khách, chạy cuối |

## Run, evidence và phục hồi

Tạo session khách → tạo asset từ sample → đặt `enable_model_calls=true` → Create
run. Script lưu `access_token`, `asset_id`, `run_id`, request ID và khóa
idempotency. `bootstrap_token` chỉ dùng khi server yêu cầu cấp phiên bằng bootstrap.

`focus_box`, `location_hint`, `run_heritage_id`, `run_conversation_id` là giá trị
JSON, mặc định `null`. Ví dụ hint:
`{"name":"Chùa Hương","provenance":"user"}`. ID trong body dùng JSON string
`"UUID hoặc ID di tích"`. Chọn di tích vẫn là ngữ cảnh chưa xác minh.

Profile `hanoi-evidence` trả nhận diện, claim/evidence, vùng ảnh và clarification.
GET evidence lưu `region_id`; GET clarification lưu ID/revision. Điền
`clarification_answer` hoặc `selected_candidate`, bật model/lifecycle rồi gửi
POST clarification. Run con lưu ở `clarification_run_id`, giữ câu hỏi/parent.
`awaiting_input` kết thúc một đoạn polling/SSE.

Runner/Newman polling có khoảng nghỉ và giới hạn lượt. Khi Send riêng lẻ,
`setNextRequest` không tự gửi tiếp; bấm status lại hoặc dùng Runner. Kết quả chưa
sẵn sàng trả 409; readiness 503 thể hiện DB/worker chưa sẵn sàng. SSE theo giai
đoạn, chưa stream từng token đáp án.

Đổi input dùng khóa idempotency mới. Retry và review có khóa riêng; review chỉ
gọi Judge và dùng artifact parent. Resume chỉ bật khi GET recovery trả
`can_resume=true`, dùng `resume_idempotency_key` riêng. Không tự resume run đã
thành công. Teardown phiên khách cần cả lifecycle và destructive flags.

## Tài khoản, hội thoại và biên tập

Điền `account_email`, `display_name`, `account_password` rồi bật
`enable_accounts`. Password và refresh/access token là secret. Login/refresh lưu
`account_access_token`; `/users/me` và favorites dùng token này. Run/conversation
dùng `access_token`: chủ động đặt biến đó bằng account access token hiện tại
nếu muốn làm việc dưới tài khoản. Refresh xoay token; cập nhật token sở hữu
đang dùng sau khi refresh.

Hội thoại có version cho chỉnh sửa đồng thời. Memory mặc định tắt, có giới hạn
và được gắn là ngữ cảnh chưa xác minh. Yêu thích di tích khác bookmark run.
Xóa hội thoại không tự xóa run; run có soft-delete và retention riêng.

Editorial dùng `editor_access_token` hoặc `operations_token` qua biến cục bộ
`editorial_token`. Role tài khoản được kiểm tra ở DB. Endpoint gán role dùng
`admin_access_token` hoặc operations token qua `role_token`, cùng cờ
`enable_role_changes`; editor không có quyền gán role.

Nguồn mới luôn vào draft. `source_id`, `version_id`, `source_version` được lưu
sau thao tác. Khi đã đọc/đối chiếu, điền
`source_review_attestation=reviewed_against_source` và `review_note`, bật
`enable_source_review`. Xuất bản cần thêm `enable_source_publish`. Việc này
ghi nhận quy trình review, không chứng minh độ chính xác nhận diện hoặc lịch sử.

Media upload cần chọn JPEG/PNG/WebP trong Body → form-data và version catalog
hiện tại. Không tự đặt multipart Content-Type để Postman tạo boundary. DELETE
run/media/conversation dùng ID riêng, mặc định rỗng: `delete_run_id`,
`delete_media_id`, `delete_conversation_id`; archive dùng `archive_heritage_id`.
Chọn ID/version chủ động trước khi bật cờ xóa. Bulk purge và duyệt bộ gold là
công cụ CLI; collection không tự purge hoặc chấm chất lượng từ kết quả demo.

## Tạo lại và kiểm tra

```powershell
uv run --locked python -m scripts.export_postman
uv run --locked pytest tests/test_postman_export.py
uv run --locked python -m scripts.api_contract_report --port 18091
```

Generator yêu cầu method/path khớp OpenAPI hoàn toàn. Runner HTTP tạo
SQLite/API/worker tạm riêng và tự dừng tiến trình sở hữu. Accounts/sources là
fixture tổng hợp, không phải người dùng hoặc tư liệu/gold được nghiệm thu.
Recovery endpoint dùng WorkerLost tổng hợp trong DB tạm, không được tính là thử
kill worker thật. Không gửi vào API phục vụ UI hoặc gọi model thật.

Report mặc định ở `reports/api-contract/results.json` và `results.md`, bị Git
bỏ qua; token/password được che. Kết quả kiểm chứng của nhánh tách được ghi ở
[BACKEND_ISOLATION.md](BACKEND_ISOLATION.md), không dùng lại số liệu của deployment
local trước đó. Chạy exporter/tests không phải một lượt chạy collection trong
ứng dụng Postman Desktop.
