# Catalog di sản lưu trong cơ sở dữ liệu

Catalog cung cấp danh sách, chi tiết, ảnh và tọa độ từ DB. Các ID là chuỗi ổn
định, không giả định UUID. API công khai chỉ trả bản ghi `published`.

## Mô hình dữ liệu và giới hạn

Migration `0005_heritage_catalog` nối tiếp `0004_review_runs`, bổ sung
`heritage_sites`, `heritage_site_information`, `heritage_site_media` và
`heritage_content_sources`. Head hiện tại là `0009_runtime_state`; nhánh
catalog và evidence được hợp nhất bằng `0006_merge_evidence_catalog`.

Tọa độ phải có đủ latitude/longitude trong khoảng hợp lệ. Nhãn `verified` yêu
cầu bản ghi không phải minh họa, ghi chú đối chiếu và nguồn đã xác minh. Backend
kiểm tra metadata được nhập, không tự xác minh tính chính xác ngoài đời.

[samples/catalog/heritages.json](../samples/catalog/heritages.json) chứa 8 bản
ghi: 7 công bố và 1 bản nháp. ID `preview-heritage-…` được giữ để link ổn định;
nội dung và tọa độ vẫn là minh họa. Metadata nguồn có
`index_status=not_indexed`: seed không tải nguồn hoặc tự biến link thành evidence.
Nguồn có nội dung được duyệt/công bố có quy trình riêng trong
[backend sản phẩm](PRODUCT_PLATFORM_DEPLOYMENT.md).

## Ảnh do người vận hành cung cấp

`API_CATALOG_MEDIA_DIR` mặc định trỏ tới `catalog-media/` ở gốc repository.
Nhánh backend không chứa ảnh hoặc mã frontend. Người vận hành chuẩn bị ảnh có
quyền sử dụng phù hợp, giữ metadata nguồn/giấy phép, rồi đặt tên theo seed:

- `demo-thap-rua.jpg`
- `van-mieu.jpg`
- `hoang-thanh.jpg`
- `chua-mot-cot.jpg`
- `co-do-hue.jpg`
- `hoi-an.jpg`
- `my-son.jpg`

API chỉ nhận tên tệp JPEG/PNG/WebP trong thư mục cấu hình; không nhận đường dẫn
tùy ý hoặc tự tải ảnh ngoài. Ảnh editor upload nằm riêng trong
`API_DATA_DIR/catalog-media`; asset của người dùng vẫn có ownership riêng.

Chạy từ gốc repository, với thư mục ảnh đã chuẩn bị:

```powershell
$env:API_CATALOG_MEDIA_DIR = "D:/heritage/catalog-media"
uv run --locked python -m scripts.seed_catalog --dry-run
```

`--dry-run` kiểm tra schema, ID trùng và đủ ảnh trước khi kết nối DB/migrate.
Thiếu ảnh hoặc đường dẫn không hợp lệ làm lệnh thất bại; không tạo bản ghi seed.
Không lấy tên tệp làm bằng chứng rằng ảnh đã được nhận diện hoặc cấp phép.

Khi chạy bằng Docker, đường dẫn môi trường là đường dẫn **trong container**.
Mount thư mục ảnh đã chuẩn bị ở chế độ chỉ đọc vào cùng đường dẫn trong cả API
và worker, rồi đặt `API_CATALOG_MEDIA_DIR` tương ứng. Ví dụ Compose override:

```yaml
services:
  api:
    environment:
      API_CATALOG_MEDIA_DIR: /app/catalog-media
    volumes:
      - "D:/heritage/catalog-media:/app/catalog-media:ro"
  worker:
    environment:
      API_CATALOG_MEDIA_DIR: /app/catalog-media
    volumes:
      - "D:/heritage/catalog-media:/app/catalog-media:ro"
```

Lưu override tại vị trí local được Git bỏ qua, rồi truyền cùng root
`compose.yaml` khi chạy mọi lệnh Compose. Không đưa ảnh riêng tư hoặc override
chứa credential vào commit.

## Seed và bảo toàn dữ liệu

Root `compose.yaml` chạy PostgreSQL, API và worker; cấu hình credential theo
[README](../README.md). Với cùng các file Compose/override đã dùng để khởi động:

```powershell
docker compose exec -T api python -m scripts.seed_catalog --dry-run
docker compose exec -T api python -m scripts.seed_catalog
```

Thêm `-f compose.yaml -f <override-local>` nếu dùng override có tên tùy chọn.
Lệnh seed migrate tới head và nhập theo stable ID. Mặc định giữ bản ghi đã tồn
tại; `--replace` là lựa chọn ghi đè tường minh. Sao lưu DB và vùng ảnh trước
khi nâng cấp; không reset DB hoặc xóa volume để giải quyết migration.

## Hợp đồng API

| Endpoint | Quyền và hành vi |
| --- | --- |
| `GET /api/v1/heritages` | Công khai; phân trang, lọc bản ghi published |
| `GET /api/v1/heritages/{id}` | Công khai; chi tiết published |
| `GET /api/v1/heritages/{id}/media/{media_id}/content` | Công khai; ảnh published |
| `POST /api/v1/heritages/{id}/media/{media_id}/assets` | Owner đã xác thực; tạo asset riêng, không gọi model |
| `POST /api/v1/operations/heritages` | Editor/admin hoặc operations bearer; tạo |
| `PUT /api/v1/operations/heritages/{id}` | Editor/admin hoặc operations bearer; thay theo version |

Danh sách nhận `q`, `province`, `category`, `has_location`, `limit`
(mặc định 100, tối đa 500), `offset`; trả
`{items,total,limit,offset,has_more}`. Ghi đè thiếu version trả 428; version cũ
trả 409. Guest không được biên tập. Operations token chỉ thuộc server.

Khả năng catalog được công bố qua `capabilities.features.heritage_catalog`.
Các API upload/thay/xóa media, entity binding và audit nằm trong OpenAPI và
[Postman](postman.md). Tạo asset từ ảnh catalog không tự tạo run AI.