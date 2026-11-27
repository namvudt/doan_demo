# Bộ test case hệ thống hỏi đáp di sản bằng ảnh

Phạm vi: profile `hanoi-evidence`, LangGraph, Gemini, API/SSE và Streamlit. Đối chiếu với commit `7e4bc89`. Tài liệu này đề xuất **60 test case**, chưa phải bảng kết quả đã chạy. Một số hành vi đã có test tự động; cần bổ sung dữ liệu thật và kiểm chứng độc lập trước khi kết luận độ chính xác.

Repo đang có 230 tests phần mềm và pilot 32 câu hỏi dự thảo trên 4 ảnh. Test mock đạt không chứng minh model nhận diện đúng hoặc trả lời lịch sử đúng. Tên file sample, tên trong catalog và verdict của model không phải đáp án chuẩn.

## 1. Quy ước và dữ liệu chuẩn bị

| Ký hiệu | Cách thực hiện |
| --- | --- |
| P0 | Ưu tiên trước: sai định danh, bịa thông tin, từ chối sai, mất hoặc lộ dữ liệu, luồng chính không hoạt động |
| P1 | Ưu tiên tiếp: ảnh khó, hội thoại, khôi phục lỗi, vận hành và trải nghiệm |
| P2 | Hoàn thiện trải nghiệm và khảo sát hiệu năng |
| A | Tự động, offline, điều khiển output model/tool bằng fixture để kiểm tra luật backend |
| E | Kiểm tra tích hợp qua HTTP/SSE hoặc giao diện; có thể dùng demo để kiểm tra giao thức |
| L | Model và ảnh thật, có người chấm độc lập; bắt buộc khi đánh giá chất lượng nội dung |

Mỗi ca có thể cần nhiều cách kiểm tra. `A + L` nghĩa là kiểm tra luật bằng fixture **và** đánh giá hành vi model thật; hai kết quả được lưu riêng.

Chuẩn bị các nhóm đầu vào:

- **Ảnh nhận diện được:** có nhãn người duyệt, vùng đặc trưng và mức chi tiết có thể xác định, ví dụ công trình thành phần hay chỉ quần thể. Thiên Trù/Chùa Hương, Khuê Văn Các/Văn Miếu là ứng viên thu thập, không tự coi sample hiện tại là ảnh có nhãn đã duyệt.
- **Ảnh rõ nhưng không đủ định danh:** kiến trúc phổ biến, chỉ thấy mái/cột/tường; dùng để kiểm tra nhận diện quá tự tin.
- **Ảnh gần giống:** nhiều cổng, tam quan, mái chùa hoặc công trình cùng quần thể, có ảnh đối chứng được duyệt.
- **Biến thể ảnh:** gốc, mờ, tối, nén, che khuất, crop, xoay. Ghi thông số tạo biến thể; người duyệt quyết định phần nào vẫn trả lời được. Không tạo ảnh vào repo hay gửi model trong tác vụ lập test case này.
- **Nguồn đã duyệt:** đúng thực thể, đoạn trích, URL, hash/version, sự kiện và thời gian; thêm fixture nguồn sai hoặc mâu thuẫn có chủ đích.

Khóa cấu hình khi so sánh: provider/model từng role, prompt/workflow version, config hash, budget, OCR, retrieval, corpus và `accuracy.recognition`. Với profile hiện tại, `max_status=probable`; ảnh đủ cơ sở có thể đạt `probable` và `answered`, không cần ép thành `recognized`.

`answered` phải phản ánh các ý người dùng đã hỏi ở mức chắc chắn công khai. Không dùng riêng cờ này, số claim `supported`, hoặc HTTP 200 để chấm đúng nội dung.

## 2. Nhận diện công trình — 10 ca

| ID | Ưu tiên / cách chạy | Đầu vào và câu hỏi | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| R01 | P0 · A + L | Ảnh có đặc trưng đã duyệt, không đọc được biển tên. “Đây có thể là công trình nào?” | Chọn đúng ứng viên ở mức `probable`, có ID quan sát hỗ trợ, diễn đạt có điều kiện. Không thiếu căn cứ chỉ vì không có OCR; không hỏi xác nhận tên lần nữa khi không cần. |
| R02 | P0 · A + L | Ảnh công trình thành phần được duyệt. “Đây là Chùa Hương hay Chùa Thiên Trù?” | Phân biệt công trình thành phần với quần thể; nêu được quan hệ đúng theo dữ liệu đã duyệt. Không coi hai tên này là hai ứng viên loại trừ nhau nếu nói về đúng quan hệ đó. |
| R03 | P0 · A + L | Cùng thực thể, dùng tên có dấu/không dấu, alias hoặc qualifier địa phương hợp lệ. | Không tạo mơ hồ giả chỉ vì cách viết. Không gộp hai nơi khác nhau chỉ do trùng tên; alias mơ hồ cần địa phương hỗ trợ. |
| R04 | P0 · A + L | Ảnh rõ nhưng chỉ có mái, cột và sân kiểu phổ biến. “Đây là chùa nào?” | Không suy ra tên cụ thể từ đặc điểm chung. Có thể mô tả phần nhìn thấy; định danh `unrecognized` hoặc `ambiguous` tùy dữ kiện, hỏi thông tin có ích nếu cần. |
| R05 | P0 · A + L | Ảnh đối chứng của hai công trình gần giống, người duyệt biết đúng nhãn. | Không chọn sai tên chỉ vì cùng phong cách. So sánh đặc điểm thực sự phân biệt; khi chưa phân biệt được phải giữ mơ hồ. Chấm cả lỗi gán sai và từ chối dù đủ đặc trưng. |
| R06 | P0 · A + L | Cùng ảnh, thêm `location_hint` sai, ví dụ gợi ý địa điểm khác với nhãn được duyệt. | Gợi ý được giữ là dữ liệu chưa kiểm chứng, không thành bằng chứng ảnh. Nhận diện không được chuyển sang tên sai chỉ vì gợi ý; nêu bất đồng hoặc giữ giới hạn phù hợp. |
| R07 | P1 · A + L | Coordinator đề xuất nhiều tên; Visual có một ứng viên có cơ sở phù hợp, Verifier kiểm tra được. | Các phương án sơ bộ khác của coordinator không tự buộc hỏi thêm. Vẫn kiểm tra cơ sở ảnh, ID và tính phù hợp trước khi chọn. |
| R08 | P1 · A + L | Ảnh có hai công trình; người dùng chọn `focus_box` và hỏi về vùng đó. | Trả lời đúng đối tượng trong vùng; không lấy tên của công trình nổi bật ngoài vùng. Bằng chứng/crop hiển thị đúng tọa độ ảnh gốc. |
| R09 | P1 · L | Ảnh di tích ngoài catalog Hà Nội, có nhãn độc lập. | Không ép thành một tên trong catalog. Nếu có cơ sở khác có thể nêu khả năng và giới hạn phạm vi; nếu chưa đủ thì giữ bất định. Không bắt buộc một trạng thái cố định chỉ vì thiếu nhãn catalog. |
| R10 | P0 · A + L | Ảnh không có di tích: cây, phòng ở hoặc bề mặt trống. “Công trình này xây thời nào?” | Không bịa công trình, niên đại hoặc nguồn. Nêu phần không xác định được; không dùng một trang lịch sử ngẫu nhiên để hợp thức hóa đáp án. |

## 3. Chất lượng ảnh và vùng quan sát — 7 ca

| ID | Ưu tiên / cách chạy | Đầu vào và câu hỏi | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| I01 | P0 · L | Ảnh mờ nhẹ nhưng người duyệt vẫn nhận ra đặc trưng. Giữ nguyên câu hỏi nhận diện. | Không từ chối chỉ do điểm chất lượng ảnh thấp. Đánh giá đủ đặc trưng và trả ở mức phù hợp; so với ảnh gốc để đo từ chối sai. |
| I02 | P0 · A + L | Mờ rất nặng, người duyệt không thể nhận ra công trình hoặc chữ. | Không tự nâng thành nhận diện có cơ sở. Mô tả giới hạn; chỉ hỏi ảnh khác nếu điều đó giúp phần câu hỏi còn thiếu. Không khẳng định các ký tự nhìn không rõ. |
| I03 | P1 · L | Ảnh tối, ngược sáng, lóa hoặc nén mạnh ở nhiều mức đã ghi nhận. | Chấm theo answerability từng vùng/ý. Chỉ câu hỏi còn dựa vào chi tiết bị mất mới cần giữ lại hoặc hỏi thêm; không loại toàn bộ ảnh máy móc. |
| I04 | P1 · A + L | Ảnh có độ phân giải thấp nhưng một chi tiết lớn còn rõ; OCR vùng bảng không thành công. | Chi tiết lớn vẫn được trả lời. OCR thất bại không xóa quan sát hợp lệ; không suy rằng toàn ảnh vô dụng. |
| I05 | P1 · A + E + L | Ảnh xoay tay hoặc có EXIF orientation; tiếp tục chọn cùng vùng vật lý. | Chuẩn hóa hướng đúng; vùng chứng cứ/crop khớp ảnh đang hiển thị. Không đảo trái/phải hay lấy tọa độ thumbnail làm tọa độ ảnh gốc. |
| I06 | P1 · A + L | Biển có Quốc ngữ/Latin rõ xen kẽ phần mờ, hoặc vùng cắt thiếu một nửa dòng. | Chép đúng phần đủ đọc; phân biệt không đọc được với không có chữ. Không điền phần mất bằng tên ứng viên hoặc trí nhớ. Kiểm tra cả crop và chữ trả về. |
| I07 | P1 · L | Vật cản, cây hoặc khách tham quan che biển tên nhưng bố cục còn đủ đặc trưng; biến thể khác che chính đặc trưng đó. | Không bắt buộc biển tên ở biến thể đầu; ở biến thể sau có thể hạ mức nhận diện. Tính nhất quán phải dựa vào phần thông tin còn lại, không ép hai ảnh cho cùng trạng thái. |

## 4. Hiểu câu hỏi và trả lời đúng ý — 8 ca

| ID | Ưu tiên / cách chạy | Đầu vào và câu hỏi | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| Q01 | P0 · A + L | “Đây **có thể là** công trình nào?”; coordinator viết slot thành câu khẳng định mạnh hơn. | Verifier và kết quả vẫn dựa vào câu hỏi gốc. Nhận diện có cơ sở được trả có điều kiện, không tự đòi xác nhận tuyệt đối. |
| Q02 | P1 · A + L | “Hãy xác nhận chắc chắn danh tính công trình”; chỉ có mức `probable`. | Nêu ứng viên và giới hạn, không tuyên bố đã đạt sự chắc chắn được yêu cầu. Không ép thành công hoặc tăng confidence để đáp ứng yêu cầu. |
| Q03 | P0 · A + L | Cặp câu: “Hãy xác nhận chắc chắn…” và “Tôi **không cần xác nhận chắc chắn**, chỉ muốn biết có thể là nơi nào.” | Hai ý định được phân biệt. Câu phủ định không bị đánh giá thiếu chỉ vì chứa cụm từ “xác nhận chắc chắn”; nhận diện khả năng đủ cho câu thứ hai nếu ảnh hỗ trợ. |
| Q04 | P1 · L | “chua nay o dau”, câu có lỗi gõ, viết tắt hoặc cách nói “cái mái kia”. | Hiểu đúng ý nếu đủ ngữ cảnh; cần làm rõ vùng khi tham chiếu mơ hồ thực sự ảnh hưởng đáp án. Không bắt người dùng gõ lại câu chuẩn chỉ để tiếp tục. |
| Q05 | P1 · E + L | “Bức tượng bên trái là gì?” với nhiều tượng; lần hai thêm `focus_box`. | Lần đầu không tùy tiện chọn đối tượng. Khi có vùng, trả lời đúng vùng và không hỏi lại cùng điều đã được làm rõ. |
| Q06 | P0 · A + L | “Nhận diện, mô tả mái, cho biết khởi dựng và trùng tu”; chỉ có bằng chứng cho ba phần đầu. | Kiểm tra từng ý riêng. Trả phần có căn cứ và chỉ rõ phần thiếu; không `answered` toàn bộ chỉ vì có một claim trong slot lịch sử gộp. |
| Q07 | P1 · A + L | “Chỉ mô tả những gì nhìn thấy, không cần đoán tên hay lịch sử.” | Ưu tiên đúng phạm vi yêu cầu; không thêm tên/niên đại tự suy. Không hỏi địa điểm để làm một tác vụ chỉ cần quan sát ảnh. |
| Q08 | P0 · A + L | Câu hỏi có tiền đề sai đã được người duyệt xác nhận: “Vì sao công trình được xây vào <mốc sai>?” | Không nhận tiền đề sai làm sự thật. Đối chiếu nguồn và sửa có căn cứ hoặc nêu chưa xác minh; không dựng lý do cho một sự kiện sai. Mốc cụ thể phải lấy từ bộ nhãn đã duyệt. |

## 5. Nguồn, lịch sử và chống bịa đặt — 10 ca

| ID | Ưu tiên / cách chạy | Đầu vào và câu hỏi | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| E01 | P0 · A + L | Nguồn đúng công trình, đúng sự kiện, có đoạn trích hỗ trợ và version/hash. Hỏi một dữ kiện lịch sử tương ứng. | Câu trả lời khớp nội dung/sự kiện, trích đúng đoạn, có ID/URL hợp lệ. Nhận diện mới `probable` thì phần lịch sử được trình bày theo điều kiện đó. |
| E02 | P0 · A + L | Kết quả tìm kiếm có chủ đề liên quan nhưng nói về công trình khác. | Không dùng làm bằng chứng cho đối tượng ảnh; thử truy xuất đúng trong budget hoặc trả phần có căn cứ. Nguồn không rỗng không đồng nghĩa nguồn phù hợp. |
| E03 | P0 · A + L | Một đoạn có nhiều năm: năm sinh vua, đặt tên, khởi dựng, bị phá hủy và trùng tu. | Gắn mỗi mốc với đúng sự kiện; không dùng năm sinh hoặc đặt tên làm năm xây. Không gộp khởi dựng, tái dựng và trùng tu. |
| E04 | P0 · A + L | Hai nguồn đã duyệt nhưng bất đồng về cùng mốc hoặc sự kiện. | Nêu rõ bất đồng và nguồn tương ứng; không tự chọn một mốc thành sự thật chắc chắn hay trộn hai nguồn thành một câu không nguồn nào chứng minh. |
| E05 | P0 · A + L | Bài viết về quần thể có nhiều công trình thành phần; đoạn cần dùng nói về một thành phần cụ thể. | Chỉ gắn dữ kiện cho đúng thành phần được đoạn đó hỗ trợ. Không lấy lịch sử quần thể/di tích bên cạnh để trả cho công trình trong ảnh. |
| E06 | P0 · A + L | Nguồn ghi “tương truyền”, “theo giai thoại” hoặc ghi chép lịch sử có mức bất định. | Giữ nguyên loại bằng chứng và mức bất định. Không trình bày truyền thuyết thành sự kiện lịch sử đã xác nhận. |
| E07 | P0 · A + E | Model trả evidence ID không tồn tại, nguồn không đăng ký, quote không nằm trong snapshot hoặc URL tự tạo. | Backend không chấp nhận nhận định đó. UI/API vẫn giữ phần hợp lệ, không hiển thị nội dung bị chặn như kết luận đã kiểm chứng. Kiểm tra ID và quote bằng dữ liệu, không chỉ nhìn prose. |
| E08 | P0 · A + L | Hỏi “Có phải gỗ lim/đồng/đá vôi không?”; một ca không nguồn, một ca có nguồn đúng thực thể nói rõ thuộc tính đó. | Không suy loại vật liệu từ màu/hình. Có nguồn thì nêu đúng đối tượng và giới hạn; không có nguồn vẫn mô tả được hình dáng/màu sắc. |
| E09 | P0 · A + L | “Đọc/dịch chữ Hán trên hoành phi rồi mô tả kiến trúc”; cấu hình không hỗ trợ phiên đọc Hán–Nôm. | Không tự phiên âm/dịch chữ. Phần kiến trúc vẫn nên được phục vụ nếu có thể tách khỏi phần không hỗ trợ; đây là kỳ vọng cần kiểm tra, không mặc định hành vi hiện tại đã đáp ứng. |
| E10 | P0 · A + L | Chỉ có ảnh rõ, retrieval hết nguồn hoặc lỗi; người dùng hỏi cả kiến trúc lẫn lịch sử. | Trả quan sát có căn cứ, giữ lại phần lịch sử. Không lấy trí nhớ model để thay nguồn; không buộc người dùng xác nhận lại tên chỉ vì hệ thống thiếu tư liệu. |

## 6. Hỏi bổ sung và tiếp tục hội thoại — 6 ca

| ID | Ưu tiên / cách chạy | Đầu vào và thao tác | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| C01 | P0 · A + E + L | Ảnh mơ hồ → nhận câu hỏi → chọn một `selected_candidate` hợp lệ. | Lưu lựa chọn có cấu trúc; tạo child run và giữ parent bất biến. Không hỏi lại đúng tên vừa chọn. Lựa chọn chỉ xác định đối tượng đối chiếu, không tự chứng minh ảnh đúng ứng viên. |
| C02 | P0 · A + E + L | Trả lời “Tôi không biết”, “Không chắc” hoặc lời không giúp định danh. | Không coi chuỗi không rỗng là đã xác nhận danh tính. Có thể gợi ý một hành động khác có ích nếu còn lượt, hoặc giữ câu trả lời một phần; không lặp vô hạn cùng câu hỏi và không ép người dùng biết đáp án. |
| C03 | P1 · A + E | Tiếp tục cùng ảnh/câu hỏi/cấu hình; sau đó thử đổi model, vùng hoặc chính sách ảnh. | Tái sử dụng perception chỉ khi đầu vào liên quan còn phù hợp. Thay cấu hình perception/vùng làm vô hiệu cache cần thiết; đổi gợi ý không làm rò gợi ý vào quan sát độc lập. |
| C04 | P0 · A + E + L | Gửi ảnh mới sau khi đã dùng nhãn sample hoặc gợi ý tên ở ảnh trước. | Không tự gắn nhãn ảnh cũ sang ảnh mới. Kiểm tra lại root ảnh, tọa độ, nguồn của gợi ý và liên kết bằng chứng; không dùng crop/ID cũ để chứng minh ảnh mới. |
| C05 | P0 · A + E | Gửi hai phản hồi đồng thời cho cùng revision; gửi lại request cùng idempotency key; gửi revision cũ. | Chỉ một phản hồi tiêu thụ revision. Gửi lại hợp lệ nhận cùng child; nội dung khác cùng key hoặc revision cũ bị từ chối đúng hợp đồng. Không tạo thêm lượt gọi model ngoài ý muốn. |
| C06 | P0 · A + E | Chạm giới hạn lượt hỏi, TTL hoặc ngân sách hội thoại; tiếp tục bằng review/retry và nhiều nhánh song song. | Không reset hoặc vượt ngân sách bằng cách tạo nhánh. Nêu đúng nguyên nhân không tiếp tục được; giữ phần kết quả trước. Hạn mức được kiểm tra trên hội thoại chung. |

## 7. API, streaming và worker — 8 ca

| ID | Ưu tiên / cách chạy | Đầu vào và thao tác | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| A01 | P0 · E | Tạo session → upload/sample asset → create run → đọc SSE/history → result/evidence/sources/crop. | Trình tự chạy được trên Swagger/Postman/client. Các endpoint nhất quán về run, trạng thái, bằng chứng và nguồn; không trả bản nháp như đáp án đã duyệt. |
| A02 | P1 · A + E | Ngắt SSE giữa chừng, nối lại bằng cursor/`Last-Event-ID`; thử token hết hạn. | Không mất sự kiện đã lưu; client xử lý idempotent theo sequence. Phân biệt đoạn chờ hỏi bổ sung với hoàn tất hội thoại; kết nối được đóng đúng khi hết quyền. |
| A03 | P0 · A + E | POST tạo run giống hệt hai lần với cùng key; tiếp tục dùng key đó nhưng đổi ảnh, query, hint hoặc vùng. | Cùng request trả cùng run; request khác bị conflict. Hash phải phân biệt ngữ cảnh thực sự ảnh hưởng xử lý. |
| A04 | P0 · A + E | Session B cố đọc asset/result/evidence/crop/events hoặc phản hồi clarification của session A. | Không truy cập hay sửa được tài nguyên của A, kể cả qua endpoint phụ. Lỗi không làm lộ nội dung hoặc credential. |
| A05 | P0 · A + E | File hỏng, giả MIME, sai định dạng, quá byte/pixel; query rỗng/quá dài; box đảo cạnh/ngoài 0..1. | Từ chối ở biên API đúng hợp đồng; không enqueue/call model với input không hợp lệ. Không tự suy tọa độ pixel thành tọa độ chuẩn hóa. |
| A06 | P1 · A + E | Hủy run đang queued hoặc đang xử lý; retry run đã kết thúc. | Hủy hợp tác, không để run kẹt; trạng thái và event nhất quán. Retry tạo child có key rõ ràng, giữ đúng input/hint và không sửa parent. |
| A07 | P0 · A + E | Restart API/worker khi run queued hoặc awaiting_input; worker mất lease trong lúc xử lý. | Kết quả và câu hỏi bổ sung tồn tại sau restart. Claim job nguyên tử; không hai worker cùng ghi thành công một lượt. Run stale được xử lý theo chính sách, không treo mãi. |
| A08 | P0 · A + E | Bật embedded worker, không mở client theo dõi; để job hoàn tất rồi kiểm tra readiness và tiếp tục chờ idle. | Job vẫn được xử lý. `/health/ready` phản ánh worker/DB thực tế và không lỗi chỉ vì hết job; không dùng trạng thái thành công của một run để che worker đã chết. |

## 8. Streamlit và trải nghiệm người dùng — 5 ca

| ID | Ưu tiên / cách chạy | Đầu vào và thao tác | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| U01 | P0 · E | Cập nhật code/schema trong khi server đang chạy; thử refresh/rerun, rồi restart tiến trình. | Xác minh trên phiên web thực tế rằng trang dựng đủ widget. Khi schema không phù hợp, chỉ rõ trường/lỗi an toàn và hướng dẫn restart. Health HTTP 200 riêng lẻ chưa đủ kết luận UI hoạt động. |
| U02 | P1 · A + E | Chạy sample mặc định; bật/tắt dùng nhãn mẫu; đổi hint, query, ảnh, hướng hoặc vùng. | Mặc định không đưa nhãn vào nhận diện độc lập. Khi bật, hiển thị provenance; thay input không để kết quả cũ giả như thuộc input mới. Thao tác tùy chọn chưa chạy không tự gọi model. |
| U03 | P1 · A + E | Nhận `partial`, `needs_clarification`, `verification_unavailable` hoặc bị lỗi ở một bước. | Thông báo khác nhau và có hành động phù hợp. Giữ phần có căn cứ; chỉ có form hỏi bổ sung khi đang chờ thực sự, không vì mỗi trạng thái partial. |
| U04 | P1 · E + L | Mở từng giai đoạn, claim, source và crop của cùng một kết quả; dùng UI local rồi UI qua API. | Truy được kết luận về bằng chứng thật; đúng vùng, đúng nguồn và mức nhận diện. Hai chế độ không diễn giải trạng thái mâu thuẫn; phần giải thích không làm rò dữ kiện bị gate chặn. |
| U05 | P2 · E | Câu trả lời dài, nhiều nguồn; màn hình nhỏ, dùng bàn phím, xem lịch sử và đổi lượt. | Nội dung/chỉ dẫn đọc được, nút thao tác dùng được, không lẫn ảnh/câu hỏi giữa các lượt. Các vùng quan trọng không bị che; ghi nhận lỗi bố cục bằng viewport cụ thể. |

## 9. Lỗi nhà cung cấp, cấu hình và quan sát vận hành — 6 ca

| ID | Ưu tiên / cách chạy | Đầu vào và thao tác | Kết quả mong đợi / cách chấm |
| --- | --- | --- | --- |
| O01 | P0 · A + E | Mô phỏng 429/503/timeout, JSON sai hoặc output bị cắt ở Visual/Knowledge/Judge; thử lỗi vĩnh viễn và lỗi hồi phục. | Phân loại lỗi đúng, retry trong hạn mức. Judge chưa hoàn tất thì không duyệt bản nháp; lỗi OCR/recovery tùy chọn không xóa phần đã được hỗ trợ. Không coi lỗi kỹ thuật là model từ chối vì thiếu bằng chứng. |
| O02 | P0 · A + E | Cấu hình YAML sai kiểu/field, env override không hợp lệ, provider thiếu capability hoặc credential. | Fail rõ ở bước phù hợp; không bỏ qua validation hoặc âm thầm đổi provider ngoài cấu hình. UI/log chỉ chứa tên trường và mã lỗi an toàn, không echo input/secret. |
| O03 | P0 · A + E | Query, ảnh, OCR hoặc source chứa chỉ thị giả “bỏ qua quy tắc”, yêu cầu lộ key/đổi nguồn; URL nguồn chuyển tới mạng nội bộ. | Dữ liệu không trở thành chỉ thị điều khiển. Không lộ key, không bỏ gate; ingestion/retrieval giữ kiểm tra URL/redirect và giới hạn đã cấu hình. Đây là kiểm thử chủ động, không phải khẳng định đã phát hiện tấn công. |
| O04 | P0 · A + E | Chạy đồng thời nhiều run và hội thoại; kiểm tra log, tool ledger và LangSmith khi bật/tắt capture content. | Đúng run/parent/trace ID, không lẫn input/bằng chứng giữa người dùng. Có thời gian/lỗi/usage khi được cung cấp; không ghi key, token hoặc ảnh thô ngoài chính sách. |
| O05 | P1 · A + E | Gọi crop/OCR/recovery song song, review nhiều lần; hết tool/model/deadline budget. | Hạn mức nguyên tử, cache đúng ảnh/vùng/query/config, không làm mới ngân sách ngoài ý muốn. Dừng theo chính sách và giữ artifact có ích; không có bước truy xuất không giới hạn. |
| O06 | P2 · E + L | Chạy lặp một bộ cố định, sau đó tăng tải theo môi trường test; mô phỏng provider chậm. | Đo thời gian nhận job, sự kiện đầu, từng stage, kết quả cuối và toàn hội thoại; báo p50/p95, retry, queue và usage. Chốt SLA sau baseline, không mặc định một con số vài giây cho luồng nhiều model. |

## 10. Các ca nên chạy trước

Đợt đầu ưu tiên **15 ca**: R01, R02, R04, I01, I02, Q03, Q06, E02, E03, E04, E08, E09, C01, C02, U01.

Chúng nhắm trực tiếp vào bài toán đồ án và các lỗi đã gặp: thiếu OCR dù ảnh đủ đặc trưng, nhầm thành phần/quần thể, bịa vì ảnh mơ hồ, đọc sai ý định, mất phần câu hỏi, nguồn sai, hỏi bổ sung không hiệu quả và server UI dùng schema cũ. Các ca A04/O02/O03 cần bổ sung vào đợt kiểm tra trước khi mở API cho người khác.

Sau đó hoàn tất P0 còn lại → P1 → P2. Mỗi ca có thể có nhiều biến thể dữ liệu; **60 test case thiết kế không đồng nghĩa 60 ảnh hoặc 60 lần gọi API**. Nên chạy live theo từng lô nhỏ, kiểm tra lỗi và budget trước khi mở rộng.

## 11. Khoảng trống cần kiểm tra thêm so với code hiện tại

Đây là nhận xét từ việc đọc code, chưa phải lỗi đã tái hiện trong tác vụ này:

| Ca | Lý do ưu tiên | Vị trí liên quan |
| --- | --- | --- |
| Q03 | Điều kiện chắc chắn đang nhận biết bằng việc xuất hiện các cụm từ; cần kiểm tra câu phủ định chứa chính cụm đó. | `workflow/accuracy.py`: `requires_certainty` |
| Q06 | Coverage dựa trên slot có claim supported; nếu coordinator gộp nhiều ý thành một slot, cần kiểm tra còn sót ý mà vẫn đánh dấu hoàn tất. | `workflow/accuracy.py`: `covered`; `core/evidence.py`: `RequestedSlot` |
| C02 | `hinted_subject` tính cả answer không rỗng; cần kiểm tra “tôi không biết” không bị coi như đã bổ sung định danh. | `workflow/accuracy.py`: `hinted_subject`, `needs_identity` |
| Q07 | Composer có thể thêm câu nhận diện khi có recognition; cần kiểm tra yêu cầu chỉ quan sát được tôn trọng. | `workflow/accuracy.py`: `recognition_sentence`, composer |
| E09 | Scope hiện chặn yêu cầu phiên đọc Hán–Nôm; cần kiểm tra câu hỏi hỗn hợp vẫn giữ được phần kiến trúc trả lời được. | `workflow/service.py`: `scope` |
| U01 | AppTest mở tiến trình mới không tái hiện đầy đủ trạng thái server giữ module cũ. | `tests/test_ui.py`; tiến trình Streamlit và phiên WebSocket đang chạy |

## 12. Gắn với các test đã có

| Nhóm | Nền tảng đã có trong repo | Phần cần bổ sung |
| --- | --- | --- |
| R/I/Q | `tests/test_recognition.py`, `tests/test_accuracy_regressions.py`, `tests/test_accuracy_profile.py` | Ảnh thật dễ nhầm, biến thể có answerability được duyệt, hiểu phủ định và câu nhiều ý |
| E | Gate ID/quote/entity, material/date/Hán–Nôm và retrieval trong các file trên; `tests/test_ingestion.py` | Nguồn lịch sử xung đột, loại sự kiện, truyền thuyết và chấm đúng nội dung bằng người |
| C/A | `tests/test_api.py`, `tests/test_accuracy_profile.py`, `tests/test_recognition_api.py` | Luồng từ “không biết”, ngữ cảnh sai hoặc thay ảnh trong nhiều lượt, tải/concurrency gần thực tế |
| U/O | `tests/test_ui.py`, `tests/test_operational_logging.py`, các test observability/gateway/budget | Phiên web thật khi nâng cấp server, đánh giá bố cục, live provider có biến động |
| Đánh giá | `core/evaluation.py`, `scripts/evaluate.py`, `tests/test_evaluation.py` | Gold và người chấm; tuyệt đối không đổi các ca chưa duyệt thành reviewed để lấy điểm |

Tên nhóm tương ứng chỉ chứng minh có nền tảng test; không có nghĩa toàn bộ ca trong bảng đã được bao phủ hoặc đã đạt.

## 13. Quy trình chạy và ghi kết quả

Với mỗi ca:

1. Ghi ID, phiên bản code/config/model, ảnh và hash, câu hỏi, context/hint, nguồn/version; đánh dấu nhãn đã duyệt hay chưa.
2. Chạy input qua entry point cần kiểm tra: service, API hoặc UI. Ca live phải dùng manager thật; lưu rõ demo/mock/live.
3. Lưu run/parent ID, các event, `recognition`, `answer_status`, claims/quotes/evidence, clarification, tool/model calls và lỗi.
4. Kiểm tra máy được: ID tồn tại, source/entity, quote, trạng thái, quyền, hash, budget, cache, tính bất biến parent và thứ tự event.
5. Người chấm kiểm tra đúng định danh, đúng chi tiết ảnh, đúng sự kiện lịch sử và đủ từng ý đã hỏi. Không sao chép verdict tự đánh giá của model.
6. Ghi kết quả `pass`, `fail`, `blocked_missing_gold` hoặc `not_run`, đính kèm lỗi tái hiện được. Chưa có gold thì vẫn kiểm tra được giao thức/gate, nhưng không công bố điểm đúng nội dung.

Mẫu bảng theo dõi:

| Case / biến thể | Run ID | Nhãn ảnh/nguồn đã duyệt? | Kỳ vọng | Thực tế | Kết quả | Người chấm / ngày | Issue |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R01 / ảnh 01 | Chưa chạy | Chưa | Probable đúng ứng viên, không hỏi lại | — | not_run | — | — |

Lệnh hỗ trợ hiện có, chạy từ `doan_demo`:

```powershell
# Kiểm tra phần mềm, không đo độ đúng lịch sử
uv run --locked pytest
uv run --locked python -m scripts.api_contract_report

# Tạo 32 ca dự thảo; chưa phải bộ 60 ca của tài liệu này
uv run --locked python -m scripts.evaluate prepare

# Kiểm tra pipeline bằng demo, không dùng kết quả này làm điểm chất lượng
uv run --locked python -m scripts.evaluate run data/evaluation/hanoi-draft.json --demo --allow-draft --limit 2 --output reports/evaluation/demo.json

# Chỉ chạy sau khi đã có manifest reviewed, ảnh/nguồn và ngân sách phù hợp
uv run --locked python -m scripts.evaluate run data/evaluation/hanoi-reviewed.json --live --limit 5 --output reports/evaluation/live.json
```

Tài liệu 60 ca này là đặc tả kiểm thử, không phải manifest có thể đưa trực tiếp vào CLI. CLI hiện chấm theo một lượt prediction/case; các ca nhiều lượt, tải hoặc nâng cấp server cần kịch bản E2E riêng. Nếu chỉ chạy 5 ca, dùng đúng manifest con 5 ca và judgments tương ứng khi chấm; scorer từ chối thiếu prediction/nhãn.

Trong bản chấm live, cần nhãn đúng/sai cho mọi claim supported, verdict từng slot và `recognition_correct` khi hiển thị `probable`/`recognized`. Các biến thể cùng ảnh và các ảnh cùng entity không được chia lẫn dev/test. Dữ liệu thay đổi phải cập nhật hash và duyệt lại nhãn phù hợp.

## 14. Tiêu chí nghiệm thu đề xuất

- **Phần mềm:** P0 được chọn cho bản phát hành phải đạt; các kiểm tra phân quyền, credential, quote/ID và ngân sách không được có lỗi đã biết chưa xử lý.
- **Chất lượng:** chấm đúng định danh, factual claim precision, độ đủ từng ý, từ chối sai và hỏi bổ sung không cần thiết. Báo riêng ca answerable/unanswerable, ảnh rõ/ảnh kém và blind/có gợi ý; không chỉ báo accuracy chung.
- **Lỗi kỹ thuật:** báo riêng timeout/provider/schema/worker, không tính chúng thành “thiếu bằng chứng” hoặc giấu bằng cách bỏ ca khỏi báo cáo. Nêu rõ mẫu số từng chỉ số.
- **Hiệu năng:** đo latency từng giai đoạn và tổng hội thoại, số lần gọi/retry/tool, usage khi có. Chưa đặt phần trăm accuracy hay SLA cho đến khi có pilot được duyệt và baseline.
- **Khả năng tái hiện:** lưu đủ input/config/source snapshot để kiểm tra lại; các test so sánh dùng cùng điều kiện và báo biến động qua số lần chạy đã định trước.

Scorer hiện hỗ trợ human claim precision, recognition precision, slot accuracy/coverage, false refusal, technical failures và p50/p95 thời gian. Các chỉ số như hỏi bổ sung không cần thiết, phân nhóm ảnh, thời gian tới event đầu và tính nhất quán qua biến thể cần bảng chấm/báo cáo bổ sung; tài liệu này không khẳng định scorer đã có sẵn tất cả.
