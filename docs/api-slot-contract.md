# Cập nhật API: kết quả theo từng ý hỏi

Giữ các endpoint `/api/v1`, result schema version 2 và cách chạy job/SSE hiện có. Các trường mới có default để đọc được result cũ; không cần thêm migration ngoài `0005_input_context` đã có. API và worker phải triển khai cùng code/profile.

## Kết quả

`GET /api/v1/runs/{id}/result`, `/evidence`, event `judge` hoàn tất và event terminal của worker có cùng `slot_results`:

```json
{
  "answer_status": "partial",
  "slot_results": [
    {
      "slot_id": "construction",
      "question": "Công trình được khởi dựng khi nào?",
      "evidence_type": "historical",
      "status": "answered",
      "reason_codes": [],
      "claim_ids": ["claim_ID_do_backend_cap"],
      "evidence_ids": ["evidence_ID_do_backend_cap"]
    },
    {
      "slot_id": "restoration",
      "question": "Những mốc trùng tu của công trình có tư liệu đối chiếu là gì?",
      "evidence_type": "historical",
      "status": "unanswered",
      "reason_codes": ["missing_source"],
      "claim_ids": [],
      "evidence_ids": []
    }
  ]
}
```

ID ở ví dụ chỉ minh họa, không phải evidence thật. Nhận diện có thể có evidence IDs mà không có claim ID vì đánh giá recognition tách với claim tuyệt đối.

| Status từng ý | Ý nghĩa |
| --- | --- |
| `answered` | Có phần trả lời được kiểm tra ở mức chắc chắn công khai |
| `partial` | Chỉ trả lời được một phần ý đó |
| `unanswered` | Chưa trả lời được ý đó |
| `unsupported` | Yêu cầu chưa thuộc phạm vi hỗ trợ |
| `conflicted` | Verifier ghi nhận nguồn còn bất đồng về ý đó |

`reason_codes`: `missing_source`, `insufficient_evidence`, `entity_ambiguous`, `image_unreadable`, `identity_unconfirmed`, `unsupported_request`, `source_conflict`, `incomplete_answer`, `verification_unavailable`.

Backend quyết định từ claim đã qua gate, evidence, recognition, phạm vi hỗ trợ và đánh giá completeness của Verifier. Verifier không thể dùng `complete` để hợp thức hóa một slot không có bằng chứng. Nguồn mâu thuẫn được đánh dấu và diễn đạt còn bất đồng; không tự hợp nhất thành một mốc chắc chắn. Đây vẫn là kiểm chứng tự động, cần bộ gold/người duyệt để đo chất lượng.

Coordinator tách từng yêu cầu. Backend bổ sung tách slot lịch sử gộp các mốc khởi dựng/trùng tu/tái dựng khi cả câu hỏi gốc yêu cầu đồng thời và slot cũng chứa các ý đó; không biến “hoặc” thành “và”. Verifier còn đánh giá `slot_assessments` để phát hiện slot chưa đủ ý. Quy tắc từ vựng có giới hạn, không phải bộ phân tích đầy đủ mọi cách diễn đạt.

`accuracy.questions` cấu hình `certainty_terms`, `certainty_negations`, `unknown_answers`, `split_history_slots`, `history_facets`, `facet_questions`. Việc phủ định yêu cầu chắc chắn được kiểm tra trong mệnh đề trước khi áp dụng giới hạn nhận diện. Thay schema Python cần restart tiến trình Streamlit.

## Người dùng chưa biết thông tin bổ sung

```http
POST /api/v1/runs/{id}/clarification
Authorization: Bearer <session token>
Idempotency-Key: <key mới>
Content-Type: application/json
```

```json
{
  "clarification_id": "ID từ câu hỏi đang chờ",
  "revision": 1,
  "response_type": "unknown"
}
```

`response_type` mặc định `answer`; client cũ vẫn gửi `answer`/`selected_candidate`/`asset_id` như trước. `unknown` cho phép không nhập câu trả lời; không được đồng thời chọn ứng viên. Chuỗi như “tôi không biết” cũng được nhận biết theo danh sách cấu hình, nhưng “không biết tên nhưng ảnh chụp ở Mỹ Đức” vẫn giữ thông tin bổ sung, không bị loại toàn bộ theo tiền tố.

Phản hồi chưa biết không trở thành bằng chứng hay xác nhận thực thể. Child run vẫn giữ kết quả parent và giới hạn hội thoại; không hỏi lại cùng điều người dùng không biết. Phần chưa đủ căn cứ được trả qua slot_results để frontend hướng dẫn tiếp. Luồng hiện tại vẫn đi qua graph và giới hạn model; chưa tối ưu thành child không gọi model cho trường hợp hoàn toàn không có thông tin mới.

Streamlit có lựa chọn “Tôi chưa biết thông tin này” và bảng “Kết quả theo từng ý hỏi”. Postman dùng `clarification_response_type=unknown`. Phần Hán–Nôm chưa hỗ trợ được tách khỏi phần kiến trúc/lịch sử được hỗ trợ khi phân biệt được các mệnh đề.

## Triển khai

```powershell
docker compose -f compose.yaml -f compose.evidence.yaml up -d --build api worker
```

File override chọn `config/hanoi-evidence.yaml` cho cả API và worker; có thể đổi bằng `HERITAGE_EVIDENCE_CONFIG` hoặc tắt bằng `HERITAGE_ACCURACY_ENABLED=false`. Không đổi hoặc in credential trong `.env`.

Trước deploy: kiểm tra active job, sao lưu PostgreSQL và ghi image ID để có đường quay lại. Giữ nguyên volume DB/media. Chạy migration mới trước khi nhận job mới; xem lại result cũ phải hoạt động, còn review lại cần đúng profile đã tạo parent. Không chạy worker cũ với API mới.

Kiểm tra `/health/ready`, `/openapi.json` (37 operations), `/api/v1/capabilities` và Swagger `/docs`. Dùng database riêng cho test tự động; kiểm tra HTTP demo không gọi Gemini và không phải phép đo độ đúng lịch sử.

## Kết quả xác nhận 16/11/2026

- 250 tests offline đạt, Ruff check/format đạt; 65 tests PostgreSQL đạt trên container/database riêng đã dọn.
- HTTP demo 86/86 trường hợp đạt, phủ 37/37 operations. Swagger/Postman đã đồng bộ, collection có 40 requests.
- API/worker local đã chạy cùng image mới, profile bằng chứng bật; PostgreSQL ở `0005_input_context`. Database gốc đã sao lưu, image trước triển khai được giữ, volume DB/media được bảo toàn.
- Một lệnh migration riêng ban đầu dùng nhầm Settings mặc định tạo SQLite rỗng; đã sửa sang `Settings.from_env()`, xác nhận migration trên PostgreSQL và dọn đúng SQLite rỗng vừa tạo sau khi kiểm tra thời điểm tạo/đường dẫn/bảng không có dữ liệu.
- API local từ 33 lên 37 operations; `/health/ready` trả 200 và OpenAPI công khai `slot_results`, `response_type` mới.
- Hai lượt gọi Gemini thật qua API gặp HTTP 429: lượt đầu chưa hoàn tất Judge, lượt sau dừng sớm và không đủ artifact để review. Không báo đây là kết quả live đạt hay độ chính xác đã đo; không tiếp tục gọi model để chọn một lần thành công.

Lỗi model/provider được trả `verification_unavailable` với lý do kỹ thuật từng ý; không ngụy trang thành thiếu bằng chứng. Nếu coordinator chưa tách được câu hỏi vì lỗi kỹ thuật, backend giữ câu hỏi gốc thành một slot lỗi. Trường hợp chưa tạo được bản nháp không được review; cần retry khi dịch vụ model cho phép. Bản ghi runtime nằm ở `reports/api-slot-contract/` (bị gitignore).
