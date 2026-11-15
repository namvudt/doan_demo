# Kế hoạch sửa nhận diện và phản hồi quá thận trọng

## Vấn đề đã quan sát

Sample Chùa Hương ở lần chạy gần nhất có ảnh đọc được, coordinator và visual cùng chọn Thiên Trù, 9/10 nhận định được hỗ trợ. Tuy nhiên Verifier tự yêu cầu biển tên Quốc ngữ để xác nhận tuyệt đối, dù câu hỏi là “có thể là”. `identity_resolved` chỉ biểu thị sự đồng thuận giữa agent; trạng thái trả lời lại phụ thuộc vào claim nhận diện. Nhãn sample không được truyền vào workflow. Đây chưa phải bộ dữ liệu có đáp án được chuyên gia duyệt.

## Thứ tự thực hiện

1. **P0 — Hợp đồng nhận diện:** thêm kết quả `recognition` độc lập với `answer_status`, gồm `recognized`, `probable`, `ambiguous`, `unrecognized`; liên kết ứng viên với các quan sát ảnh có ID thật. Giữ đọc được kết quả cũ. Sự đồng thuận giữa agent không tự chứng minh danh tính.
2. **P0 — Kiểm chứng theo mức nhận diện:** Verifier đánh giá riêng liên kết ảnh–ứng viên; backend kiểm tra ID, tính đồng thuận và cơ sở đặc trưng. Nhận diện `probable` được diễn đạt “có thể là”; không cần OCR/biển tên khi đặc điểm kiến trúc và bố cục có cơ sở. Không tự chuyển claim bị bác bỏ thành đúng. Lịch sử, niên đại, vật liệu và Hán–Nôm giữ nguyên kiểm soát nguồn.
3. **P0 — Quyết định trả lời/hỏi thêm:** chỉ hỏi khi thiếu định danh hoặc ảnh không đọc được thực sự chặn một phần câu hỏi. Một ứng viên có cơ sở được trả lời có điều kiện; thiếu tư liệu lịch sử không buộc người dùng xác nhận lại tên. Câu hỏi gốc phải được giữ trong payload đánh giá, không bị slot do coordinator viết lại nâng thành yêu cầu chắc chắn tuyệt đối.
4. **P1 — Ngữ cảnh minh bạch:** thêm gợi ý địa điểm tùy chọn cho API/Streamlit. Sample có chế độ nhận diện độc lập mặc định và tùy chọn dùng nhãn làm gợi ý; ghi nguồn gợi ý, không coi nhãn/file name hoặc lời người dùng là đáp án chuẩn. Gợi ý không được đưa vào bước quan sát ảnh độc lập. Hash, continuation và cache phải phân biệt ngữ cảnh.
5. **P1 — Trải nghiệm/quan sát:** API, SSE, Swagger và UI cùng hiển thị trạng thái nhận diện, cơ sở ảnh, giới hạn và thông tin gợi ý. Nội dung nguồn được diễn đạt có điều kiện khi danh tính mới là khả năng; không trình bày phần chưa đủ căn cứ như yêu cầu xác nhận bắt buộc.
6. **P1 — Kiểm thử:** kiểm thử hồi quy ảnh không có biển tên nhưng có đặc trưng, đặc điểm chung chung, nhiều ứng viên, ID giả, gợi ý sai, ảnh không đọc được, thiếu nguồn lịch sử, tiếp tục hội thoại và kết quả cũ. Chạy kiểm tra tĩnh, bộ test offline, API PostgreSQL và một lần sample thật có giới hạn; lưu báo cáo runtime vào thư mục bị ignore.

## Tiêu chí nghiệm thu

- Nhận diện có bằng chứng được trả lời theo mức chắc chắn; không hạ kiểm soát nguồn để đạt `answered`.
- Chỉ tên ứng viên, nhãn sample hoặc sự đồng thuận agent không đủ để tạo nhận diện có cơ sở.
- Mọi evidence ID công khai đều do backend đăng ký; không có tỷ lệ tự tin tự tạo.
- API và Streamlit dùng chung quyết định; luồng cũ và kết quả lưu cũ vẫn đọc được.
- Báo cáo phân biệt kết quả mock với lần gọi Gemini thật; không coi một sample là chứng minh độ chính xác toàn hệ thống.

## Cấu hình và hoàn tác

Chính sách nhận diện nằm trong `accuracy.recognition`; không hardcode tên Chùa Hương/Thiên Trù vào quyết định. Có thể tắt phần nhận diện mới, hoặc tắt toàn bộ profile bằng `HERITAGE_ACCURACY_ENABLED=false`. Không sửa `.env`, không thay service API đang chạy và không push trong tác vụ này.

## Kết quả thực hiện — 15/11/2026

Đã triển khai P0 và P1 trong phạm vi trên:

- `core/recognition.py`, `core/evidence.py`: hợp đồng nhận diện, ánh xạ quan sát, kiểm tra ID/basis/ứng viên, lọc giải thích chứa dữ kiện cần nguồn. Mặc định giới hạn `probable`, cấu hình được bằng YAML.
- `workflow/accuracy.py`, `workflow/service.py`: nhận diện có điều kiện độc lập với claim tuyệt đối; giữ câu hỏi gốc, xử lý quan hệ quần thể/thành phần, trả phần có căn cứ và chỉ hỏi bổ sung có mục đích.
- API, Store/worker, HTTP adapter và Streamlit: ngữ cảnh gợi ý có provenance, lựa chọn ứng viên có cấu trúc, lưu qua review/retry/continuation; hash/cache phù hợp và hiển thị cơ sở nhận diện. Không cần migration mới cho các trường JSON bổ sung.
- Swagger/Postman và tài liệu đã đồng bộ. Scorer yêu cầu con người duyệt nhận diện riêng, không lấy model tự đánh giá làm độ đúng.

Kiểm tra: **228 tests offline đạt**, **45 tests PostgreSQL đạt** trên database/container riêng đã dọn, **86/86 trường hợp HTTP** phủ **37/37 operations**. Postman có 40 requests. Ruff check/format và `git diff --check` đạt; quét 67 file thay đổi/thêm không thấy mẫu credential thật.

Sample Chùa Hương qua Streamlit AppTest và Gemini thật, **không dùng nhãn sample**:
`recognition=probable`, `answer_status=answered`, không có clarification chờ, 0 lỗi UI.
Có 6 ID quan sát hỗ trợ nhận diện; nội dung nguồn được trình bày có điều kiện.
Thời gian **103,53 giây**, 6 lượt gọi gồm một lần thử lại do provider 503; không tuyên bố cải thiện tốc độ. Lần trước `partial`, 54,61 giây và cũng không còn clarification chờ. Bản ghi thật đã được kiểm tra lại với gate cuối cùng mà không gọi thêm model.

Báo cáo chi tiết: `reports/chua-huong-recognition/report.md`, `result.json`, `validation.json` (runtime bị gitignore). Độ đúng lịch sử, độ phân biệt với di tích tương tự và tỷ lệ từ chối sai trên tập rộng vẫn cần bộ gold và người duyệt; chưa có số đo chất lượng tổng thể để công bố.

Hướng dẫn cấu hình, API và cách diễn đạt trạng thái: [accuracy-profile.md](accuracy-profile.md).
