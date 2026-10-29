# Theo dõi bằng LangSmith

Workflow Streamlit và CLI dùng chung telemetry. Các lần gọi SDK trực tiếp qua
gateway cũng có trace, bao gồm cả baseline so sánh và legacy streaming.

## Bật theo môi trường

Điền trong `.env` đã được Git bỏ qua, hoặc cấu hình qua secret của môi trường deploy:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<key của workspace>
LANGSMITH_PROJECT=heritage-vqa-dev
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
# LANGSMITH_WORKSPACE_ID=<workspace ID nếu key thuộc nhiều workspace>
```

Khởi động lại Streamlit sau khi đổi `.env`. Đổi project để tách dev/test/production.
Workspace EU dùng endpoint `https://eu.api.smith.langchain.com` theo tài liệu
[LangSmith về region](https://docs.langchain.com/langsmith/trace-with-langgraph).
Đặt `LANGSMITH_TRACING=false` để tắt. Khi thiếu key, telemetry cũng tự tắt.

## Xem gì trên dashboard

Mở [LangSmith](https://smith.langchain.com), chọn project đã cấu hình:

- `heritage-vqa.run`: trace gốc; ID trùng `run_id` trong kết quả JSON và UI.
- `heritage-vqa.graph`: đồ thị thật, gồm nhánh Visual/Knowledge chạy song song.
- `model.<role>`: từng attempt gọi Gemini/OpenAI/GPU, thời gian, provider/model,
  số lần retry và cờ fallback. `model.<role>.stream` dành cho legacy streaming.
- `search.wikipedia`: thời gian truy xuất, trạng thái và số nguồn tìm thấy.
- Metadata gốc: workflow version, config hash, audience, benchmark,
  `result_status`, `error_count`. Lỗi đã được node xử lý vẫn được đánh dấu trên trace.

Token được chuẩn hóa từ usage thực do SDK trả về; Gemini output bao gồm thinking
tokens khi SDK cung cấp. Thiếu usage thì để trống. Giá tiền phụ thuộc model có nằm
trong bảng giá LangSmith hay không; hệ thống không tự ước lượng chi phí GPU/model lạ.
Baseline gọi model trực tiếp có trace theo attempt; không có graph node vì không
đi qua workflow LangGraph.

## Dữ liệu gửi đi

Client riêng lọc dữ liệu trước khi SDK đưa vào hàng đợi. Chỉ giữ metadata và
summary vận hành trong danh sách cho phép. Không gửi ảnh/bytes/base64, câu hỏi,
system prompt, nội dung trả lời, đoạn nguồn, config đầy đủ, attachment, serialized
objects hay chi tiết exception/traceback. Lỗi giữ loại trong metadata và thông báo
chung. Vì vậy dashboard không hiển thị nội dung prompt/response để đọc lại.

Chính sách này áp dụng cả trace tự động của LangGraph; không bật gửi nội dung bằng
biến `LANGSMITH_HIDE_INPUTS=false`. API key nằm trong `.env`/secret, không xuất vào
config snapshot hay result. Kiểm thử offline tắt telemetry và chặn mạng.

SDK gửi trace nền; flush khi trace gốc kết thúc có giới hạn một giây. Lỗi telemetry
không đổi kết quả workflow; khi mạng lỗi, trace có thể bị thiếu hoặc đến muộn.

## Kiểm tra kết nối riêng

```powershell
uv run --locked python -m scripts.langsmith_smoke
```

Lệnh gửi một trace đồ thị tổng hợp, đọc lại trace gốc và graph để xác nhận che
dữ liệu. Không gọi Gemini/OpenAI/GPU. Kết quả thành công có `trace_verified=true`,
`redaction_verified=true` và `model_calls=0`. Lỗi chỉ in HTTP status hoặc tên loại lỗi.

Tài liệu chính thức: [LangGraph tracing](https://docs.langchain.com/langsmith/trace-with-langgraph),
[custom spans](https://docs.langchain.com/langsmith/annotate-code),
[ẩn inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs).
