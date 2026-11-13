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
LANGSMITH_CAPTURE_CONTENT=true
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

Client lọc dữ liệu trước khi SDK đưa vào hàng đợi. Có hai chế độ:

| `LANGSMITH_CAPTURE_CONTENT` | Nội dung trên LangSmith |
| --- | --- |
| `false` hoặc chưa đặt | Summary vận hành; inputs rỗng, không gửi câu hỏi/prompt/response |
| `true` | Câu hỏi, prompt và system instruction của model, response (kể cả bản bị cắt), báo cáo các agent, nguồn và kết quả cuối đã lọc credential |

Mode content áp dụng cả root, native graph/node, model attempts và search.
Ảnh vẫn được chiếu thành kích thước/media type/SHA-256 khi có bytes; không gửi
ảnh gốc/bytes/base64. Credential, header Authorization, config/client objects,
attachments và serialized objects bị loại bỏ ở cả hai mode. Những credential
đã biết qua biến môi trường và các mẫu API key/Bearer/query token được che trong
text. Không bật nội dung chỉ bằng `LANGSMITH_HIDE_INPUTS=false`; dùng cờ riêng
ở trên. File log JSON trên máy vẫn chỉ ghi metadata, không ghi prompt/response.

Mỗi trường text tối đa 12.000 ký tự, mỗi payload content có ngân sách 60.000 ký tự,
danh sách tối đa 40 mục, độ sâu tối đa 10. Nội dung bị giới hạn có `[TRUNCATED]`;
summary và numeric usage được giữ riêng. Các giới hạn này dành cho telemetry,
không thay đổi câu trả lời thật của model. Raw exception message/stack locals
không gửi ra ngoài; giữ error type và các mã chẩn đoán an toàn.

Trace cũ đã bị xóa input tại client không thể lấy lại bằng cách đổi cờ; chỉ các
lượt chạy mới có nội dung. Cấu hình local của đợt sửa 13/11 đã bật mode content
trong `.env` bị Git bỏ qua; mẫu `.env.example` vẫn mặc định false.

## Chẩn đoán phản hồi bị lỗi

Model spans giữ `finish_reason`, `block_reason`, `response_has_text`,
`max_output_tokens`, `error_code`, HTTP status provider khi có và numeric usage,
kể cả khi SDK trả response nhưng validation từ chối. Không suy diễn usage thiếu
là 0. Các loại lỗi chính: `TruncatedModelResponse`, `EmptyModelResponse`,
`BlockedModelResponse`, `IncompleteModelResponse`.

`MAX_TOKENS`/OpenAI `length` được retry tối đa một lần bằng cách tăng output limit,
vẫn nằm trong max calls/deadline/ceiling. Empty/safety block/response không hợp lệ
khác không tự retry. Không nối bản nháp bị cắt vào câu trả lời lần sau.

```yaml
roles:
  visual: {provider: gemini, max_output_tokens: 4096}
budget:
  max_output_tokens: 2048
  max_output_tokens_ceiling: 8192
  truncation_retries: 1
```

Có thể cấu hình `roles.<role>.thinking_level` (`minimal`, `low`, `medium`, `high`)
khi model Gemini tương ứng hỗ trợ. Mặc định không ép thinking level. Chỉ điều
chỉnh khi biết model/capability; role OpenAI/GPU bỏ qua tùy chọn Gemini này.

SDK gửi trace nền; flush khi trace gốc kết thúc có giới hạn một giây. Lỗi telemetry
không đổi kết quả workflow; khi mạng lỗi, trace có thể bị thiếu hoặc đến muộn.

## Kiểm tra kết nối riêng

```powershell
uv run --locked python -m scripts.langsmith_smoke
uv run --locked python -m scripts.langsmith_smoke --content
uv run --locked python -m scripts.langsmith_smoke --summary-only
```

Lệnh gửi trace đồ thị tổng hợp, đọc lại root/graph để xác nhận input/output đúng
mode và credential mẫu bị che. Không gọi Gemini/OpenAI/GPU. Kết quả thành công
có `trace_verified=true`, `redaction_verified=true`, `content_verified=true` khi
chọn content và `model_calls=0`. Lỗi chỉ in mã kiểm tra hoặc tên loại lỗi.

Tài liệu chính thức: [LangGraph tracing](https://docs.langchain.com/langsmith/trace-with-langgraph),
[custom spans](https://docs.langchain.com/langsmith/annotate-code),
[ẩn inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs).
