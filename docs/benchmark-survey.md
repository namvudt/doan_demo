# Khảo sát benchmark cho hỏi–đáp ảnh di tích và văn hóa

Ngày tra cứu: **16/11/2026**. Trạng thái: **khảo sát nguồn, chưa chạy đánh giá hệ thống**.

Đề xuất dùng **VietTravelVQA làm nguồn ứng viên**, xây thêm bộ Hà Nội được duyệt để đo toàn luồng; dùng benchmark nhận diện, OCR và grounding để tìm lỗi từng thành phần. Trong các nguồn đã kiểm tra, chưa có bộ đáp ứng đồng thời ảnh di tích Hà Nội, lịch sử có nguồn, ảnh mờ, câu hỏi khó và hội thoại hỏi bổ sung.

Quy mô bên dưới là thông tin tác giả công bố hoặc metadata của bản phát hành, không phải số mẫu đã được dự án kiểm chứng. Chỉ đọc bài báo, dataset card, metadata kho và một preview nhỏ; không tải toàn bộ ảnh, gọi Gemini, tạo prediction hay chấm điểm. Unit test và kiểm tra HTTP trước đây không phải kết quả benchmark chất lượng.

## 1. Các bộ nên xem trước

P0/P1/P2 là thứ tự đề xuất cho dự án này, không phải xếp hạng chất lượng công bố.

| Ưu tiên | Bộ và nguồn chính thức | Quy mô công bố | Dùng cho hệ thống | Điều kiện trước khi dùng |
| --- | --- | --- | --- | --- |
| P0 | [VietTravelVQA v2](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v2) | 9.530 QA, 1.406 ảnh; test 1.715 QA | VQA tiếng Việt, kiến thức di sản | Lọc Hà Nội và di tích; kiểm tra đáp án, nguồn và split theo thực thể |
| P0, bổ sung có chọn lọc | [VietTravelVQA v3](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v3) | 10.530 QA trên cùng 1.406 ảnh; test 1.893 QA | Câu hỏi kiến thức có provenance graph | Phần KG chưa được người duyệt; không coi v2/v3 là hai tập độc lập |
| P1 | [Google Landmarks v2 — GLDv2](https://github.com/cvdfoundation/google-landmark) | Khoảng 5 triệu ảnh, 200 nghìn lớp | Nhận diện địa danh, truy hồi ảnh tham chiếu | Không có QA lịch sử; cần kiểm tra có đủ địa danh mục tiêu |
| P1 nếu có truy hồi ảnh | [Revisited Oxford / Paris](https://cmp.felk.cvut.cz/revisitop/) | 70 query mỗi bộ, có bounding box và nhãn truy hồi | Phân biệt công trình, góc chụp khó | Địa danh ngoài phạm vi Hà Nội; đo riêng thành phần retrieval |
| P1, tham khảo thiết kế | [ChinaHeritaQA](https://github.com/boleima/ChinaHeritaQA) | 51 di sản Trung Quốc, 23 địa điểm gây nhiễu; 7 dạng câu hỏi | Nhận diện, triều đại, lịch sử, công năng | Trắc nghiệm Trung/Anh; repo hiện ghi chỉ có ảnh mẫu, ảnh đầy đủ chờ phát hành |
| P1 cho chữ Quốc ngữ | [ViTextVQA](https://github.com/minhquan6203/ViTextVQA-Dataset) | 16.762 ảnh, 50.342 QA | Đọc chữ trong ảnh và hỏi–đáp dựa vào chữ | Không chuyên di tích/Hán–Nôm; kho dữ liệu chính yêu cầu chấp nhận điều kiện truy cập |
| P2 cho bằng chứng ảnh | [Seeing Culture — SCB](https://seeingculture-benchmark.github.io/) | 1.065 ảnh, 3.178 câu hỏi, 138 hiện vật/vật thể văn hóa | Kiểm tra trả lời có dựa đúng vùng ảnh | Không chuyên kiến trúc di tích; ảnh/answer key/mask cần quyền truy cập đánh giá |
| P2 | [CVQA](https://huggingface.co/datasets/afaji/cvqa) | 10.374 mẫu trong metadata; 39 cặp quốc gia–ngôn ngữ | Trắc nghiệm văn hóa, có nhóm buildings/landmarks | Cần xác nhận nhãn của revision chọn dùng; không mặc định có tập Hà Nội |
| P2 | [CulturalVQA](https://huggingface.co/datasets/mair-lab/CulturalVQA) | Bài công bố 2.378 QA; metadata kho hiện 2.374 dòng | Kiến thức phong tục, nghi lễ, văn hóa | Không chuyên di tích; phải ghi đúng số mẫu của bản thực tế |

## 2. Những điểm quyết định lựa chọn

### VietTravelVQA: sát bài toán nhất trong các nguồn tìm được

Hai bản có `messages`, `images` và metadata provenance. V3 ghi rõ KG chưa được người duyệt, không có OCR, split theo ảnh chứ không theo địa danh; dữ kiện địa giới giữa các nguồn có thể khác thời điểm. Đây là lý do cần duyệt lại lịch sử và nhóm theo QID/thực thể trước khi dùng cho Hà Nội. Không lấy câu hỏi có sẵn tên công trình để kết luận khả năng nhận diện ảnh. [Dataset card v3](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v3).

[Mendeley V2](https://data.mendeley.com/datasets/fvxtpnh8mh/2), DOI `10.17632/fvxtpnh8mh.2`, là một nguồn phát hành khác của VietTravelVQA. Chưa so sánh file/hash với Hugging Face; không mặc định hai nơi cùng nội dung chỉ vì cùng ghi V2.

### GLDv2 và Revisited Oxford/Paris: đo nhận diện và truy hồi

GLDv2 có nhãn nhận diện/truy hồi và mã tính metric; nhãn phân cấp được bổ sung trong lịch sử phát hành. Có thể tham khảo để biểu diễn quan hệ quần thể–công trình thành phần, nhưng chưa xác minh mức bao phủ Hà Nội. Annotation CC BY 4.0; ảnh giữ quyền riêng theo nguồn. [Repo GLDv2](https://github.com/cvdfoundation/google-landmark).

Revisited cung cấp giao thức Easy/Medium/Hard, mAP và mP@k. Phù hợp khi bổ sung index ảnh tham chiếu; không đo được độ đúng của niên đại hoặc trích dẫn. Chỉ có nhãn khó không đồng nghĩa đã có đủ ảnh mờ kiểu người dùng chụp. [Mã đánh giá chính thức](https://github.com/filipradenovic/revisitop).

### ChinaHeritaQA: hữu ích để thiết kế câu hỏi gây nhầm

Có thể học cách chọn ứng viên cùng loại di sản, cùng địa phương và ngoài miền. Tuy nhiên, 5 lựa chọn làm bài toán khác với hỏi–đáp mở. README ghi ảnh đầy đủ hơn 6 GB chưa phát hành tại kho này; code ghi CC BY-NC-ND 4.0, ảnh Weibo thuộc chủ sở hữu gốc. Đưa vào danh sách tham khảo, chưa coi là bộ sẵn sàng nhập toàn bộ. [README tác giả](https://github.com/boleima/ChinaHeritaQA).

### ViTextVQA và SCB: tách khả năng đọc chữ khỏi khả năng chỉ đúng vùng ảnh

ViTextVQA thích hợp đo đọc biển/bảng chữ tiếng Việt; không dùng kết quả của nó để suy ra khả năng phiên đọc bia Hán–Nôm. HF chính ghi CC BY-NC 3.0 và yêu cầu đồng ý điều kiện trước khi lấy dữ liệu. [Kho tác giả](https://huggingface.co/datasets/minhquan6203/ViTextVQA).

SCB yêu cầu chọn ảnh rồi phân đoạn vật thể làm bằng chứng. Card hiện công khai metadata dev 149 dòng; answer key và mask được giữ cho đánh giá, cần liên hệ tác giả để có ảnh/scoring. Annotation CC BY-NC-SA 4.0. Hệ thống hiện xuất bounding box/crop, chưa xuất segmentation mask: có thể tham khảo cách gán nhãn, chưa chấm mIoU tương đương giao thức SCB. [Dataset card SCB](https://huggingface.co/datasets/Multimedia-SMU/seeingculture-benchmark).

### CVQA và CulturalVQA: benchmark bổ trợ, cần đối chiếu phiên bản

CVQA là trắc nghiệm 4 lựa chọn. Card vẫn mô tả `Label=-1` và chấm qua EvalAI, nhưng preview API chính thức đã kiểm tra 100 dòng có nhãn 0–3. Chưa kiểm tra toàn bộ nhãn; cần chốt revision và giao thức trước khi chọn chấm local hay nộp chính thức. Giấy phép theo mẫu/ảnh, có mục chỉ dùng nghiên cứu. [CVQA](https://huggingface.co/datasets/afaji/cvqa).

CulturalVQA có nhiều đáp án tham chiếu cho câu hỏi mở về văn hóa; hợp với kiểm tra đồng nghĩa. Chênh lệch 2.378 mẫu công bố và 2.374 dòng metadata phải được ghi lại, chưa xác định nguyên nhân. Annotation CC BY-SA 4.0, quyền ảnh theo nguồn. [Dataset card](https://huggingface.co/datasets/mair-lab/CulturalVQA).

## 3. Nguồn bổ trợ cho các điểm yếu hiện tại

| Nguồn | Giá trị có thể áp dụng | Giới hạn |
| --- | --- | --- |
| [VizWiz-VQA](https://vizwiz.org/tasks-and-datasets/vqa/) | Có nhãn không thể trả lời; phù hợp nghiên cứu khi nào nên từ chối với ảnh người dùng chụp | Không phải ảnh di tích; train/val có đáp án, test ẩn đáp án |
| [ImageNet-C](https://github.com/hendrycks/robustness) | Tham khảo giao thức làm suy giảm ảnh theo loại và mức độ | Áp dụng biến đổi lên ảnh di tích đã có quyền; kết quả tự tạo phải ghi là biến thể của dự án, không gọi là điểm ImageNet-C chính thức |
| [ALCE](https://github.com/princeton-nlp/ALCE) | Tham khảo cách tách độ đúng nội dung và chất lượng citation | Không chuyên di tích, không đo ảnh; chấm tự động cần đối chiếu người duyệt tiếng Việt |
| [SHP-QA](https://huggingface.co/datasets/FatimahEmadEldin/SHP-QA) | 433 QA về địa điểm lịch sử Saudi, có `answerable`, `gold_place_ids`, `gold_chunk_ids`; tham khảo schema nguồn | Tiếng Ả Rập; card ghi `human_verified=false` toàn bộ, câu hỏi do model sinh; chưa dùng làm gold nghiệm thu |

Nguồn thông tin di tích hoặc catalog địa điểm không tự trở thành benchmark: vẫn cần câu hỏi, đáp án chấp nhận được, nguồn đối chiếu, split, quyền ảnh và quy tắc chấm.

## 4. Bộ đánh giá đề xuất cho đồ án Hà Nội

Đây là **thiết kế dự kiến**, chưa thu thập hay gán nhãn xong.

### Phạm vi và cỡ mẫu

- Bước đầu: 40–50 ca được duyệt để hiệu chỉnh rubric và tìm lỗi; chưa đủ để tuyên bố chất lượng toàn Hà Nội.
- Sau đó: khoảng 300–500 câu hỏi trên 15–20 di tích/quần thể, có nhiều ảnh độc lập mỗi nơi. Chốt số lượng theo nguồn ảnh và khả năng duyệt, không nhân bản câu hỏi để đạt chỉ tiêu.
- Có nhãn phân biệt quần thể với thành phần; đặc biệt tránh gộp Chùa Hương với mọi công trình bên trong hoặc Văn Miếu với riêng Khuê Văn Các.
- Dành nhóm riêng cho ảnh không phải di tích, công trình tương tự, ảnh thiếu góc phân biệt, thông tin nguồn thiếu/mâu thuẫn và yêu cầu ngoài khả năng hỗ trợ.

| Nhóm | Cần kiểm tra | Đáp án/nhãn cần có |
| --- | --- | --- |
| Danh tính | Tên, tên khác, quần thể/thành phần, ứng viên gần giống | Entity ID, alias, quan hệ cha–con, mức có thể xác định từ ảnh |
| Quan sát ảnh | Mái, cổng, bố cục, số lượng chi tiết nhìn thấy | Chi tiết chấp nhận được, bounding box; phần bị che hoặc không thể suy ra |
| Lịch sử | Khởi dựng, tái dựng, trùng tu, nhân vật, công năng | Fact riêng theo sự kiện, nguồn và đoạn trích, thời điểm dữ kiện |
| Câu hỏi nhiều ý | Một số ý có chứng cứ, một số thiếu | Slot độc lập, answerability và fact chuẩn từng slot |
| Ảnh chất lượng thấp | Mờ, tối, JPEG, độ phân giải thấp, che khuất | Nhãn lại khả năng trả lời sau biến đổi; không mặc định ảnh mờ đều phải từ chối |
| Câu hỏi khó | Không dấu, lỗi gõ, cách nói đời thường, phủ định, tiền đề sai | Ý định, các cách trả lời tương đương, phần cần sửa tiền đề |
| Hỏi bổ sung | Có/không cần hỏi; người dùng biết/không biết địa điểm | Thông tin thực sự thiếu, phản hồi ở lượt sau, điều kiện dừng hỏi |
| Chữ và suy luận vượt ảnh | Quốc ngữ so với Hán–Nôm; vật liệu chính xác, niên đại từ vẻ cũ | Phần đọc được, giới hạn suy luận, yêu cầu nguồn hoặc trả lời ngoài phạm vi |

Ảnh gốc và mọi bản crop/mờ/nén thuộc cùng `image_family`. Gom các thành phần cùng quần thể vào `entity_group` khi chia dev/test để hạn chế rò rỉ gần nhau. Không đưa tên file, EXIF, QID, đáp án hoặc caption chứa danh tính vào prompt nhận diện mù.

Tách hai phép đo: nhận diện mù chỉ ảnh + câu hỏi trung tính; hỏi–đáp có gợi ý địa điểm đúng như đầu vào người dùng. Nếu thay split hoặc dịch/chỉnh câu hỏi benchmark công khai, báo rõ là tập thích nghi, không so trực tiếp với leaderboard gốc.

### Duyệt ground truth

1. Kiểm tra quyền ảnh, nguồn gốc, ảnh trùng/gần trùng và thực thể. Không dùng nhãn tên file sample làm ground truth.
2. Với lịch sử, lưu URL, tiêu đề, thời điểm truy cập, bản chụp nội dung/hash, đoạn hỗ trợ và phạm vi thực thể. Ghi riêng lịch sử khởi dựng, công trình hiện còn và truyền thuyết.
3. Gán nhãn từng ý: trả lời được hay không, đáp án/fact chấp nhận, nguồn, vùng ảnh nếu cần. Giữ bản chưa kiểm chứng ở `draft`.
4. Ưu tiên hai người duyệt độc lập nhóm lịch sử/ca mâu thuẫn và một người phân xử. Nếu chưa có người có chuyên môn, không ghi “đã được chuyên gia xác nhận”.
5. Đóng băng bản test trước khi chỉnh prompt/ngưỡng. Lưu revision dữ liệu, config, model, nguồn retrieval và ngân sách mỗi lần chạy sau này.

Với biến thể chất lượng ảnh, một câu hỏi lịch sử vẫn có thể trả lời khi danh tính đã được cung cấp, trong khi nhận diện mù không thể. Answerability phải xét đủ ảnh, câu hỏi, gợi ý và nguồn được phép dùng.

## 5. Metric và cách nối với repo

Repo có [schema/chấm điểm](../core/evaluation.py), [CLI](../scripts/evaluate.py) và [pilot dự thảo](../config/evaluation/hanoi-pilot.json). Pilot hiện 32 ca từ 4 ảnh, chưa phải bộ gold. `score` yêu cầu prediction live, manifest được duyệt và judgment con người gắn hash; không lấy `claims[].verdict` của model làm nhãn đúng/sai.

| Khía cạnh | Đã có trong scorer | Cần bổ sung cho benchmark đầy đủ |
| --- | --- | --- |
| Nhận diện | Precision trên kết quả probable/recognized có nhãn người duyệt | Top-1/top-k theo entity, độ bao phủ, sai quần thể/thành phần, chấp nhận sai ảnh ngoài miền |
| Câu trả lời | Claim precision, accuracy trên slot đã trả lời, coverage, false refusal | Tỷ lệ slot trả lời **đúng** trên mọi slot có thể trả lời; phân tích niên đại/công năng/quan sát |
| Nguồn | Manifest lịch sử yêu cầu source ID, URL và hash | Citation hỗ trợ đúng claim, đủ citation, đúng thực thể/sự kiện và độ tin cậy nguồn |
| Vùng ảnh/OCR | Có artifact trong workflow | Bounding-box IoU, độ đúng grounding theo người duyệt; CER/WER nếu có transcript chuẩn |
| Hỏi bổ sung | Có continuation trong API | Hỏi thừa, lặp hỏi, cải thiện sau câu trả lời bổ sung, xử lý “không biết” |
| Vận hành | Lỗi kỹ thuật, p50/p95 thời gian | Số model/tool call, token/chi phí có usage thực, lỗi provider theo nhóm |

`answerable_slot_coverage` hiện đếm slot đã trả lời trong các slot có đáp án; chưa đảm bảo câu trả lời đó đúng. Luôn đọc cùng accuracy và false refusal, tránh tối ưu coverage bằng cách đoán. Mẫu số bằng 0 phải để null. Lỗi 429/timeout báo riêng, không gộp thành thiếu nguồn hay bỏ âm thầm khỏi mẫu số kết quả toàn luồng.

Khi bắt đầu đánh giá thật ở bước sau, nên so sánh VLM trực tiếp, một agent có retrieval/OCR và luồng LangGraph trên cùng case và điều kiện truy cập nguồn. Ghi ngân sách/thời gian để phân biệt lợi ích kiến trúc với lợi ích do nhiều lượt gọi hơn. Các benchmark quốc tế chỉ đo thành phần hoặc profile đánh giá riêng; không nới chính sách Hà Nội của sản phẩm chỉ để vượt bài test ngoài phạm vi.

Không có adapter nhập các bộ bên ngoài trong lần khảo sát này. Cần chuyển đổi dữ liệu sang `EvaluationCase`, bổ sung quyền ảnh/nguồn/slot rồi duyệt; không sửa manifest thành `reviewed` chỉ dựa trên tuyên bố của dataset card. CLI hiện chưa đủ để chấm hội thoại nhiều lượt, citation và grounding theo các giao thức nêu trên.

## 6. Phiên bản đã tra cứu và việc tiếp theo

Revision Hugging Face đọc qua API metadata:

| Bộ | Revision | Liên kết cố định |
| --- | --- | --- |
| VietTravelVQA v2 | `1aa7c4f3c3bd179b94c3093678515af7f6f3da48` | [Card tại revision](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v2/blob/1aa7c4f3c3bd179b94c3093678515af7f6f3da48/README.md) |
| VietTravelVQA v3 | `75d72d93f12f40756e5dfa0775236d3d78483fa4` | [Card tại revision](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v3/blob/75d72d93f12f40756e5dfa0775236d3d78483fa4/README.md) |

Các bộ còn lại đã đọc trang chính thức ngày tra cứu, chưa pin revision dữ liệu. Bản card/API nhỏ đã đọc lưu local trong `reports/benchmark-survey/` (gitignore); không có ảnh bộ dữ liệu hay kết quả model ở đó.

Thứ tự thực hiện đề xuất:

1. Kiểm kê metadata VietTravelVQA bản đã pin, xác định số thực thể/ảnh/QA thuộc Hà Nội; đối chiếu nguồn và loại phần không phù hợp. Chưa có số lượng Hà Nội đã xác minh trong khảo sát này.
2. Chọn một phiên bản gốc, deduplicate theo ảnh và thực thể, tách QA gốc/QA sinh; chọn 40–50 ca để người duyệt thử rubric.
3. Bổ sung ảnh tự thu thập và nhóm âm tính/ảnh khó/hỏi bổ sung mà bộ công khai không phủ đủ.
4. Hoàn thiện adapter và các metric thiếu, đóng băng test và điều kiện chạy.
5. Chỉ sau đó mới gọi model và lập bảng kết quả đo thật. Hiện chưa có điểm accuracy nào để công bố.
