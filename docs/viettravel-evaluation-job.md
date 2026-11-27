# Job đánh giá VietTravelVQA

## Bản sửa sau phân tích log 6 câu

Job so sánh `viettravel-validation-small-v2` dùng lại đúng manifest của `small-v1`, không ghi đè kết quả cũ. Cấu hình tạo job: `config/evaluation/viettravel-small-job-v2.yaml`. Các câu này đã được dùng để phát triển luồng; kết quả v2 là hồi quy trên validation, không phải đánh giá test độc lập.

Profile hiện dùng catalog nhãn Việt Nam kế thừa Hà Nội, không chứa đáp án benchmark. Chủ thể được nêu rõ trong câu hỏi tách khỏi nhận diện ảnh; quốc gia và giá trị đáp án không trở thành ứng viên công trình. Quan sát ảnh hoàn tất trước tra cứu; bất đồng nhận diện có tối đa một lượt đối chiếu theo `recognition.max_disambiguation_rounds`.

Verifier bắt buộc trả `claims` và `slot_assessments`; slot visual/kiến thức báo `complete` phải có claim supported. `verifier_contract_retries` giới hạn một lần sửa cấu trúc; lỗi lặp lại trả `invalid_verifier_response`, không âm thầm chuyển thành thiếu nguồn. Output đề xuất, lỗi hợp đồng và claim sau gate nằm trong `node_metadata.judge.review_diagnostics`; SSE/API steps và LangSmith có dữ liệu tương ứng được lọc credential.

Tra cứu có `relation_aware`, `require_relation_coverage`, `relation_rules`, `max_http_requests`. Tín hiệu coverage chỉ sàng lọc ứng viên nguồn bằng từ khóa, không chứng nhận đúng sự kiện. Recovery bỏ query đã chạy và dùng ngân sách HTTP còn lại. Câu hỏi gần nhất cần phạm vi so sánh cùng bằng chứng khoảng cách; hệ thống không lấy graph/reference benchmark làm nguồn trả lời.

Đếm bật `perception.require_count_grounding`: mỗi instance có loại đối tượng, mức xác định và box `x_min,y_min,x_max,y_max`. Backend chặn box mâu thuẫn hướng, trùng instance, loại chưa chắc và tổng không khớp; không tự đảo x/y. Giới hạn 20 observations/refs; số 0 chưa có bằng chứng phủ định toàn cảnh sẽ không tự được coi là đúng. Grounding vẫn phụ thuộc model và cần duyệt ảnh khi lớp đối tượng không rõ.

Các mã `no_retrieved_sources`, `no_supporting_source`, `invalid_visual_grounding`, `count_grounding_missing`, `object_class_uncertain` làm rõ nguyên nhân. `missing_source` còn giữ để client cũ đọc được; nó không khẳng định hệ thống chưa lấy nguồn.

```powershell
uv run --locked python -m scripts.evaluation_job create --definition config/evaluation/viettravel-small-job-v2.yaml --manifest data/evaluation/viettravel/75d72d93f12f40756e5dfa0775236d3d78483fa4/validation-small-v1.json
uv run --locked python -m scripts.evaluation_job run reports/evaluation/jobs/viettravel-validation-small-v2 --live
```

Job v2 giữ khoảng cách 30 giây/request và 20 giây/case, giới hạn 54 request để có chỗ cho recheck/repair. 429 dừng và cooldown; 503 theo fallback có giới hạn như v1. Không khởi động job toàn bộ test trong đợt này.

### Kiểm tra lại quan hệ trong quotation

`small-v2` hoàn tất 6/6 nhưng việc đọc từng quotation phát hiện hai claim quốc gia dùng đoạn không trực tiếp chứng minh quan hệ, cùng một câu “gần nhất” bị thay bằng địa hình xung quanh. Không coi trạng thái `answered` hoặc đáp án xếp hạng trùng chuỗi là độ đúng: case Bút Tháp trong v2 nhận diện thành Chùa Keo dù tên hạng di tích trùng tham chiếu.

Job `viettravel-validation-relations-v3` chạy lại 3 ca Lý Sơn, Sơn La và Mũi Cà Mau sau sửa, giữ dữ liệu v1/v2 nguyên trạng. Manifest subset bảo toàn provenance và đánh dấu cả ba là đã dùng để phát triển. Các kết quả chỉ dùng kiểm thử hồi quy; các chỉ số chuỗi của phần đã xem không được dùng để tuyên bố accuracy độc lập.

`claim_policy.require_relation_quote` yêu cầu quotation chứng minh đúng quan hệ trong câu hỏi. `source_relation_rules` cho phép thay các mẫu hỏi, mẫu nhận diện object và mẫu quotation bằng cấu hình; `{subject}`/`{object}` là placeholder được escape khi khớp tên. Các gate chỉ bao phủ một số cấu trúc quốc gia và gần nhất, không phải bộ chứng minh ngữ nghĩa tổng quát. Nếu câu diễn đạt không được hỗ trợ thì giữ thiếu căn cứ, không tự nới để khớp nhãn benchmark.

`questions.nearest_patterns`, `nearest_terms`, `nearest_scope_terms`, `require_nearest_scope` điều khiển nhận diện câu so sánh gần nhất. Luồng giữ lại điều kiện gốc khi Coordinator làm mất; thiếu phạm vi so sánh thì hỏi phạm vi/danh sách, không hỏi lại danh tính nếu danh tính không phải nút thắt. Chỉ có khoảng cách tới một điểm chưa chứng minh điểm đó gần nhất trong tập đang xét.

```powershell
uv run --locked python -m scripts.evaluation_job create --definition config/evaluation/viettravel-relation-retest.yaml --manifest data/evaluation/viettravel/75d72d93f12f40756e5dfa0775236d3d78483fa4/validation-relations-v3.json
uv run --locked python -m scripts.evaluation_job run reports/evaluation/jobs/viettravel-validation-relations-v3 --live
```

Job `viettravel-validation-small-v1` dùng **6 câu validation**, chọn theo seed `20261127` từ revision `75d72d93f12f40756e5dfa0775236d3d78483fa4`: 2 câu mỗi nhóm `original`, `kg_generated`, `graph_generated`, trên 6 ảnh khác nhau. Loại các câu và nguồn ảnh trùng với nhóm calibration trước. Đây là phép thử kỹ thuật và khám phá, không đại diện cho toàn bộ dữ liệu; split theo ảnh vẫn có thể trùng di tích, biến thể ảnh hoặc kiến thức đã học.

Profile `config/evaluation/viettravel-adapted.yaml` tách khả năng nhìn cảnh với đọc chữ, chỉ kích hoạt OCR khi câu hỏi có dấu hiệu cần đọc chữ, hướng dẫn box và ID bằng chứng, ưu tiên câu trả lời ngắn. Các gate nguồn và bằng chứng vẫn được áp dụng. Đây là điều chỉnh prompt/luồng, chưa huấn luyện trọng số.

Đợt mẫu trước trên 3 câu validation cho thấy baseline gặp 2 lỗi 504 và trả lời một câu đếm tháp. Sau điều chỉnh, hệ thống nhận diện và đếm tháp được; câu lịch sử ban đầu bị từ chối do Verifier dùng nhầm source ID làm evidence ID. Sau khi làm rõ hợp đồng ID, một lượt review tái sử dụng ảnh và nguồn đã trả lời được có citation. Khác biệt về timeout và provider khiến các lượt này chưa đủ để kết luận mức cải thiện accuracy. Kết quả và nguồn gốc local ở `reports/evaluation/viettravel-adaptation-20261127/`.

Job giãn **30 giây giữa các request generation**, 20 giây giữa các câu; qua ranh giới shard hoặc resume vẫn giữ giới hạn 30 giây. Độ trễ thực tế có thể dài hơn. Lỗi 503 dùng khóa dự phòng sau chờ và lưu slot credential, không lưu khóa; 429 tạm dừng với cooldown, không đổi khóa để vượt quota. Giới hạn job nhỏ là 36 request, 4 giờ và 2 lần nghỉ tăng dần khi 503. Ba lỗi kỹ thuật liên tiếp sẽ tạm dừng. Các giới hạn này không kiểm soát ứng dụng khác dùng chung project/key.

Các trường `reference_exact_match` và `reference_token_f1` chỉ so khớp chuỗi với câu trả lời upstream đã bỏ dấu; không phải metric chính thức, không phải độ chính xác lịch sử được người duyệt. Cần đối chiếu từng kết quả, nguồn, khả năng trả lời và lỗi kỹ thuật. Dữ liệu KG sinh tự động chưa được duyệt; kết quả lỗi kỹ thuật không được coi là đáp án lịch sử sai.

## Theo dõi và điều khiển

Tại thư mục repo:

```powershell
uv run --locked python -m scripts.evaluation_job status reports/evaluation/jobs/viettravel-validation-small-v1
uv run --locked python -m scripts.evaluation_job pause reports/evaluation/jobs/viettravel-validation-small-v1
```

Lệnh pause yêu cầu dừng sau case đang xử lý; không gửi thêm case sau khi nhận yêu cầu. Trạng thái/case, thời điểm request, hạn mức và kết quả được ghi vào thư mục job trong `reports/`, bị gitignore. Đọc `summary.json`, `state.json` và `shards/*/predictions.json`; ảnh và reference được giữ trong `data/evaluation/` bị gitignore.

Nếu job dừng với cooldown hoặc lỗi kỹ thuật, xem state và nguyên nhân trước khi tiếp tục. Resume bỏ qua case đã ghi, kể cả case thất bại; vì vậy phải báo số case lỗi riêng. Khi tiến trình bị dừng đột ngột, checkpoint có `active_case_id` và file `.lock` có thể còn lại. Xác minh tiến trình PID đã kết thúc và lưu trạng thái trước khi xử lý thủ công; không tự xóa lock hay replay case đang dở vì request có thể đã được tính phí.

Job test đầy đủ 1.893 câu chỉ được tạo sẵn; không được khởi động trong đợt thử nhỏ này. Khi cần tạo job mới, chọn manifest, config, ngân sách và split rõ ràng; không dùng các câu test đã xem như test độc lập. Với toàn bộ test, 20 case đã xem hoặc có chung URL nguồn ảnh với calibration được đánh dấu, nhưng cách so URL chưa phát hiện mọi ảnh trùng và thực thể trùng.

## Tái tạo job nhỏ

```powershell
uv run --locked python -m scripts.prepare_viettravel_small
uv run --locked python -m scripts.evaluation_job create --definition config/evaluation/viettravel-small-job.yaml --manifest data/evaluation/viettravel/75d72d93f12f40756e5dfa0775236d3d78483fa4/validation-small-v1.json
uv run --locked python -m scripts.evaluation_job run reports/evaluation/jobs/viettravel-validation-small-v1 --live
```

Lệnh `create` từ chối ghi đè job đã tồn tại. Job ghi hash manifest, cấu hình và code engine; nếu code hoặc cấu hình thay đổi, cần tạo job so sánh riêng để kết quả có thể tái lập. Khóa dự phòng chỉ cấu hình bằng `GEMINI_FALLBACK_API_KEY` trong `.env` local.
