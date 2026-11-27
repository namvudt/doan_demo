# Kế hoạch sửa nhận diện và phản hồi quá thận trọng

## Vấn đề đã quan sát

Verifier có thể đòi biển tên để xác nhận tuyệt đối dù câu hỏi chỉ là “có thể là”.
`identity_resolved` biểu thị sự đồng thuận giữa agent, chưa tự chứng minh nhận
diện đúng. Vì vậy kết quả nhận diện cần độc lập với độ đầy đủ của câu trả lời
và mọi mức nhận diện cần có cơ sở ảnh được backend kiểm tra.

## Thứ tự thực hiện

1. **P0 — Hợp đồng nhận diện:** thêm kết quả `recognition` độc lập với `answer_status`, gồm `recognized`, `probable`, `ambiguous`, `unrecognized`; liên kết ứng viên với các quan sát ảnh có ID thật. Giữ đọc được kết quả cũ. Sự đồng thuận giữa agent không tự chứng minh danh tính.
2. **P0 — Kiểm chứng theo mức nhận diện:** Verifier đánh giá riêng liên kết ảnh–ứng viên; backend kiểm tra ID, tính đồng thuận và cơ sở đặc trưng. Nhận diện `probable` được diễn đạt “có thể là”; không cần OCR/biển tên khi đặc điểm kiến trúc và bố cục có cơ sở. Không tự chuyển claim bị bác bỏ thành đúng. Lịch sử, niên đại, vật liệu và Hán–Nôm giữ nguyên kiểm soát nguồn.
3. **P0 — Quyết định trả lời/hỏi thêm:** chỉ hỏi khi thiếu định danh hoặc ảnh không đọc được thực sự chặn một phần câu hỏi. Một ứng viên có cơ sở được trả lời có điều kiện; thiếu tư liệu lịch sử không buộc người dùng xác nhận lại tên. Câu hỏi gốc phải được giữ trong payload đánh giá, không bị slot do coordinator viết lại nâng thành yêu cầu chắc chắn tuyệt đối.
4. **P1 — Ngữ cảnh minh bạch:** gợi ý địa điểm tùy chọn cho API có provenance; không coi nhãn/file name hoặc lời người dùng là đáp án chuẩn. Gợi ý không đi vào bước quan sát ảnh độc lập. Hash, continuation và cache phải phân biệt ngữ cảnh.
5. **P1 — Quan sát:** API, SSE và Swagger công bố trạng thái nhận diện, cơ sở ảnh, giới hạn và thông tin gợi ý. Nội dung nguồn được diễn đạt có điều kiện khi danh tính mới là khả năng; không biến phần chưa đủ căn cứ thành yêu cầu xác nhận bắt buộc.
6. **P1 — Kiểm thử:** hồi quy ảnh có đặc trưng nhưng không có biển tên, đặc điểm chung chung, nhiều ứng viên, ID giả, gợi ý sai, ảnh không đọc được, thiếu nguồn lịch sử, continuation và kết quả cũ. Chạy kiểm tra tĩnh, offline và PostgreSQL riêng; lưu báo cáo runtime trong vùng Git bỏ qua.

## Tiêu chí nghiệm thu

- Nhận diện có bằng chứng được trả lời theo mức chắc chắn; không hạ kiểm soát nguồn để đạt `answered`.
- Chỉ tên ứng viên, nhãn sample hoặc sự đồng thuận agent không đủ để tạo nhận diện có cơ sở.
- Mọi evidence ID công khai đều do backend đăng ký; không có tỷ lệ tự tin tự tạo.
- API và worker dùng chung quyết định; luồng cũ và kết quả lưu cũ vẫn đọc được.
- Báo cáo phân biệt kết quả mock với lần gọi Gemini thật; không coi một sample là chứng minh độ chính xác toàn hệ thống.

## Cấu hình và hoàn tác

Chính sách nhận diện nằm trong `accuracy.recognition`; không hardcode tên di tích
vào quyết định. Có thể tắt phần nhận diện mới, hoặc tắt toàn bộ profile bằng
`HERITAGE_ACCURACY_ENABLED=false`. Giữ migration và adapter kết quả cũ khi tắt.

## Các phần hiện thực

Đã triển khai P0 và P1 trong phạm vi trên:

- `core/recognition.py`, `core/evidence.py`: hợp đồng nhận diện, ánh xạ quan sát, kiểm tra ID/basis/ứng viên, lọc giải thích chứa dữ kiện cần nguồn. Mặc định giới hạn `probable`, cấu hình được bằng YAML.
- `workflow/accuracy.py`, `workflow/service.py`: nhận diện có điều kiện độc lập với claim tuyệt đối; giữ câu hỏi gốc, xử lý quan hệ quần thể/thành phần, trả phần có căn cứ và chỉ hỏi bổ sung có mục đích.
- API và Store/worker: ngữ cảnh gợi ý có provenance, lựa chọn ứng viên có cấu trúc, lưu qua review/retry/continuation; hash/cache phân biệt input. Không cần migration riêng cho các trường JSON bổ sung.
- Swagger/Postman và tài liệu đã đồng bộ. Scorer yêu cầu con người duyệt nhận diện riêng, không lấy model tự đánh giá làm độ đúng.

Validation của nhánh backend được ghi ở [BACKEND_ISOLATION.md](BACKEND_ISOLATION.md).
Độ đúng lịch sử, khả năng phân biệt di tích tương tự và tỷ lệ từ chối sai trên
tập rộng vẫn cần bộ gold và người duyệt; test phần mềm không thay thế các nhãn này.

Hướng dẫn cấu hình, API và cách diễn đạt trạng thái: [accuracy-profile.md](accuracy-profile.md).
