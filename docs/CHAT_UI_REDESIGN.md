# Thiết kế lại giao diện hỏi đáp AI

Ngày kiểm tra: 15/11/2026. Phạm vi: giao diện nhập câu hỏi và trang kết quả,
cả UI Preview và chế độ API. Không thay đổi hợp đồng backend hoặc gọi model
AI trả phí trong đợt thiết kế này.

## Thay đổi chính

- Vùng nhập được đưa vào trung tâm: tiêu đề gọn, ảnh đính kèm dạng thẻ nhỏ,
  câu hỏi và nút gửi nằm gần nhau. Có gợi ý câu hỏi và Ctrl/⌘ + Enter.
- Hỗ trợ chọn/kéo thả, đổi và bỏ ảnh. Tệp sai định dạng không làm mất ảnh
  hoặc câu hỏi đang có; có giới hạn kích thước theo cấu hình đầu vào.
- Lịch sử mở theo nhu cầu thay vì chiếm một cột thường trực. Mobile dùng
  panel trong viewport; Escape đóng và trả focus về nút mở, giữ nguyên bản nháp.
- Trang kết quả ưu tiên câu trả lời và nguồn hỗ trợ. Chi tiết workflow/model
  được thu trong mục “Chi tiết xử lý”, người dùng có thể mở khi cần.
- Nguồn trong Preview được ghi rõ là metadata minh họa. Chế độ API tiếp tục
  dùng ảnh, phiên khách, trạng thái, nguồn, phản hồi và tác vụ từ backend;
  giữ nguyên consent/gate AI live và cơ chế upload, preflight, retry, review.
- Không thêm blur nền hoặc hiệu ứng vẽ lại liên tục khi cuộn. Giữ hỗ trợ
  reduced motion và bố cục không tràn ngang ở 320px/390px.

Triển khai: [ChatComposer.tsx](../frontend/src/ui/ChatComposer.tsx),
[ChatWorkspace.tsx](../frontend/src/ui/ChatWorkspace.tsx),
[ChatPages.tsx](../frontend/src/pages-v2/ChatPages.tsx),
[chat-experience.css](../frontend/src/ui/chat-experience.css).

## Quan sát bố cục trước/sau

Số đo UI Preview local ở trạng thái trang nhập ban đầu; đơn vị px. Đây là phép đo vị trí
và chiều cao bố cục, không phải benchmark FPS hoặc thời gian phản hồi AI.

| Màn hình | Nút gửi trước | Nút gửi sau | Chiều cao trang trước → sau |
| --- | --- | --- | --- |
| Desktop 1366×768 | y≈790, dưới màn hình đầu | y≈602, đáy≈646 | 1011 → 903 |
| Mobile 390×844 | y≈797 | y≈624, đáy≈668 | 1413 → 995 |

Desktop: [trước](../frontend/artifacts/screenshots/chat-redesign/chat-before-desktop.png),
[sau](../frontend/artifacts/screenshots/chat-redesign/chat-after-desktop.png).
Mobile: [trước](../frontend/artifacts/screenshots/chat-redesign/chat-before-mobile.png),
[sau](../frontend/artifacts/screenshots/chat-redesign/chat-after-mobile.png).
[Trang kết quả mới](../frontend/artifacts/screenshots/chat-redesign/chat-result-desktop.png).
[Kết quả mobile](../frontend/artifacts/screenshots/chat-redesign/chat-result-mobile.png),
[lịch sử mobile](../frontend/artifacts/screenshots/chat-redesign/chat-history-mobile.png).

Giao diện API cũng được kiểm tra trực quan với backend Docker demo:
[trang nhập](../frontend/artifacts/screenshots/chat-redesign/chat-api-compose.png),
[kết quả desktop](../frontend/artifacts/screenshots/chat-redesign/chat-api-result-desktop.png),
[kết quả mobile](../frontend/artifacts/screenshots/chat-redesign/chat-api-result-mobile.png).
Nút gửi ở desktop API nằm tại y≈705, đáy≈749 trong viewport 1366×768.
Các phiên khách tạo cho smoke test đã được thu hồi sau kiểm tra.

## Kiểm chứng

- Typecheck, lint, build và 41 unit tests đạt.
- 5/5 E2E Chat mới đạt: nút chính nằm trong viewport desktop, upload/drop/
  remove/reselect ảnh, lỗi tệp không mất bản nháp, gợi ý, nguồn minh họa,
  workflow thu gọn, lịch sử, Escape/focus và mobile 320px/390px.
- 7/7 E2E Preview toàn giao diện đạt, bao gồm catalog, ảnh lỗi/thử lại,
  đăng nhập mô phỏng, admin CRUD và bản đồ.
- 2/2 E2E với backend Docker local ở `model_mode=demo` đạt. Đây là gọi API
  thật với inference demo, không phải xác minh chất lượng model AI live.
- 4/4 E2E cuộn đạt sau thay đổi bố cục Chat, gồm cuộn native desktop/mobile,
  ảnh tải chậm/reduced motion và danh sách map không bị zoom theo wheel.

Tổng trong đợt kiểm tra này: **18/18 E2E đạt**. Các suite tách biệt UI Preview,
backend demo và AI live để không gọi nhầm model có thể tính phí.

Suite mới [chat-ui.spec.ts](../frontend/tests/e2e/chat-ui.spec.ts) chặn host
ngoài local và mọi request API/health. Nó không dùng token Mapbox hoặc gọi AI.

```powershell
cd frontend
$env:RUN_CHAT_UI = '1'
npm run test:e2e
Remove-Item Env:RUN_CHAT_UI
```

Các nhãn trong E2E API/live được cập nhật theo giao diện mới. Suite AI live
không được chạy trong đợt này. Backend hiện chưa cung cấp conversation/turn
memory; lịch sử ở đây là các lần hỏi/run, không phải hội thoại nhiều lượt
được lưu bởi backend.
