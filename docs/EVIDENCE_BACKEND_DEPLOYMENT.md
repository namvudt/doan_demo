# Backend evidence: hợp đồng API và triển khai

Backend evidence-v2 được tách trên nền `origin/main`, kết hợp catalog và các
nhóm API sản phẩm. [Phạm vi tách nhánh](BACKEND_ISOLATION.md) ghi rõ base và
các phần giao diện được giữ ngoài change set.

## Phiên bản và hợp đồng

- Tiền tố HTTP giữ nguyên `/api/v1`.
- OpenAPI hiện có `info.version=1.2.0`, 81 operations; Postman có 84 requests.
- `result_schema_version=2` biểu thị kết quả evidence. Kết quả cũ được đọc theo
  version 1 với các trường bằng chứng rỗng/mặc định.
- `X-Backend-Build` nhận diện build khi đặt `HERITAGE_BUILD_REVISION`.
- API và worker cần cùng code/profile. Root Compose chọn
  `config/hanoi-evidence.yaml`; launcher local chọn bằng `--profile`.

| Tính năng | API |
| --- | --- |
| Gợi ý có provenance, vùng chú ý | `POST /api/v1/runs`: location_hint, focus_box |
| Nhận diện, claim và bằng chứng | `GET /api/v1/runs/{id}/result`, `…/{id}/evidence` |
| Crop thuộc owner của run | `GET …/{id}/regions/{region_id}/image` |
| Đọc yêu cầu bổ sung | `GET …/{id}/clarification` |
| Tạo child có revision/idempotency | `POST …/{id}/clarification` |
| Quan sát và phục hồi | SSE, history, steps, metrics, retry, Judge-only review, recovery/resume |

`awaiting_input` kết thúc một đoạn polling/SSE và chờ hành động người dùng.
Continuation tạo run con và giữ kết quả parent bất biến; thay input phải có
revision và `Idempotency-Key` hợp lệ. Chi tiết:
[accuracy profile](accuracy-profile.md), [API server](api-server.md).

## Chạy riêng và triển khai

```powershell
uv sync --locked --group dev
uv run --locked python -m scripts.serve_api --demo --profile hanoi-evidence --port 8001
```

Demo dùng DB/media riêng trong `.api-demo/interactive`, không gọi provider
trả phí. Catalog cần được nhập riêng; xem
[media do người vận hành cung cấp và seed](CATALOG_DATABASE.md).
Root Docker Compose và credential được hướng dẫn trong [README](../README.md).

Hai revision `0005_heritage_catalog` và `0005_input_context` cùng nối tiếp
`0004_review_runs`. `0006_merge_evidence_catalog` hợp nhất cả hai; các revision
sau nối tới head `0009_runtime_state`. Không đổi ID migration đã áp dụng.

Sao lưu DB, assets và media trước triển khai. Đổi image không tự hoàn tác schema;
thử restore vào DB/volume mới với image tương thích trước khi chuyển traffic.
Rollback chức năng bằng `HERITAGE_ACCURACY_ENABLED=false` chỉ tác động run mới,
không xóa migration hoặc viết lại result cũ.

## Kiểm chứng

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m scripts.api_contract_report
uv run --locked pytest tests/test_postman_export.py
```

HTTP contract report tạo API/worker demo riêng và dữ liệu fixture riêng; report
nằm trong vùng Git bỏ qua. PostgreSQL tests dùng `API_TEST_DATABASE_URL` và
schema test riêng, không trỏ vào DB sử dụng thật.

`scripts.evidence_deployment_check` là smoke cho server demo loopback **đã có
catalog seed**. Nó kiểm tra build, routes, DTO, ảnh/crop, ownership, SSE,
idempotency và parent bất biến; không chứng minh độ đúng lịch sử. Mặc định
công cụ so OpenAPI đang chạy với các route từ source hiện tại, không phụ
thuộc lịch sử Git hoặc một commit ngoài nhánh. Có thể truyền
`--reference <checkout-tham-chieu>` để kiểm tra thêm các route của checkout
baseline tường minh. Công cụ tạo dữ liệu QA demo và thu hồi session do nó tạo.

## Giới hạn

DTO/test đạt không chứng minh chất lượng nhận diện. Demo không nhận diện thật;
pending mô phỏng không thay thế một continuation model thật. Nguồn công bố,
entity binding, ảnh và bộ gold cần người duyệt. Quy trình đánh giá ở
[QUALITY_ACCEPTANCE.md](QUALITY_ACCEPTANCE.md). Kết quả kiểm chứng của nhánh
tách được ghi riêng tại [BACKEND_ISOLATION.md](BACKEND_ISOLATION.md).
