# Kết quả thử Gemini với 3 câu VietTravelVQA

Ngày chạy: **16/11/2026**. Nhánh: `eval/hanoi-small-batch`.

Đây là **đầu ra live để tìm lỗi**, chưa phải phép đo accuracy có người duyệt. Chạy một lần mỗi câu, giữ nguyên cả kết quả chưa tốt; không chạy lại để chọn đáp án đẹp.

## Điều kiện chạy

- VietTravelVQA v3, revision `75d72d93f12f40756e5dfa0775236d3d78483fa4`, 3 câu `original` từ test split, trên 2 ảnh. Manifest trong dự án vẫn là `draft`.
- Model thực tế của mọi role: `gemini-3.5-flash`, lấy từ cấu hình hiện có. Không đổi model/provider để tránh quota.
- Luồng LangGraph bằng chứng hiện có, OCR/retrieval vẫn được phép chạy. Các lần chạy độc lập, không chia sẻ kết quả nhận diện giữa các câu.
- Request generation được tuần tự hóa, khoảng cách admission nhỏ nhất đo theo wall clock khoảng **30,0 giây**; khoảng nghỉ giữa các case **60,9 và 61,0 giây**. Graph giữ 3 workers để streaming hoạt động.
- Tổng **14 request generation**, tất cả thành công ở cấp provider; **0 lỗi 429**, không fallback. Usage ghi nhận tổng 49.190 tokens, chưa quy đổi thành tiền.

## Bảng kết quả thực tế

| Case | Câu hỏi | Đầu ra chính | Trạng thái hệ thống | Lượt model | Thời gian/case |
| --- | --- | --- | --- | ---: | ---: |
| `VN_003358_q3` | Ngọn tháp màu đỏ trong ảnh thuộc ngôi chùa nào? | “Có thể là Chùa Trấn Quốc”, có quan sát ảnh, không hỏi thêm | `answered`, nhận diện `probable` | 4 | 110,25 giây |
| `VN_002260_q2` | Mặt tiền nhà thờ có bao nhiêu cánh cửa ra vào chính có vòm? | “3 lối cửa ra vào chính dạng vòm” | `answered` | 5 | 154,45 giây |
| `VN_003358_q4` | Ngôi chùa Chấn Quốc trong ảnh được biết đến với ý nghĩa văn hóa và lịch sử nổi bật nào? | Trả một phần tư liệu có 2 nguồn; vẫn yêu cầu ảnh gần/rõ hơn | `needs_clarification`; slot lịch sử `partial` | 5 | 141,33 giây |

Hai đáp án đầu khớp tên/số lượng tham chiếu upstream, nhưng chưa thể kết luận toàn bộ bằng chứng/grounding đúng. Câu cuối giữ nguyên lỗi gõ “Chấn Quốc” trong dataset. Thời gian trên gồm chờ điều tiết trong case, chưa gồm khoảng nghỉ giữa các case; không dùng để so tốc độ với cấu hình không pacing.

Phân bổ request: coordinator 3, visual 4, aggregator 3, judge 3, knowledge 1. Hai câu đầu không gọi Knowledge. Câu đếm cửa dùng thêm crop/OCR, vì vậy có 5 request thay vì 4.

## Các lỗi/điểm cần cải thiện đã quan sát

### P0 — Nhận diện bị hạ vì `readability` không nhất quán

Câu đầu và câu lịch sử dùng **cùng ảnh, cùng hash**, thông số ảnh 1280×960 và quality flags rỗng. Tuy vậy:

| Trường | Câu nhận diện | Câu lịch sử |
| --- | --- | --- |
| Visual `readability` | `adequate` | `unreadable` |
| Visual candidate | Chùa Trấn Quốc | Chùa Trấn Quốc |
| Verifier assessment | `probable` | `probable` |
| Kết quả sau backend gate | `probable` | `unrecognized` |
| Gate reason | Không có | `recognition_image_unreadable` |

Như vậy, có căn cứ cụ thể để giải thích lần hỏi lại: Visual gắn nhãn `unreadable`, backend chặn nhận diện và tạo clarification `image_unreadable`, dù Visual vẫn mô tả nhiều chi tiết và Verifier đề xuất probable. Quality flags rỗng không tự chứng minh ảnh luôn trả lời được; nhưng hai kết quả cho cùng ảnh là dấu hiệu cần kiểm tra định nghĩa readability và mức phụ thuộc câu hỏi/lượt model.

Đề xuất tiếp theo: tách khả năng nhìn đặc điểm công trình, đọc chữ và trả lời lịch sử; thiếu tư liệu lịch sử không tự chuyển thành ảnh không đọc được. Bổ sung regression cùng ảnh với câu hỏi nhận diện/lịch sử và lỗi gõ. Cần duyệt sự phù hợp của nhãn ảnh; không đơn giản bỏ gate để nâng mọi ảnh lên probable.

### P0 — Tên đúng chưa đảm bảo vùng ảnh đúng

Kiểm tra sơ bộ ảnh và box trả về ở câu nhận diện: box được gắn với ao sen nằm phía trên/bên phải, còn box hàng cau lại nằm vùng thấp của ảnh. Đây là dấu hiệu grounding sai dù tên công trình khớp tham chiếu. Chưa có box chuẩn hoặc người duyệt độc lập để tính IoU.

Đề xuất: gán box chuẩn cho một nhóm nhỏ, kiểm tra quy ước tọa độ/resize/orientation và chấm grounding riêng. Không dùng agreement giữa Visual và Verifier làm bằng chứng rằng box đã đúng.

### P1 — Truy hồi và mức đầy đủ câu trả lời lịch sử

Câu lịch sử thu được 2 nguồn Wikipedia, lưu URL/revision/hash/đoạn trích. Đầu ra nghiêng về trùng tu, tháp và cảnh quan; hệ thống vẫn đánh dấu `incomplete_answer`. Đáp án tham chiếu upstream chưa được duyệt nên chưa dùng làm gold, và số lượng nguồn không đủ để kết luận lịch sử đúng.

Đề xuất: duyệt các fact thực sự cần cho câu hỏi về ý nghĩa lịch sử/văn hóa, kiểm tra retrieval có lấy đúng đoạn hỗ trợ các fact đó và đánh giá riêng từng ý. Giữ khả năng trả lời phần có nguồn, tránh yêu cầu ảnh mới khi điều thiếu là tư liệu.

### P1 — Cân đối tool call và thời gian

Câu đếm cửa gọi crop và OCR dù yêu cầu chính là đếm. Cần xem điều kiện kích hoạt OCR có đem lại thông tin cần thiết hay chỉ tăng số request. Chưa đủ dữ liệu để loại OCR khỏi luồng; benchmark tiếp theo nên so riêng có/không OCR trên câu quan sát có chữ và không có chữ.

## Artifact và giới hạn kết luận

Artifact local trong `reports/evaluation/viettravel-smoke-20261116/` (gitignore):

- `predictions.json`: toàn bộ đầu ra, stages, evidence, claim, nguồn, request metadata và usage.
- `predictions.run.json`: trạng thái batch và thời điểm admission từng request.
- `summary.json`: bảng tóm tắt được tính từ artifact thật.
- `code-snapshot.json`: hash 33 file code/config tại lượt chạy, base commit và trạng thái worktree chưa commit. Guard từ chối resume khi thiếu checkpoint được bổ sung sau lượt này; không chạy lại model vì thay đổi đó.
- `diagnostics/`: ghi nhận lần khởi động ban đầu bị kẹt vì graph chỉ một worker; đã tái hiện bằng demo, sửa profile và chạy lại trước đợt live ở bảng trên.

Lần này không có 429, nhưng không chứng minh đã giải quyết mọi giới hạn RPM/TPM/RPD. Ba câu trên hai ảnh chưa đại diện cho Hà Nội, chưa có ảnh suy giảm hay hội thoại bổ sung được chấm độc lập. Không báo “2/3 chính xác” từ trạng thái `answered` của hệ thống.

Lệnh chạy lại/tiếp tục và cấu hình nằm ở [hướng dẫn evaluation nhỏ](evaluation-smoke.md). Chưa mở rộng số câu hoặc gọi model thêm sau khi hoàn tất batch này.

Kiểm thử phần mềm sau chỉnh sửa: **260 tests đạt**, Ruff check/format đạt. Có test cho giãn request đồng thời, dừng khi 429, RetryInfo/Retry-After, ngân sách, resume, tiến trình ngắt giữa case và graph streaming với profile evaluation. Đây là kiểm tra tính đúng của phần mềm, tách biệt với chất lượng lịch sử/grounding chưa được chấm gold.
