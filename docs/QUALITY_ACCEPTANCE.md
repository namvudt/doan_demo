# Nghiệm thu AI, bộ ca người duyệt và cache truy xuất

Các kiểm thử logic/API không xác nhận độ đúng lịch sử. Backend đã có công cụ
chấm bằng nhãn người duyệt; bộ ca repository vẫn là bản dự thảo. Không tự điền
reviewer, đáp án chuẩn hay quyền ảnh từ tên sample hoặc kết quả model.

## Xuất bộ ca để người dùng duyệt

Từ thư mục repository:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_review_pack export --output .api-demo/review-packs/review-01
```

Công cụ sao chép nguyên byte bốn ảnh thật đi kèm repo, xuất 32 câu hỏi và thay
tên ảnh/ca trong thư mục `blind/`. Thư mục `operator/` giữ ánh xạ nguồn gốc và
SHA256. Nó không chứa nhãn gold đã duyệt. Thư mục đích phải rỗng để tránh ghi
đè công sức người duyệt.

Người duyệt bắt đầu từ `blind/manifest.json`, kiểm tra ảnh và tư liệu trước khi
xem dự đoán model. Điền reviewer, ngày duyệt, nguồn/quyền ảnh, answerability,
accepted_answers và nguồn có URL/content_hash cho các nhận định lịch sử. Đặt
split `dev` hoặc `test`; cùng image_family/entity_group không được nằm ở cả hai
split. Có thể chỉnh entity_group sau khi thực sự nhận diện; câu hỏi, byte ảnh,
image_family và các slot phải giữ nguyên nếu muốn tái sử dụng dự đoán đã chạy.

Sau khi lưu bản đã duyệt:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_review_pack finalize --pack .api-demo/review-packs/review-01 --reviewed path/to/manifest-reviewed.json --predictions .api-demo/reports/live-review-01/predictions.json
```

`finalize` kiểm tra toàn bộ contract gold, split và hash ảnh. Dự đoán draft
chỉ được gắn `case_hash` mới khi ảnh/câu hỏi/slot trùng đúng bản gốc. Hash cũ
được giữ ở `original_case_hash`; không gọi lại model hoặc sửa nội dung dự đoán.
Đây là gắn metadata gold do người dùng nhập vào cùng một input đã chạy, không
phải chứng nhận model đã trả lời đúng.

Trong `reviewed/`, người duyệt tiếp tục điền `judgments-template.json`: đúng/sai
cho từng claim được hiển thị, verdict cho từng slot, và nhãn nhận diện nếu model
đưa ra `probable/recognized`. Reviewer/ngày duyệt và các giá trị correctness
trong template đều để trống. Sau đó mới chấm:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate score .api-demo/review-packs/review-01/reviewed/prediction-manifest.json .api-demo/review-packs/review-01/reviewed/predictions.json path/to/judgments-completed.json --output .api-demo/reports/quality-reviewed.json
```

Demo, nhãn chưa duyệt, ảnh/câu hỏi bị thay, judgment lỗi thời hoặc thiếu nguồn
phiên bản đều bị từ chối. Kết quả một tập nhỏ chưa đủ chứng minh chất lượng trên
di tích hoặc điều kiện ảnh chưa xuất hiện trong tập kiểm tra.

## Nghiệm thu model thật có ngân sách

Chạy trên stack live riêng đã được cấu hình server. Tool chỉ chấp nhận origin
HTTP loopback và yêu cầu `--live` tường minh. Nó không đọc `.env`; bootstrap hoặc
session có sẵn chỉ được lấy từ tên biến môi trường được chỉ định, không từ
tham số token/plaintext và không ghi token vào report.

```powershell
.\.venv\Scripts\python.exe -m scripts.live_acceptance --live --url http://127.0.0.1:8002 --manifest .api-demo/review-packs/review-01/blind/manifest.json --allow-draft --max-cases 2 --max-model-calls 24 --output .api-demo/reports/live-review-01
```

Server phải quảng bá giới hạn đã thực thi tại
`capabilities.accuracy.budget.max_llm_calls`. Tool kiểm tra tổng số ca × giới hạn
mỗi run trước khi tạo session/run; trước mỗi run tiếp theo nó tiếp tục kiểm tra
số attempts đã quan sát + giới hạn run mới. Không tạo thêm run khi thiếu ngân
sách. Server vẫn cần cấu hình quota ngày, deadline và retry phù hợp; tool
không sửa quota hoặc credential server.

Tool ưu tiên các image_family khác nhau, upload dưới tên trung tính, không đưa
nhãn file/sample vào `location_hint`. Report gồm prediction hash, tổng attempts,
trạng thái nhận diện/câu trả lời, latency queue/node/total, idempotency và cursor
SSE. Response text được lưu trong prediction local để người dùng duyệt; report
tóm tắt không ghi token, API key hoặc prompt nội bộ. Thư mục output phải rỗng.

Nếu model thực sự hỏi bổ sung, có thể truyền `--clarification-answer` chứa thông
tin người dùng cung cấp. Tool chỉ gửi khi có pending hợp lệ và còn ngân sách cho
một run con; nó kiểm tra revision, replay idempotency, parent bất biến và lineage.
Không có pending thì report ghi rõ không quan sát được transition; không tạo
pending giả hoặc cho rằng UI fixture là bằng chứng model thật.

Với hai ca và một continuation, có thể cần trần 36 thay vì 24 khi server đặt
12 attempts/run. Giới hạn 24 vẫn được giữ cứng ở bước admission: tool sẽ dừng
thay vì tự nới trần. Người vận hành chọn số ca/trần trước khi chạy. Các run còn
đang chạy được yêu cầu cancel khi tool lỗi; phiên khách do tool tạo được thu hồi.

## Đo độ trễ và cache nguồn

`summary.json` có p50/p95 nearest-rank cho queue wait, từng node và tổng thời
gian từ các run đã quan sát. Nó ghi cỡ mẫu và nhắc rằng vài ca acceptance không
phải benchmark production. Chạy lại cùng tập với cấu hình cố định để so sánh;
không lấy thời gian demo làm độ trễ của Gemini/OpenAI thật.

`SharedRetrievalCache` dùng SQLite WAL, transaction cho nhiều process, TTL,
giới hạn số entry và tổng byte payload. Dung lượng file SQLite/WAL có phần
overhead riêng; cache có thể xóa/tạo lại, không là nguồn sự thật. Payload chỉ
chứa SourceRecord công khai đã whitelist; không lưu query echo, auth header,
URL chứa credential/token, model output, draft source hoặc kết quả lỗi/rỗng.

`CachedSearchEngine` chỉ bọc `search_heritage`, không bọc
`KnowledgeAgent.retrieve` vì bước này còn gọi LLM. Key gồm hash câu hỏi/thực thể,
namespace config hash và revision của corpus/entity/nguồn đã xuất bản. Callback
revision được đọc trước mỗi hit và kiểm tra lại; sửa/withdraw nguồn làm cache
cũ không còn được dùng ngay cả khi TTL chưa hết. Lỗi cache bỏ qua cache và gọi
retriever; lỗi đọc revision không được dùng làm lý do trả dữ liệu stale.

Trong mỗi run, ToolExecutor vẫn ghi ledger và budget riêng. Cache nguồn không
bỏ qua Verifier, không nâng nhãn xác minh và không dùng lại suy luận LLM giữa
các run. Runtime kết hợp revision DB với SHA256 của corpus/entity file để
tránh reuse nội dung đã bị rút hoặc thay ngoài DB.

## Câu hỏi trộn nhiều ý

Scope mới giữ câu hỏi gốc trong result/fingerprint, tách phần được hỗ trợ cho
coordinator/experts/Verifier và thêm lời từ chối rõ cho phần ngoài khả năng.
Ví dụ mô tả kiến trúc kèm yêu cầu đọc Hán–Nôm vẫn xử lý phần kiến trúc; nếu có
căn cứ thì `answer_status=partial`. Câu chỉ yêu cầu phiên đọc Hán–Nôm vẫn dừng
ngoài phạm vi và không gọi model. Evidence/quotation/risk gates vẫn giữ nguyên.
