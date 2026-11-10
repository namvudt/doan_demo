# Kết quả kiểm thử từng API

Thời điểm: 2026-11-10T15:48:18.828666+07:00 (Asia/Ho_Chi_Minh).
Base URL: `http://127.0.0.1:18512`. Chạy HTTP thật với API và worker riêng, SQLite riêng, **demo mode**.
Không gọi Gemini/GPU thật; báo cáo này kiểm tra hợp đồng API và workflow, không đo chất lượng AI.

- OpenAPI: **31/31 operations** đã được gọi và kiểm tra.
- Kịch bản: **73/73 đạt**, 0 lỗi.
- Run chính: `55500e90-2c23-451f-bdfa-c5c776d864b5`.
- Run chính phát 21 events, trả 1 nguồn minh họa; model calls trả phí: **0**.
- Token và bootstrap credential đã được che; thời gian dưới đây chỉ là một lượt local, không phải benchmark.

## Tổng hợp theo từng API

| # | Method | Endpoint | HTTP thực nhận | Số case | Kết quả |
| --- | --- | --- | --- | --- | --- |
| 1 | GET | `/health/live` | 200 | 1 | Đạt |
| 2 | GET | `/health/ready` | 200, 503 | 2 | Đạt |
| 3 | POST | `/api/v1/sessions` | 201, 403 | 3 | Đạt |
| 4 | GET | `/api/v1/sessions/me` | 200, 401 | 2 | Đạt |
| 5 | DELETE | `/api/v1/sessions/me` | 204 | 2 | Đạt |
| 6 | GET | `/api/v1/capabilities` | 200 | 1 | Đạt |
| 7 | GET | `/api/v1/workflow` | 200 | 1 | Đạt |
| 8 | POST | `/api/v1/assets` | 201, 413, 422 | 3 | Đạt |
| 9 | GET | `/api/v1/assets` | 200 | 1 | Đạt |
| 10 | GET | `/api/v1/assets/{asset_id}` | 200, 404, 422 | 4 | Đạt |
| 11 | DELETE | `/api/v1/assets/{asset_id}` | 204, 409 | 2 | Đạt |
| 12 | GET | `/api/v1/assets/{asset_id}/content` | 200 | 1 | Đạt |
| 13 | GET | `/api/v1/samples` | 200 | 1 | Đạt |
| 14 | POST | `/api/v1/samples/{sample_id}/assets` | 201, 404 | 2 | Đạt |
| 15 | POST | `/api/v1/runs` | 202, 404, 409, 422, 429 | 9 | Đạt |
| 16 | GET | `/api/v1/runs` | 200, 401 | 5 | Đạt |
| 17 | GET | `/api/v1/runs/{run_id}` | 200, 404 | 3 | Đạt |
| 18 | POST | `/api/v1/runs/{run_id}/cancel` | 200, 404 | 3 | Đạt |
| 19 | POST | `/api/v1/runs/{run_id}/retry` | 202, 409, 422 | 3 | Đạt |
| 20 | GET | `/api/v1/runs/{run_id}/events/history` | 200, 404 | 3 | Đạt |
| 21 | GET | `/api/v1/runs/{run_id}/events` | 200 | 2 | Đạt |
| 22 | GET | `/api/v1/runs/{run_id}/result` | 200, 409 | 4 | Đạt |
| 23 | GET | `/api/v1/runs/{run_id}/sources` | 200 | 1 | Đạt |
| 24 | GET | `/api/v1/runs/{run_id}/steps` | 200 | 2 | Đạt |
| 25 | GET | `/api/v1/runs/{run_id}/metrics` | 200 | 1 | Đạt |
| 26 | GET | `/api/v1/operations/metrics` | 200, 401 | 4 | Đạt |
| 27 | GET | `/api/v1/runs/{run_id}/export` | 200 | 2 | Đạt |
| 28 | PUT | `/api/v1/runs/{run_id}/bookmark` | 200 | 1 | Đạt |
| 29 | POST | `/api/v1/runs/{run_id}/feedback` | 200 | 1 | Đạt |
| 30 | PUT | `/api/v1/runs/{run_id}/feedback` | 200 | 1 | Đạt |
| 31 | GET | `/api/v1/runs/{run_id}/feedback` | 200 | 2 | Đạt |

## Chi tiết các tình huống

HTTP 4xx/503 trong case âm là kết quả đúng khi trùng với kỳ vọng.

| Case | Tình huống | Kỳ vọng | Thực nhận | ms | Kết quả trả về | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | Tiến trình API hoạt động | 200 | 200 | 1.7 | status=ok | Đạt |
| C02 | Chưa có worker: readiness trả 503 | 503 | 503 | 8.26 | status=worker_unavailable; model_mode=demo | Đạt |
| C03 | Cấu hình demo và giới hạn | 200 | 200 | 5.43 | model_mode=demo | Đạt |
| C04 | Cấp phiên thiếu bootstrap bị từ chối | 403 | 403 | 2.29 | error.code=bootstrap_required | Đạt |
| C05 | Cấp token phiên A | 201 | 201 | 46.34 | Đã cấp access_token; token được che trong báo cáo | Đạt |
| C06 | Cấp token phiên B | 201 | 201 | 3.94 | Đã cấp access_token; token được che trong báo cáo | Đạt |
| C07 | Operations rejects missing token | 401 | 401 | 1.92 | error.code=operations_unauthorized | Đạt |
| C08 | Operations rejects guest token | 401 | 401 | 1.47 | error.code=operations_unauthorized | Đạt |
| C09 | Operations accepts operator token | 200 | 200 | 6.77 | Đã nhận báo cáo Markdown | Đạt |
| C10 | Đọc phiên đang đăng nhập | 200 | 200 | 4.5 | session_id=4b57bc1c-cfeb-4345-bd8e-b343baf86f47 | Đạt |
| C11 | Thiếu token bị từ chối | 401 | 401 | 1.88 | error.code=authentication_required | Đạt |
| C12 | Token sai bị từ chối | 401 | 401 | 2.11 | error.code=invalid_token | Đạt |
| C13 | Sơ đồ và bảy giai đoạn | 200 | 200 | 6.12 | version=langgraph-v1 | Đạt |
| C14 | Danh sách ảnh mẫu | 200 | 200 | 1.83 | items=11 | Đạt |
| C15 | Upload ảnh multipart | 201 | 201 | 194.08 | JSON hợp lệ | Đạt |
| C16 | Danh sách ảnh của phiên | 200 | 200 | 5.29 | 1 bản ghi | Đạt |
| C17 | Metadata ảnh đã chuẩn hóa | 200 | 200 | 4.88 | JSON hợp lệ | Đạt |
| C18 | Tải ảnh PNG | 200 | 200 | 24.22 | PNG, 1200×896, 2123792 bytes | Đạt |
| C19 | Phiên B không đọc được ảnh A | 404 | 404 | 3.78 | error.code=not_found | Đạt |
| C20 | UUID không hợp lệ | 422 | 422 | 2.7 | error.code=validation_error | Đạt |
| C21 | Từ chối file giả ảnh | 422 | 422 | 54.52 | error.code=invalid_image | Đạt |
| C22 | Từ chối ảnh quá dung lượng | 413 | 413 | 50.64 | error.code=image_too_large | Đạt |
| C23 | Xóa ảnh chưa được sử dụng | 204 | 204 | 77.52 | Không có response body | Đạt |
| C24 | Ảnh đã xóa trả 404 | 404 | 404 | 3.51 | error.code=not_found | Đạt |
| C25 | Tạo asset từ ảnh mẫu | 201 | 201 | 183.56 | JSON hợp lệ | Đạt |
| C26 | Ảnh mẫu không tồn tại | 404 | 404 | 2.9 | error.code=sample_not_found | Đạt |
| C27 | Tạo run và nhận 202 | 202 | 202 | 23.18 | execution_status=queued | Đạt |
| C28 | Gửi trùng key/body trả cùng run | 202 | 202 | 3.45 | execution_status=queued | Đạt |
| C29 | Trùng key nhưng khác body trả 409 | 409 | 409 | 2.46 | error.code=idempotency_conflict | Đạt |
| C30 | Câu hỏi rỗng trả 422 | 422 | 422 | 1.76 | error.code=validation_error | Đạt |
| C31 | Profile chưa hỗ trợ trả 422 | 422 | 422 | 1.92 | error.code=validation_error | Đạt |
| C32 | Không dùng ảnh của phiên khác | 404 | 404 | 8.34 | error.code=not_found | Đạt |
| C33 | Đọc trạng thái queued | 200 | 200 | 3.87 | execution_status=queued | Đạt |
| C34 | Chưa xong: result trả 409 | 409 | 409 | 3.3 | error.code=run_not_finished | Đạt |
| C35 | Không retry run còn hoạt động | 409 | 409 | 3.27 | error.code=run_active | Đạt |
| C36 | Phiên B không đọc được run A | 404 | 404 | 3.11 | error.code=not_found | Đạt |
| C37 | Phiên B không đọc được events A | 404 | 404 | 2.72 | error.code=not_found | Đạt |
| C38 | Phiên B không hủy được run A | 404 | 404 | 4.37 | error.code=not_found | Đạt |
| C39 | Xóa ảnh đang được run sử dụng trả 409 | 409 | 409 | 3.02 | error.code=asset_in_use | Đạt |
| C40 | Tạo run để hủy | 202 | 202 | 10.63 | execution_status=queued | Đạt |
| C41 | Hủy queued có hiệu lực ngay | 200 | 200 | 4.41 | execution_status=cancelled | Đạt |
| C42 | Run đã hủy không có answer | 409 | 409 | 2.54 | error.code=result_unavailable | Đạt |
| C43 | Retry bắt buộc Idempotency-Key | 422 | 422 | 1.89 | error.code=validation_error | Đạt |
| C44 | Retry tạo run mới liên kết parent | 202 | 202 | 12.32 | execution_status=queued | Đạt |
| C45 | Tạo active run thứ ba | 202 | 202 | 10.94 | execution_status=queued | Đạt |
| C46 | Vượt ba active runs trả 429 | 429 | 429 | 10.37 | error.code=queue_limit | Đạt |
| C47 | Hủy run quota sau kiểm tra | 200 | 200 | 4.18 | execution_status=cancelled | Đạt |
| C48 | Database và worker sẵn sàng | 200 | 200 | 1.72 | status=ready; model_mode=demo | Đạt |
| C49 | Run đã hoàn tất | 200 | 200 | 2.74 | execution_status=succeeded | Đạt |
| C50 | Lịch sử có phân trang | 200 | 200 | 5.08 | items=2 | Đạt |
| C51 | Lọc lịch sử succeeded | 200 | 200 | 6.78 | items=2 | Đạt |
| C52 | Lịch sử sự kiện JSON | 200 | 200 | 6.19 | items=21 | Đạt |
| C53 | Lịch sử có bản nháp khi opt-in | 200 | 200 | 4.23 | items=21 | Đạt |
| C54 | Nhận toàn bộ SSE và terminal event | 200 | 200 | 6.88 | 21 SSE events | Đạt |
| C55 | SSE kết nối lại từ Last-Event-ID | 200 | 200 | 4.58 | 2 SSE events | Đạt |
| C56 | Kết quả cuối và nguồn | 200 | 200 | 3.78 | status=reviewed; sources=1 | Đạt |
| C57 | Kết quả có nội dung trung gian opt-in | 200 | 200 | 3.17 | status=reviewed; sources=1 | Đạt |
| C58 | Nguồn có trích dẫn | 200 | 200 | 4.84 | items=1 | Đạt |
| C59 | Các giai đoạn và bản nháp mặc định ẩn | 200 | 200 | 3.91 | items=9 | Đạt |
| C60 | Các giai đoạn bật bản nháp | 200 | 200 | 3.36 | items=9 | Đạt |
| C61 | Metrics demo không tự tạo token usage | 200 | 200 | 4.34 | 5 model calls; total_tokens=null (demo) | Đạt |
| C62 | Xuất JSON không kèm draft mặc định | 200 | 200 | 2.91 | status=reviewed; sources=1 | Đạt |
| C63 | Xuất Markdown | 200 | 200 | 2.78 | Đã nhận báo cáo Markdown | Đạt |
| C64 | Đánh dấu run | 200 | 200 | 53.05 | execution_status=succeeded | Đạt |
| C65 | Lọc các run đã lưu | 200 | 200 | 4.54 | items=1 | Đạt |
| C66 | Ghi phản hồi bằng POST | 200 | 200 | 5.97 | rating=helpful | Đạt |
| C67 | Đọc phản hồi đã lưu | 200 | 200 | 2.92 | rating=helpful | Đạt |
| C68 | Cập nhật phản hồi bằng PUT | 200 | 200 | 9.4 | rating=needs_review | Đạt |
| C69 | Xác nhận cập nhật phản hồi | 200 | 200 | 3.79 | rating=needs_review | Đạt |
| C70 | Thu hồi token phiên B | 204 | 204 | 5.67 | Không có response body | Đạt |
| C71 | Token đã thu hồi trả 401 | 401 | 401 | 2.07 | error.code=invalid_token | Đạt |
| C72 | Operations metrics after processing | 200 | 200 | 3.77 | Đã nhận báo cáo Markdown | Đạt |
| C73 | Thu hồi token phiên A | 204 | 204 | 3.24 | Không có response body | Đạt |

## Xem request/response đầy đủ

Dữ liệu phản hồi thật, request, header đã che token và assertion của từng case nằm ở
[results.json](../reports/api-contract/results.json). File này được tạo local, không commit cùng source.
Ảnh tải về được ghi nhận bằng format, kích thước, số byte và SHA-256; SSE được parse thành các frame.

## Chạy lại

```powershell
uv run --locked python -m scripts.api_contract_report
```

Lệnh tạo server demo tạm trên port 18512, tạo worker riêng và tự dừng cả hai khi xong.
Không thay đổi `.env`, không gửi request vào server live port 8000. Có thể đổi `--port`.
Hướng dẫn thao tác thủ công từng API: [api-swagger-walkthrough.md](api-swagger-walkthrough.md).
