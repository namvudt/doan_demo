# Hệ thống VQA di tích Việt Nam — LangGraph

Ứng dụng hỏi đáp bằng ảnh, ưu tiên Gemini API và cấu hình provider/model theo từng vai trò. UI Streamlit, CLI và chế độ so sánh dùng chung một workflow LangGraph.

## Cài đặt

Yêu cầu Python 3.12 và uv. Tại thư mục repo:

```powershell
uv sync --locked --group dev
Copy-Item .env.example .env
```

Điền GEMINI_API_KEY trong `.env`; file này được Git bỏ qua. Một key chung đủ cho cấu hình mặc định. Có thể cấu hình key riêng cho role bằng các biến tương ứng trong `.env.example`.

```powershell
uv run streamlit run app.py
```

Phương án chỉ cài dependency runtime: `pip install -r requirements.txt`. File requirements được xuất từ uv.lock; sửa dependency gốc tại pyproject.toml rồi cập nhật lock/export.

## Cách hoạt động

1. Kiểm tra ảnh, câu hỏi và phạm vi.
2. Coordinator trả ExecutionPlan có schema.
3. Visual và Knowledge chạy song song; các kết quả/lỗi được hợp nhất bằng reducer.
4. Generation chỉ chạy khi bật trong cấu hình và có trong kế hoạch, sau khi các expert có kết quả.
5. Aggregator tạo bản nháp nội bộ.
6. Judge đối chiếu ảnh gốc và các đoạn nguồn thực, trả kết quả theo schema.
7. UI công bố câu trả lời khi có đánh giá hợp lệ hoặc thông báo thiếu căn cứ. Bản nháp không được stream công khai.

Các trạng thái nội dung: `reviewed`, `unverified`, `insufficient_evidence`, `out_of_scope`, `failed`. `reviewed` nghĩa là có đánh giá tự động hợp lệ; không phải bảo đảm đáp án đúng tuyệt đối.

Sơ đồ thực: [docs/langgraph.mmd](docs/langgraph.mmd). Chi tiết thay đổi và giới hạn: [docs/implementation-progress.md](docs/implementation-progress.md).

## Cấu hình

Cấu hình runtime là [config/default.yaml](config/default.yaml). `HERITAGE_CONFIG` có thể trỏ tới YAML khác; cấu hình được xác thực trước khi chạy.

- Mặc định mọi role dùng Gemini; sửa `roles.<role>.provider` và `model` để đổi binding.
- Provider được khai báo rõ; không suy từ tiền tố API key.
- Cross-provider fallback là opt-in qua `fallback_providers`; benchmark tắt fallback để giữ điều kiện.
- Giới hạn model calls, timeout, output tokens, retry và concurrency nằm trong cấu hình.
- Mỗi run giữ config snapshot/hash, provider/model/usage và lỗi của từng attempt. Secret không được xuất vào result.
- YAML được đọc khi tạo manager mới; sau khi sửa `.env`, khởi động lại ứng dụng để nạp lại các biến môi trường.
- GPU provider dùng endpoint tương thích API đã khai báo; cần chọn model và kiểm tra khả năng nhận ảnh/JSON trước khi sử dụng. Chưa benchmark GPU.

Các YAML ở thư mục thiết kế của workspace là tài liệu đề xuất rộng hơn, không thay thế trực tiếp schema runtime này.

## Theo dõi LangSmith

Bật `LANGSMITH_TRACING=true`, điền `LANGSMITH_API_KEY` và chọn `LANGSMITH_PROJECT`
trong `.env`, rồi khởi động lại ứng dụng. Trace gồm workflow/node, từng attempt gọi
model và search; giữ thời gian, token thực, provider/model và trạng thái. Nội dung
ảnh/câu hỏi/phản hồi/nguồn được ẩn. Hướng dẫn và lệnh kiểm tra kết nối:
[docs/langsmith.md](docs/langsmith.md).

## CLI và so sánh

```powershell
uv run python benchmark_run.py samples/chua_mot_cot.jpg "Đây là công trình nào?"
uv run python benchmark_run.py samples/chua_mot_cot.jpg "Đây là công trình nào?" --compare --output comparison.json
```

Các lệnh chạy model thật cần key và có thể phát sinh phí. Chế độ `--compare` chỉ báo đầu ra, thời gian, calls và lỗi. Chưa có gold answers/evaluator độc lập, không tính accuracy hoặc kết luận phương pháp thắng. Baseline ReAct hiện là mô phỏng bằng prompt, được ghi rõ `has_tools=false`.

## Kiểm tra offline

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m scripts.export_graph
```

Test mặc định dùng mock và chặn kết nối ra ngoài, không cần key. CI được cấu hình cho Windows và Linux.

Live smoke riêng, chỉ chạy khi chủ động bật:

```powershell
$env:RUN_LIVE_SMOKE = '1'
uv run python -m scripts.live_api_smoke
Remove-Item Env:RUN_LIVE_SMOKE
```

Import `test.py` không còn thực thi request. Các script không tự thay đổi OPENAI_BASE_URL trong môi trường.

## Phạm vi và giới hạn

Bản hiện tại tập trung vào nhận diện và lịch sử công trình. Phiên âm/dịch Hán–Nôm và sáng tác không thuộc đường chạy chính; generation mặc định tắt. OCR chuyên dụng, entity catalog nhiều ứng viên và corpus di sản được tuyển chọn nằm ở giai đoạn tiếp theo.

Search hiện dùng Wikipedia tiếng Việt và đoạn mở đầu có giới hạn. Mỗi nguồn giữ ID/snippet/revision khi có và thời điểm truy cập; timeout/error khác với không có kết quả. Maps URL là liên kết tìm kiếm điều hướng, không phải tọa độ được xác minh hoặc bằng chứng lịch sử.

Chưa có claim-level verifier đầy đủ, debate loop, evaluator độc lập, database hoặc API web mới. Checkpointer có thể được inject và đã kiểm tra serialization bằng InMemorySaver; mặc định không lưu checkpoint giữa các lần chạy và chưa hỗ trợ phục hồi sau restart.
