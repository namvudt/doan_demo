# Kết quả kiểm thử từng API

Thời điểm: 2026-11-04T22:07:43.864257+07:00 (Asia/Ho_Chi_Minh).
Base URL: `http://127.0.0.1:18512`. Chạy HTTP thật với API và worker riêng, SQLite riêng, **demo mode**.
Không gọi Gemini/GPU thật; báo cáo này kiểm tra hợp đồng API và workflow, không đo chất lượng AI.

- OpenAPI: **30/30 operations** đã được gọi và kiểm tra.
- Kịch bản: **69/69 đạt**, 0 lỗi.
- Run chính: `d39c80c8-4e1c-4d59-b1d2-f67317dddd10`.
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
| 26 | GET | `/api/v1/runs/{run_id}/export` | 200 | 2 | Đạt |
| 27 | PUT | `/api/v1/runs/{run_id}/bookmark` | 200 | 1 | Đạt |
| 28 | POST | `/api/v1/runs/{run_id}/feedback` | 200 | 1 | Đạt |
| 29 | PUT | `/api/v1/runs/{run_id}/feedback` | 200 | 1 | Đạt |
| 30 | GET | `/api/v1/runs/{run_id}/feedback` | 200 | 2 | Đạt |

## Chi tiết các tình huống

HTTP 4xx/503 trong case âm là kết quả đúng khi trùng với kỳ vọng.

| Case | Tình huống | Kỳ vọng | Thực nhận | ms | Kết quả trả về | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | Tiến trình API hoạt động | 200 | 200 | 3.22 | status=ok | Đạt |
| C02 | Chưa có worker: readiness trả 503 | 503 | 503 | 8.81 | status=worker_unavailable; model_mode=demo | Đạt |
| C03 | Cấu hình demo và giới hạn | 200 | 200 | 6.01 | model_mode=demo | Đạt |
| C04 | Cấp phiên thiếu bootstrap bị từ chối | 403 | 403 | 2.91 | error.code=bootstrap_required | Đạt |
| C05 | Cấp token phiên A | 201 | 201 | 6.76 | Đã cấp access_token; token được che trong báo cáo | Đạt |
| C06 | Cấp token phiên B | 201 | 201 | 4.48 | Đã cấp access_token; token được che trong báo cáo | Đạt |
| C07 | Đọc phiên đang đăng nhập | 200 | 200 | 3.65 | session_id=c1791a2e-8665-4699-93e6-459f9abd7567 | Đạt |
| C08 | Thiếu token bị từ chối | 401 | 401 | 2.98 | error.code=authentication_required | Đạt |
| C09 | Token sai bị từ chối | 401 | 401 | 2.39 | error.code=invalid_token | Đạt |
| C10 | Sơ đồ và bảy giai đoạn | 200 | 200 | 6.83 | version=langgraph-v1 | Đạt |
| C11 | Danh sách ảnh mẫu | 200 | 200 | 2.36 | items=11 | Đạt |
| C12 | Upload ảnh multipart | 201 | 201 | 209.66 | JSON hợp lệ | Đạt |
| C13 | Danh sách ảnh của phiên | 200 | 200 | 6.11 | 1 bản ghi | Đạt |
| C14 | Metadata ảnh đã chuẩn hóa | 200 | 200 | 5.47 | JSON hợp lệ | Đạt |
| C15 | Tải ảnh PNG | 200 | 200 | 34.33 | PNG, 1200×896, 2123792 bytes | Đạt |
| C16 | Phiên B không đọc được ảnh A | 404 | 404 | 4.52 | error.code=not_found | Đạt |
| C17 | UUID không hợp lệ | 422 | 422 | 4.16 | error.code=validation_error | Đạt |
| C18 | Từ chối file giả ảnh | 422 | 422 | 73.78 | error.code=invalid_image | Đạt |
| C19 | Từ chối ảnh quá dung lượng | 413 | 413 | 81.3 | error.code=image_too_large | Đạt |
| C20 | Xóa ảnh chưa được sử dụng | 204 | 204 | 48.78 | Không có response body | Đạt |
| C21 | Ảnh đã xóa trả 404 | 404 | 404 | 4.48 | error.code=not_found | Đạt |
| C22 | Tạo asset từ ảnh mẫu | 201 | 201 | 188.87 | JSON hợp lệ | Đạt |
| C23 | Ảnh mẫu không tồn tại | 404 | 404 | 3.35 | error.code=sample_not_found | Đạt |
| C24 | Tạo run và nhận 202 | 202 | 202 | 22.68 | execution_status=queued | Đạt |
| C25 | Gửi trùng key/body trả cùng run | 202 | 202 | 5.45 | execution_status=queued | Đạt |
| C26 | Trùng key nhưng khác body trả 409 | 409 | 409 | 5.67 | error.code=idempotency_conflict | Đạt |
| C27 | Câu hỏi rỗng trả 422 | 422 | 422 | 4.27 | error.code=validation_error | Đạt |
| C28 | Profile chưa hỗ trợ trả 422 | 422 | 422 | 4.03 | error.code=validation_error | Đạt |
| C29 | Không dùng ảnh của phiên khác | 404 | 404 | 11.77 | error.code=not_found | Đạt |
| C30 | Đọc trạng thái queued | 200 | 200 | 6.51 | execution_status=queued | Đạt |
| C31 | Chưa xong: result trả 409 | 409 | 409 | 5.4 | error.code=run_not_finished | Đạt |
| C32 | Không retry run còn hoạt động | 409 | 409 | 4.72 | error.code=run_active | Đạt |
| C33 | Phiên B không đọc được run A | 404 | 404 | 3.39 | error.code=not_found | Đạt |
| C34 | Phiên B không đọc được events A | 404 | 404 | 4.81 | error.code=not_found | Đạt |
| C35 | Phiên B không hủy được run A | 404 | 404 | 5.52 | error.code=not_found | Đạt |
| C36 | Xóa ảnh đang được run sử dụng trả 409 | 409 | 409 | 4.41 | error.code=asset_in_use | Đạt |
| C37 | Tạo run để hủy | 202 | 202 | 16.07 | execution_status=queued | Đạt |
| C38 | Hủy queued có hiệu lực ngay | 200 | 200 | 6.87 | execution_status=cancelled | Đạt |
| C39 | Run đã hủy không có answer | 409 | 409 | 4.66 | error.code=result_unavailable | Đạt |
| C40 | Retry bắt buộc Idempotency-Key | 422 | 422 | 4.04 | error.code=validation_error | Đạt |
| C41 | Retry tạo run mới liên kết parent | 202 | 202 | 16.47 | execution_status=queued | Đạt |
| C42 | Tạo active run thứ ba | 202 | 202 | 15.41 | execution_status=queued | Đạt |
| C43 | Vượt ba active runs trả 429 | 429 | 429 | 13.19 | error.code=queue_limit | Đạt |
| C44 | Hủy run quota sau kiểm tra | 200 | 200 | 6.16 | execution_status=cancelled | Đạt |
| C45 | Database và worker sẵn sàng | 200 | 200 | 2.51 | status=ready; model_mode=demo | Đạt |
| C46 | Run đã hoàn tất | 200 | 200 | 5.42 | execution_status=succeeded | Đạt |
| C47 | Lịch sử có phân trang | 200 | 200 | 8.29 | items=2 | Đạt |
| C48 | Lọc lịch sử succeeded | 200 | 200 | 6.9 | items=2 | Đạt |
| C49 | Lịch sử sự kiện JSON | 200 | 200 | 7.8 | items=21 | Đạt |
| C50 | Lịch sử có bản nháp khi opt-in | 200 | 200 | 6.38 | items=21 | Đạt |
| C51 | Nhận toàn bộ SSE và terminal event | 200 | 200 | 10.91 | 21 SSE events | Đạt |
| C52 | SSE kết nối lại từ Last-Event-ID | 200 | 200 | 7.38 | 2 SSE events | Đạt |
| C53 | Kết quả cuối và nguồn | 200 | 200 | 5.28 | status=reviewed; sources=1 | Đạt |
| C54 | Kết quả có nội dung trung gian opt-in | 200 | 200 | 4.94 | status=reviewed; sources=1 | Đạt |
| C55 | Nguồn có trích dẫn | 200 | 200 | 5.34 | items=1 | Đạt |
| C56 | Các giai đoạn và bản nháp mặc định ẩn | 200 | 200 | 6.14 | items=9 | Đạt |
| C57 | Các giai đoạn bật bản nháp | 200 | 200 | 5.95 | items=9 | Đạt |
| C58 | Metrics demo không tự tạo token usage | 200 | 200 | 4.71 | 5 model calls; total_tokens=null (demo) | Đạt |
| C59 | Xuất JSON không kèm draft mặc định | 200 | 200 | 4.74 | status=reviewed; sources=1 | Đạt |
| C60 | Xuất Markdown | 200 | 200 | 5.37 | Đã nhận báo cáo Markdown | Đạt |
| C61 | Đánh dấu run | 200 | 200 | 61.22 | execution_status=succeeded | Đạt |
| C62 | Lọc các run đã lưu | 200 | 200 | 6.43 | items=1 | Đạt |
| C63 | Ghi phản hồi bằng POST | 200 | 200 | 8.11 | rating=helpful | Đạt |
| C64 | Đọc phản hồi đã lưu | 200 | 200 | 6.18 | rating=helpful | Đạt |
| C65 | Cập nhật phản hồi bằng PUT | 200 | 200 | 6.43 | rating=needs_review | Đạt |
| C66 | Xác nhận cập nhật phản hồi | 200 | 200 | 5.04 | rating=needs_review | Đạt |
| C67 | Thu hồi token phiên B | 204 | 204 | 6.46 | Không có response body | Đạt |
| C68 | Token đã thu hồi trả 401 | 401 | 401 | 2.33 | error.code=invalid_token | Đạt |
| C69 | Thu hồi token phiên A | 204 | 204 | 4.57 | Không có response body | Đạt |

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
