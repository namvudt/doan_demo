# Sửa lỗi phản hồi model và thiếu nội dung LangSmith — 13/11/2026

## Sự cố

Run `efb508e4-7793-4649-9f53-570dfafc5be5`, lúc 10:40:55–10:41:29 Asia/Saigon,
thất bại tại visual/ValueError. Coordinator và knowledge thành công, search có
hai nguồn. Trace không giữ input/output vì client chủ động che, và gateway làm
mất usage/finish reason nếu validation response raise. Streamlit local không
khởi tạo logger API/worker nên không có JSONL cho lượt này.

Không thể khôi phục prompt/finish reason đã bị loại bỏ của lượt cũ. Nguyên nhân
cụ thể MAX_TOKENS của lượt cũ vẫn chưa được chứng minh.

## Thay đổi

- Content mode LangSmith có cờ riêng; thu câu hỏi, prompt/system instruction,
  response, báo cáo agent và nguồn; credential được che trước hàng đợi SDK.
  Chế độ summary vẫn được kiểm thử độc lập. Ảnh là metadata/fingerprint.
- Gắn JSON logger có rotation cho Streamlit và CLI, dùng lại handler qua rerun.
- Phân biệt response rỗng, bị chặn, bị cắt và finish không hoàn chỉnh. Giữ
  usage, finish/block reason, output limit và provider HTTP status khi có.
- MAX_TOKENS/length được thử lại tối đa một lần với giới hạn tăng gấp đôi, có
  ceiling và ngân sách tổng. Empty/block không retry. Partial stream không replay.
- Visual có output limit 4096 thay vì dùng chung mức 2048; các role khác giữ
  budget riêng như cũ. Có cấu hình thinking level tùy model, không ép mặc định.
- Migration 0003 lưu diagnostics cho API attempts; bảng kỹ thuật UI hiển thị thêm
  finish reason, mã lỗi, HTTP provider và output limit.

## Xác minh

- Fixture mô phỏng text rỗng/truncate: giữ được usage, phân loại đúng và có bounded
  recovery. Kiểm tra thêm safety block, SDK text extraction error, call budget,
  provider status, database persistence, credential masking và UI logging.
- Synthetic LangSmith smoke đã gửi/đọc lại root và native graph ở cả content và
  summary mode; input/output xuất hiện đúng mode, credential mẫu bị che, 0 model calls.
- Một visual call thật với ảnh mẫu Chùa Một Cột và câu hỏi quan sát kiến trúc:
  `gemini-3.5-flash`, STOP, 18.25 giây cho model, 3160 ký tự kết quả, 1557 input
  tokens + 2697 output/thinking tokens = 4254 total. Thành công ở attempt đầu với
  output limit 4096. Lượng output này vượt 2048, cho thấy mức cũ có thể quá thấp;
  không dùng lượt khác ảnh/câu hỏi để khẳng định nguyên nhân chính xác của run cũ.
- Đã đọc lại trace thật: root query, model prompt/system instruction và response
  có nội dung, finish reason STOP. Chỉ dùng một model call thật trong đợt kiểm tra.
- API demo chạy HTTP thật: 31/31 operations, 73/73 cases đạt, không gọi model trả phí.
- Bộ kiểm thử ứng dụng: 135 tests đạt; Ruff check/format và migration schema check đạt.

Chi tiết lượt kiểm tra thật ở `reports/incident/visual-fix-validation.json` local
(bị Git bỏ qua). Hướng dẫn cấu hình: [langsmith.md](../langsmith.md).

## Áp dụng

Cấu hình local `.env` đã bật `LANGSMITH_CAPTURE_CONTENT=true`, giữ nguyên key/model.
Reload/khởi động lại Streamlit và API để nạp code/env mới. API/worker tự migrate
DB khi startup; Streamlit local không tự migrate hoặc tạo queue. Workflow chạy
mới mới có nội dung trace; các run cũ vẫn giữ chính sách nội dung của lúc tạo.
