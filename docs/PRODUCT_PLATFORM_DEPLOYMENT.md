# Backend sản phẩm: dữ liệu, tài khoản và phục hồi

Backend mở rộng evidence-v2/catalog bằng migration
`0007_accounts_product`, `0008_content_platform` và
`0009_runtime_state`. OpenAPI 1.2.0 có 81 operations, Postman 84 requests;
tiền tố HTTP giữ nguyên `/api/v1`.

## Các nhóm API

| Nhóm | Hành vi backend |
| --- | --- |
| Tài khoản | Scrypt password, opaque access/refresh token được băm, rotation, role user/editor/admin |
| Hội thoại và favorites | Owner ổn định, conversation/turn/message, memory opt-in có giới hạn, favorites di tích riêng bookmark run |
| Catalog/entity | Metadata/ảnh/tọa độ từ DB; heritage_id và entity binding có provenance |
| Nguồn và media | Source/version draft → review → publish/withdraw, revision conflict, audit, kiểm tra upload và đường dẫn |
| Retrieval cache | Artifact nguồn công khai dùng chung giữa tiến trình, TTL/bounded payload và invalidation theo revision |
| Vòng đời | Soft-delete run, bảo vệ lineage, retention plan/apply, dọn guest hết hạn và asset không còn tham chiếu |
| Phục hồi | Completed-node checkpoint, input/config/build/source signatures, lease fencing và ngân sách ban đầu |
| Nghiệm thu AI | HTTP runner live opt-in, trần attempts, prediction/hash/latency, chấm bằng người duyệt |

Swagger mô tả từng request/response và quyền; [Postman](postman.md) mặc định
tắt model calls, account/editorial writes, role changes và thao tác xóa.
Đây là API/backend quản trị; giao diện CMS nằm ngoài nhánh này.

## Danh tính và quyền sở hữu

Đăng ký công khai chỉ tạo role `user`. Role được đọc lại từ DB khi kiểm tra
quyền; editor/admin hoặc operations bearer mới được biên tập, admin hoặc
operations bearer mới được gán role. Bootstrap/operations token thuộc server.

Owner tài khoản ổn định giữa các lần đăng nhập. Refresh xoay token; logout thu
hồi phiên thiết bị hiện tại. Guest giữ ownership/session riêng. Conversation
tách khỏi ancestry retry/review/clarification; xóa hội thoại không tự xóa run.

Memory mặc định tắt, tối đa 8 message/4.000 ký tự. Ngữ cảnh có provenance và
không trở thành bằng chứng đã kiểm chứng. Quên memory áp dụng cho run mới;
không sửa snapshot của run đã queue. Favorites di tích tách khỏi bookmark run.

## Tư liệu, ảnh và cache

Catalog metadata nguồn không đồng nghĩa nội dung đã được nhập/duyệt để retrieval.
Tên di tích, nhãn sample và lời người dùng là gợi ý có provenance. Source version
giữ text/hash/nguồn gốc; publication được kiểm tra trong transaction. Draft hoặc
version bị withdraw không được retrieval sử dụng.

Publish/withdraw/entity binding thay revision; cache cũ không còn được dùng.
Cache lưu SourceRecord công khai được whitelist, không lưu token, model output
hoặc draft source. Nó không bỏ qua Verifier hay dùng lại suy luận model.

Ảnh catalog do người vận hành cấp qua `API_CATALOG_MEDIA_DIR` (mặc định
`catalog-media/`), độc lập frontend. Upload của editor nằm ở vùng writable
`API_DATA_DIR/catalog-media`. Xem [cấu hình ảnh và seed](CATALOG_DATABASE.md).

## Vòng đời và checkpoint

`DELETE /runs/{id}` ẩn run thuộc owner. Run đang hoạt động cần được hủy trước;
parent còn descendant chưa xóa trả 409. Purge bảo vệ owner tài khoản, active jobs,
lineage và asset còn tham chiếu. Lệnh mặc định chỉ tạo kế hoạch:

```powershell
docker compose exec -T api python -m scripts.purge_data
```

Dùng cùng các file Compose/override đã chọn khi khởi động. Chỉ thêm `--apply`
sau khi kiểm tra kế hoạch và bản sao dữ liệu phù hợp. Không dùng volume prune
để thay cho retention.

Replay chỉ dùng node hoàn tất có input/config/build/source signature khớp,
lease hiện tại và ngân sách còn lại. Attempts đã ghi vẫn tính vào budget;
thời gian sau crash không được reset. External call bị ngắt có thể phải chạy
lại, không có cam kết exactly-once với provider.

## Triển khai và kiểm chứng

Dùng root [compose.yaml](../compose.yaml), hướng dẫn credential/build/readiness
ở [README](../README.md), và mount ảnh catalog riêng nếu nhập seed. API/worker
cần cùng code, build revision và profile. Không reset DB hoặc đổi migration ID.

```powershell
uv run --locked pytest
uv run --locked python -m scripts.api_contract_report
uv run --locked pytest tests/test_postman_export.py
```

HTTP report tạo API/worker demo và fixture riêng. Source review/publish/recovery
fixtures tổng hợp chỉ kiểm tra phần mềm, không phải gold lịch sử. Kiểm thử
PostgreSQL dùng DB/schema riêng. Xem [phạm vi và validation](BACKEND_ISOLATION.md).

`scripts.verify_backup` được giữ như công cụ restore rehearsal cho **deployment
demo legacy**: project `heritage-fe-local`, DB container/network cố định và
image `heritage-frontend-backend:*` hoặc image digest local. Nó không tự tìm
hoặc phục hồi root Compose ở deployment khác. Các bài test safety không gọi
Docker. Khi áp dụng cho deployment mới cần kế hoạch backup/restore phù hợp
với DB, assets và media thực tế.

Nghiệm thu model thật và bộ ca do người duyệt được hướng dẫn ở
[QUALITY_ACCEPTANCE.md](QUALITY_ACCEPTANCE.md). Không công bố accuracy từ demo,
nhãn draft hoặc verdict model; vài ca smoke không đại diện benchmark tải.
