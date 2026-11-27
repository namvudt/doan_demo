# Kết quả sửa luồng và kiểm thử VietTravelVQA

Ngày kiểm tra: 27/11/2026. Nhánh làm việc: `eval/hanoi-small-batch`.

Đã sửa các lỗi hợp đồng Verifier, quản lý thực thể, truy xuất theo quan hệ, bằng chứng đếm và chẩn đoán. Kết quả chạy thật cho thấy có cải thiện về căn cứ và khả năng từ chối đúng lý do; hệ thống vẫn còn lỗi nhận diện và thiếu nguồn, chưa giải đúng toàn bộ sáu câu.

## Thay đổi đã triển khai

- Verifier phải có `claims` và `slot_assessments`. Slot kiến thức/visual báo `complete` phải có claim supported tương ứng; phản hồi sai được sửa tối đa một lần theo cấu hình, lỗi lặp lại trả lỗi kiểm chứng. Lưu output đề xuất, lỗi hợp đồng và claim sau gate trong `review_diagnostics`.
- Loại quốc gia, đơn vị hành chính và giá trị đáp án khỏi ứng viên nhận diện công trình. Tách chủ thể đã nêu trong câu hỏi khỏi việc xác nhận ảnh; catalog nhãn Việt Nam kế thừa Hà Nội, không chứa đáp án benchmark. Giữ hai thực thể khác nhau nếu chưa có cơ sở đồng nhất.
- Quan sát ảnh trước truy xuất. Có tối đa một lượt đối chiếu bất đồng nhận diện, không tự nâng xác nhận bằng việc các agent lặp lại tên của nhau. Không ép chọn tên đúng theo metadata benchmark.
- Truy xuất theo chủ thể và quan hệ; ưu tiên đoạn có thông tin cần hỏi, bỏ query đã chạy trong recovery và giới hạn HTTP. Nguồn chỉ nhắc tên không mặc nhiên đủ để trả lời.
- Câu đếm có inventory từng instance, loại vật thể, mức xác định và box có tên tọa độ. Backend chặn trùng instance, box mâu thuẫn, loại chưa chắc và tổng không khớp; không tự đảo trục.
- Quotation quốc gia phải chứng minh quan hệ của đúng chủ thể. Không dùng quốc tịch của người cách mạng làm bằng chứng tỉnh thuộc quốc gia nào. Quy tắc có thể điều chỉnh bằng `source_relation_rules`; vẫn cần đánh giá ngữ nghĩa ngoài các cấu trúc được hỗ trợ.
- Giữ điều kiện “gần nhất” khi Coordinator viết lại câu hỏi. Thiếu tập so sánh/khu vực thì hỏi phạm vi; nguồn chỉ nói cảnh quan quanh đó không hoàn thành câu hỏi nhiều bước.
- Bổ sung reason codes, dữ liệu chẩn đoán qua API/SSE/steps và LangSmith, nhãn lý do trên Streamlit. Luồng hỏi bổ sung sử dụng phạm vi người dùng đã cung cấp, giữ câu hỏi gốc và không tự coi phạm vi là bằng chứng địa lý.

## Chạy thật

Model: Gemini `gemini-3.5-flash`; profile `config/evaluation/viettravel-adapted.yaml`. `small-v2` chạy đủ sáu câu validation cũ; sau khi đọc quotation, `relations-v3` chạy lại hai câu quốc gia và câu gần nhất. Kết quả v1/v2 được giữ nguyên để đối chiếu. Lượt sửa continuation cuối cùng được kiểm thử offline, chưa chạy cuộc hội thoại tiếp nối bằng model thật.

| Câu | Trước sửa (v1) | Kết quả mới nhất | Nhận xét khi đọc bằng chứng |
|---|---|---|---|
| Lý Sơn thuộc quốc gia nào? | Hỏi xác nhận | v3: answered, Việt Nam | Quotation trực tiếp: “Lý Sơn là một đặc khu thuộc tỉnh Quảng Ngãi, Việt Nam.” |
| Di tích trong ảnh xếp hạng nào? | Hỏi xác nhận | v2: answered có điều kiện về Chùa Keo | **Sai chủ thể** so với metadata Chùa Bút Tháp. Không tính đúng chỉ vì tên hạng di tích trùng đáp án. |
| Bao nhiêu cột cổng chính? | answered, 2 | v2: answered, 2 | Hai instance confirmed, hai vùng ảnh phù hợp; khớp nhãn “Hai”. |
| Bao nhiêu cột cờ? | answered, 2; nhãn “Một” | v2: insufficient_evidence | Hai thanh trên mái chưa xác định là cột cờ; phát hiện observation box đảo trục. Không khẳng định số 0 hoặc 2. Nhãn “Một” chưa có box chuẩn để kiểm định. |
| Sơn La thuộc quốc gia nào? | insufficient_evidence | v3: partial | Nhận diện công trình có điều kiện; claim quốc gia bị chặn vì quotation không chứng minh quan hệ. Knowledge gặp 504, có một vòng recovery. |
| Địa điểm gần nhất thuộc loại gì? | Hỏi xác nhận danh tính | v3: needs_clarification về phạm vi | Giữ điều kiện gần nhất, không trả rừng ngập mặn thay đáp án. Còn bất định nhận diện và thiếu căn cứ so sánh. |

`small-v2` ban đầu có 5 trạng thái answered, nhưng hai câu quốc gia dùng quotation yếu và câu Mũi Cà Mau bỏ điều kiện gần nhất. Vì vậy không dùng số answered đó để công bố độ chính xác. Gate bổ sung của v3 đã chặn hoặc yêu cầu bổ sung các quan hệ chưa được chứng minh.

| Job | Case hoàn tất | Request provider | Token có usage | Lỗi provider |
|---|---:|---:|---:|---|
| `viettravel-validation-small-v2` | 6/6 | 29 | 117.747 | 1 lỗi 503, phục hồi bằng fallback sau chờ |
| `viettravel-validation-relations-v3` | 3/3 | 17 | 68.801 | 1 lỗi 504 ở Knowledge; được giữ trong errors của câu Sơn La |

Cấu hình giãn 30 giây giữa request, 20 giây giữa case; không có lỗi 429 trong hai job. Không khởi động job toàn bộ test. `technical_failures=0` trong summary chỉ đếm kết quả run failed/unverified, **không có nghĩa mọi agent đều thành công**: câu Sơn La vẫn có lỗi Knowledge 504 và không hoàn thành phần quốc gia.

## Kiểm thử và giới hạn

**450/450 kiểm thử offline đạt**, 0 lỗi, 0 bỏ qua trên Windows/Python 3.12. Bao gồm API/SSE, Streamlit, worker, hợp đồng JSON, continuation, entity, retrieval, quote gate, count grounding và cơ chế pacing/fallback. Ruff check, Ruff format và repository check đều đạt. Kết quả cuối cùng được lưu local tại `reports/evaluation/viettravel-final-offline-tests.xml`. Các bài thử model thật không thay thế kiểm thử bằng đáp án và ảnh được chuyên gia duyệt.

Các câu validation này đã được xem và dùng để điều chỉnh hệ thống. Đây là kiểm thử hồi quy phát triển, không phải accuracy độc lập hay metric chính thức của benchmark. Bộ graph có câu “gần nhất” thiếu tập so sánh; nhãn cột cờ chưa có annotation vật thể. Không sửa nhãn hoặc đưa câu trả lời chuẩn vào prompt/catalog.

Các hạn chế còn quan sát được: nhận diện nhầm Bút Tháp thành Keo; observation tuple đôi khi vẫn đảo x/y dù đã có named boxes và gate phát hiện; thiếu nguồn trực tiếp cho quan hệ tỉnh → quốc gia ở câu Sơn La. `reviewed`/`answered` vẫn là trạng thái quy trình tự động, không bảo đảm đúng lịch sử hoặc đúng danh tính ảnh.

Bản [JSON tóm tắt để chia sẻ](evaluation/viettravel-regression-summary.json) được đưa lên Git cùng báo cáo này, gồm kết quả sáu câu, số request/token, lỗi provider và các giới hạn đánh giá. Không chứa credential, ảnh, đường dẫn máy cá nhân hoặc trace thô.

Artifact local (không đưa dữ liệu ảnh, khóa hoặc log thô lên Git):

- `reports/evaluation/viettravel-regression-comparison.json`: sáu kết quả mới nhất và baseline.
- `reports/evaluation/jobs/viettravel-validation-small-v2/`: full run sáu câu.
- `reports/evaluation/jobs/viettravel-validation-relations-v3/`: kiểm tra lại ba câu quan hệ.
- `shards/*/predictions.json`: plan, expert reports, evidence, claims, gate errors và diagnostics.
- `shards/*/predictions.run.json`: thời điểm request, HTTP status, pacing và credential slot, không có giá trị khóa.

Hướng dẫn cấu hình và tái tạo job: [viettravel-evaluation-job.md](viettravel-evaluation-job.md).
