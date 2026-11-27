# Evaluation nhỏ, gọi Gemini có khoảng nghỉ

Nhánh: `eval/hanoi-small-batch`. Đợt đầu chọn 3 câu hỏi từ VietTravelVQA v3, revision `75d72d93f12f40756e5dfa0775236d3d78483fa4`, thuộc test split gốc. Chọn phần `original`, không lấy câu do KG sinh.

[Kết quả live ngày 16/11/2026 và các lỗi quan sát được](evaluation-smoke-results.md).

| Case | Loại | Câu hỏi giữ nguyên từ dữ liệu |
| --- | --- | --- |
| `VN_003358_q3` | Nhận diện | Ngọn tháp màu đỏ trong ảnh thuộc ngôi chùa nào? |
| `VN_002260_q2` | Quan sát | Mặt tiền nhà thờ có bao nhiêu cánh cửa ra vào chính có vòm? |
| `VN_003358_q4` | Lịch sử/văn hóa | Ngôi chùa Chấn Quốc trong ảnh được biết đến với ý nghĩa văn hóa và lịch sử nổi bật nào? |

Câu cuối giữ lỗi gõ “Chấn Quốc” của dữ liệu. Hai ảnh được tải từ bản đã pin và kiểm tra xem được. Đáp án upstream chỉ là tham chiếu; manifest vẫn `draft`, quyền/attribution từng ảnh chưa được duyệt đầy đủ, chưa có chuyên gia duyệt lịch sử. Không công bố accuracy từ ba ca này.

Nguồn: [VietTravelVQA v3](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v3), [card tại revision](https://huggingface.co/datasets/phunguyendinhkh/VietTravelVQA-v3/blob/75d72d93f12f40756e5dfa0775236d3d78483fa4/README.md). Bộ phát hành ghi CC BY 4.0; từng ảnh giữ giấy phép nguồn Wikimedia Commons. Script giữ metadata/provenance, không đưa ảnh vào Git.

## Hạn chế 429

- Mỗi thời điểm chỉ có một request generation, kể cả khi graph mở nhiều nhánh agent.
- Tối thiểu 30 giây giữa thời điểm bắt đầu hai request; nghỉ 60 giây giữa hai case.
- Không retry lỗi tạm thời trong gateway của evaluation; không đổi provider ngầm. Retry tăng output limit vẫn có giới hạn và đi qua cùng bộ điều tiết.
- Gặp 429: lưu kết quả lần thử, dừng batch; các node còn lại không gửi thêm generation. Lưu thời điểm có thể thử lại, tối thiểu 90 giây hoặc lâu hơn theo Retry-After/RetryInfo của provider.
- Tối đa 3 case và 24 request generation trong một batch, tính cả request thất bại. Số request đã dùng tiếp tục được tính khi resume cùng output.
- Lưu JSON sau từng case và checkpoint trước mỗi request, khóa output để tránh chạy trùng cùng file. Resume không tự chạy lại các case đã có bản ghi, kể cả case thất bại; nếu process ngắt giữa case thì yêu cầu kiểm tra thay vì tự phát lại lời gọi trả phí.

[Google mô tả giới hạn theo RPM, TPM, RPD và project/tier](https://ai.google.dev/gemini-api/docs/rate-limits). Khoảng nghỉ có thể giảm request dồn, không bảo đảm hết 429 khi hết quota ngày, giới hạn chi tiêu hoặc thiếu năng lực phục vụ. Bộ điều tiết ở đây chỉ quản lý process evaluation; ứng dụng khác dùng cùng project vẫn có thể tiêu thụ chung quota.

Điều chỉnh nhịp trong [pacing.yaml](../config/evaluation/pacing.yaml). Profile [hanoi-paced.yaml](../config/evaluation/hanoi-paced.yaml) kế thừa luồng bằng chứng, tăng deadline lên 600 giây để chờ giữa các lượt, request timeout 60 giây. Không sửa `.env`, provider/model hiện có, prompt nghiệp vụ hay API/Streamlit đang chạy.

Giữ 3 graph workers cho cơ chế streaming; chỉ request generation bị tuần tự hóa. Đã tái hiện trường hợp `max_concurrency=1` làm queue streaming chiếm worker và chờ vô hạn trước generation; profile mới tránh cấu hình đó và có kiểm thử graph demo với timeout.

## Chuẩn bị và chạy

Chạy tại thư mục repo:

```powershell
uv run --locked python -m scripts.prepare_viettravel_smoke
uv run --locked python -m scripts.evaluate run data/evaluation/viettravel-smoke/manifest.json --live --allow-draft --limit 3 --config config/evaluation/hanoi-paced.yaml --policy config/evaluation/pacing.yaml --output reports/evaluation/viettravel-smoke-20261116/predictions.json
```

Script chuẩn bị chỉ tải metadata và 2 ảnh cần dùng, đối chiếu câu hỏi/đáp án với test split đã pin. Model chỉ nhận ảnh và câu hỏi, không nhận đáp án, tên file hay entity group của manifest.

Kết quả local, được gitignore:

- `data/evaluation/viettravel-smoke/manifest.json`: 3 case dự thảo.
- `data/evaluation/viettravel-smoke/provenance.json`: nguồn, revision, hash ảnh/metadata, tham chiếu upstream.
- `reports/evaluation/viettravel-smoke-20261116/predictions.json`: đầu ra thật theo case, giai đoạn, claim, nguồn và model calls.
- `reports/evaluation/viettravel-smoke-20261116/predictions.run.json`: trạng thái batch, số lượt gọi, case còn lại và cooldown.

Sau khi cooldown đã hết, có thể tiếp tục những case **chưa có bản ghi** bằng cùng lệnh thêm `--resume`. Không đổi manifest, ảnh hay cấu hình workflow khi resume; runner kiểm tra hash trước khi gọi model. Phải giữ cả predictions và checkpoint; thiếu checkpoint thì từ chối resume vì không xác định được ngân sách đã dùng. Không dùng output mới chỉ để bỏ qua cooldown của project.

```powershell
uv run --locked python -m scripts.evaluate run data/evaluation/viettravel-smoke/manifest.json --live --allow-draft --limit 3 --config config/evaluation/hanoi-paced.yaml --policy config/evaluation/pacing.yaml --output reports/evaluation/viettravel-smoke-20261116/predictions.json --resume
```

Đây là phép thử luồng thật có dữ liệu bên ngoài. Muốn đo chất lượng chính thức cần duyệt nhãn, nguồn và quyền ảnh, chốt split, thêm judgment độc lập rồi mới chạy `score`. CLI từ chối chấm gold trên dữ liệu draft/demo. Xem thêm [khảo sát benchmark](benchmark-survey.md).
