# Kiến trúc frontend và ranh giới tích hợp

Tài liệu cũ trong file này mô tả hợp đồng API giả định của gói giao diện tham
khảo. Nội dung đó đã được thay thế để phản ánh đúng repository hiện tại.

## Kiến trúc

Frontend gồm năm lớp chính:

1. **Giao diện và route** — React Router cung cấp bố cục ứng dụng, bố cục quản
   trị, màn hình xác thực, Chat, hồ sơ di sản, bản đồ, yêu thích, profile và
   trạng thái 403/404.
2. **Trạng thái sản phẩm** — AppContext quản lý chế độ Preview/API, capability,
   guest session và thông báo. PreviewProvider giữ dữ liệu mô phỏng dùng chung.
3. **Transport** — src/api/http.ts ánh xạ đúng FastAPI hiện có, xác thực response
   bằng Zod, giới hạn Bearer theo đúng origin/prefix và xử lý lỗi chuẩn hóa.
4. **Streaming** — src/api/sse.ts đọc fetch stream có Authorization, giữ phần
   chunk chưa hoàn chỉnh, bỏ heartbeat, theo dõi sequence và hỗ trợ kết nối lại.
5. **Trình bày an toàn** — Markdown không thực thi raw HTML; ảnh được bảo vệ tải
   bằng Blob; URL ngoài và dữ liệu bản đồ được kiểm tra trước khi hiển thị.

## Hai chế độ

### UI Preview

VITE_FRONTEND_MODE=preview dùng fixture xác định, không gọi AI và không ghi dữ
liệu lên backend. Banner sau luôn hiển thị:

> UI Preview — Dữ liệu mô phỏng, chưa lưu lên backend

Preview cung cấp account giả lập, ba vai trò guest/user/admin, catalog di sản,
yêu thích, marker bản đồ và thao tác admin. Các trang dùng cùng một store để
thay đổi admin xuất hiện nhất quán ở danh sách, chi tiết, bản đồ và yêu thích.

### API integration

VITE_FRONTEND_MODE=api dùng backend FastAPI thật. Backend hiện có guest session,
asset, sample, run, event, kết quả, nguồn, stage snapshot, model attempt,
cancel/retry/review, bookmark run, feedback và export.

Frontend phải đọc model_mode từ /api/v1/capabilities. Chỉ khi giá trị là demo
mới được tạo run, retry hoặc Judge-only review trong quy trình kiểm thử này.
Không được tự chuyển sang fixture khi HTTP thất bại.

## Ranh giới domain

- api_sessions là phiên xác thực/ownership, không phải cuộc hội thoại.
- parent_run_id không phải bộ nhớ hội thoại.
- Steps là snapshot của giai đoạn workflow, không mặc nhiên là một LLM/tool
  call.
- Metrics có model attempts nhưng không có prompt, hidden reasoning hoặc tool
  trace.
- Run bookmark không phải heritage favorite.
- Sample image không phải hồ sơ di sản.
- Retrieved source không phải bản ghi source quản trị hoặc corpus RAG.
- Link tìm kiếm bản đồ không phải tọa độ đã xác minh.
- Frontend role guard không thay thế RBAC phía server.

## Tài liệu chi tiết

- [API_INTEGRATION.md](API_INTEGRATION.md)
- [FEATURE_MATRIX.md](FEATURE_MATRIX.md)
- [MISSING_BACKEND_CAPABILITIES.md](MISSING_BACKEND_CAPABILITIES.md)
- [TESTING.md](TESTING.md)
- [DEPLOYMENT.md](DEPLOYMENT.md)
