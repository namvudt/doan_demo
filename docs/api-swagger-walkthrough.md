# Hướng dẫn thử từng API trên Swagger

Nếu dùng Postman, có sẵn [collection và environment JSON đầy đủ](postman.md)
với script tự lưu token/ID, polling và SSE.

Hướng dẫn bao phủ 33 HTTP operations. Chạy `python -m scripts.api_contract_report`
để sinh bảng `reports/api-contract/results.md` và request/response đã che token
trong `reports/api-contract/results.json`. Report là artifact local, không commit.
Khi thử lại, tạo phiên, ảnh và run mới theo các bước dưới đây.

Endpoint mới `GET /api/v1/operations/metrics` thuộc nhóm Operations, xuất
Prometheus text. Nó dùng `API_OPERATIONS_TOKEN` riêng thay cho guest access token;
chưa cấu hình trả 503, thiếu/sai token trả 401, token đúng trả 200. Hướng dẫn
log, metrics và thử stack giám sát: [observability.md](observability.md).

## 1. Chuẩn bị và mở Swagger

Tại thư mục `D:\Projects\doan\doan_demo`:

```powershell
uv sync --locked --group dev
uv run --locked python -m scripts.serve_api --demo --port 8001
```

Giữ terminal này chạy, mở <http://127.0.0.1:8001/docs>. Demo đi qua workflow thật
nhưng dùng model và nguồn minh họa; không gọi Gemini/GPU và không phát sinh phí
model. Server live hiện có ở port 8000 có thể tiếp tục chạy đồng thời.

Trong Swagger, mỗi API có một dòng màu: GET xanh dương, POST xanh lá, PUT cam,
DELETE đỏ. Bấm vào dòng → **Try it out** → điền tham số/body → **Execute**.
Xem phần **Server response**, đặc biệt **Code** và **Response body**; phần
**Responses** bên dưới chỉ là mô tả schema, chưa phải kết quả request vừa gửi.

API đầy đủ dùng tiền tố `/api/v1`. Các bảng bên dưới giữ nguyên đường dẫn để
bạn tìm đúng dòng trên Swagger. `asset_id` và `run_id` là path parameter; chúng
khác với query parameter như `limit`, `after`, `include_draft`.

## 2. Kiểm tra hệ thống trước khi tạo dữ liệu

Các API sau chưa cần Bearer token:

| API | Nhập gì | HTTP đúng và cách đọc kết quả |
| --- | --- | --- |
| `GET /health/live` | Không có body | 200, `{"status":"ok"}`: tiến trình API còn hoạt động |
| `GET /health/ready` | Không có body | 200 với `database=true`, `worker=true`; 503 khi chưa có worker/DB chưa sẵn sàng |
| `GET /api/v1/capabilities` | Không có body | 200; kiểm tra `model_mode=demo`, `max_upload_bytes`, `max_image_pixels`, `profiles` |
| `GET /api/v1/samples` | Không có body | 200; `items` chứa các `sample_id`, có `chua_mot_cot` |

`model_configured=true` chỉ báo đã có cấu hình cần thiết. Ở chế độ live, nó chưa
chứng minh key còn quota hoặc model trả lời thành công. Trong lần kiểm thử đã
thực hiện, `/health/ready` được thử cả lúc chưa khởi động worker (503) và sau khi
worker có heartbeat (200); cả hai đều đúng theo trạng thái lúc gọi.

## 3. Cấp token và Authorize

Mở `POST /api/v1/sessions`, nhập:

```json
{
  "label": "Thu Swagger tren may cua toi"
}
```

Nếu `/capabilities` trả `session_bootstrap_required=true`, bấm **Authorize** và
điền giá trị `API_BOOTSTRAP_TOKEN` của server vào ô **APIKeyHeader** trước khi
gọi. Nếu giá trị này là false, có thể để ô đó trống.

Nhận HTTP **201**, body có dạng:

```json
{
  "session_id": "UUID cua phien",
  "access_token": "token thuc te chi duoc tra o buoc nay",
  "token_type": "bearer",
  "expires_at": "thoi diem het han"
}
```

Sao chép đúng giá trị `access_token`, bấm **Authorize** ở đầu Swagger, dán vào ô
**HTTPBearer**, rồi bấm **Authorize** → **Close**. Trong ô này không thêm tiền tố
`Bearer `. Gemini key, LangSmith key và bootstrap token không thay thế access token.

Kiểm tra `GET /api/v1/sessions/me`: phải trả 200 và đúng `session_id`, `label`.
Thiếu Bearer token trả 401/`authentication_required`; token sai hoặc đã thu hồi
trả 401/`invalid_token`.

Sau khi có token, `GET /api/v1/workflow` trả phiên bản, sơ đồ Mermaid và bảy giai
đoạn: scope, coordinate, visual, knowledge, generation, aggregate, judge.

## 4. Tạo ảnh và kiểm tra các API Assets

Chọn một trong hai cách tạo asset:

**Cách A — upload ảnh:** mở `POST /api/v1/assets` → Try it out → ở ô **file** bấm
**Choose File**, chọn JPEG/PNG/WebP → Execute. Đây là multipart upload, không
dán đường dẫn ảnh vào ô JSON. Backend kiểm tra nội dung thực của file, chuẩn hóa
PNG và bỏ EXIF.

**Cách B — dùng ảnh mẫu:** mở `POST /api/v1/samples/{sample_id}/assets`, nhập
`sample_id=chua_mot_cot` → Execute. Không cần request body hoặc upload file.

Cả hai trả HTTP **201**. Sao chép `asset_id` từ response và giữ lại. Các trường
`width`, `height`, `size_bytes`, `sha256`, `media_type`, `content_url` mô tả ảnh
đã chuẩn hóa. Ảnh được test thực tế là PNG **1200 × 896**, **2.123.792 bytes**.

| API | Tham số trên Swagger | Kết quả đúng |
| --- | --- | --- |
| `GET /api/v1/assets` | `limit=50`, `offset=0` | 200; danh sách ảnh thuộc phiên hiện tại |
| `GET /api/v1/assets/{asset_id}` | UUID vừa tạo | 200; metadata của ảnh |
| `GET /api/v1/assets/{asset_id}/content` | Cùng UUID | 200; nội dung binary PNG, có thể tải xuống |
| `DELETE /api/v1/assets/{asset_id}` | UUID của ảnh chưa được run dùng | 204, body trống; GET lại trả 404 |

Muốn thử xóa mà vẫn giữ ảnh cho bước sau, tạo hai asset, chỉ xóa một. Khi ảnh đã
được một run tham chiếu, DELETE trả **409**/`asset_in_use`. Đây là hành vi giữ
nguồn đầu vào của lịch sử, không phải lỗi server.

Các case âm đã kiểm tra: file giả ảnh → 422/`invalid_image`; quá giới hạn upload
→ 413/`image_too_large`; UUID sai định dạng → 422; phiên khác đọc ảnh → 404.

## 5. Tạo lượt hỏi đáp

Mở `POST /api/v1/runs`. Điền header **Idempotency-Key** là một chuỗi dễ nhớ, ví dụ
`swagger-demo-001`. Body:

```json
{
  "asset_id": "THAY_BANG_ASSET_ID_VUA_TAO",
  "question": "Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?",
  "audience": "tourist",
  "profile": "default"
}
```

Thay placeholder bằng UUID thực từ bước upload. `audience` nhận `tourist` hoặc
`student`; `profile` hiện hỗ trợ `default`. Có thể bỏ `parent_run_id` trong lượt đầu.

Nhận HTTP **202 Accepted**; sao chép `run_id`. API trả `execution_status`,
`events_url`, `result_url` và header `Location`. 202 có nghĩa job đã được tiếp
nhận, chưa có nghĩa đã tạo xong câu trả lời.

Thử Execute lần nữa với **cùng key và cùng body**: nhận lại cùng `run_id`. Nếu
đổi câu hỏi nhưng giữ key, nhận 409/`idempotency_conflict`. Để tạo lượt mới độc
lập, đổi key hoặc để trống header.

Các lỗi đã thử: câu hỏi chỉ có dấu cách → 422; profile lạ → 422; dùng ảnh của
phiên khác → 404; tạo vượt ba active runs/phiên → 429/`queue_limit`.

## 6. Theo dõi và đọc lại lịch sử

| API | Nhập gì | Dữ liệu cần quan sát |
| --- | --- | --- |
| `GET /api/v1/runs/{run_id}` | Run UUID | `execution_status`, `result_status`, `event_count`, `error_type` |
| `GET /api/v1/runs` | `limit=20`, `offset=0`; tùy chọn `execution_status=succeeded` | `items`, `total`; dữ liệu chỉ thuộc phiên hiện tại |
| `GET /api/v1/runs/{run_id}/events/history` | `after=0`, `limit=100`, `include_draft=false` | `items` theo sequence tăng dần, `next_after`, `terminal` |

Trạng thái thực thi đi qua `queued`, `running`, sau đó `succeeded`, `failed` hoặc
`cancelled`; có thể có `cancel_requested`. Trạng thái nội dung là trường riêng,
ví dụ `reviewed`, `unverified`, `insufficient_evidence`.

Khi polling lịch sử sự kiện, request tiếp theo dùng `after` bằng `next_after`
vừa nhận. Hợp nhất theo `sequence`, không nối lại toàn bộ danh sách cũ.
Đặt `include_draft=true` khi chủ động muốn lấy bản nháp tổng hợp chưa đánh giá.

Trong run chính của báo cáo: **21 events**, kết thúc bằng `run.succeeded`,
`execution_status=succeeded`, `result_status=reviewed`. Demo hoàn tất nhanh, nên
GET lần đầu của bạn có thể đã thấy succeeded.

## 7. Thử SSE

Mở `GET /api/v1/runs/{run_id}/events`, điền UUID, `after=0`, `include_draft=false`.
HTTP **200**, Content-Type là `text/event-stream`. Với run đang chạy, Swagger có
thể chờ đến khi stream đóng mới hiện đầy đủ body. Dùng `/events/history` nếu muốn
xem ngay từng đợt JSON trong Swagger.

SSE có các frame theo cấu trúc:

```text
id: 21
event: run.succeeded
data: {"sequence":21,"event":"run.succeeded","data":{"run_id":"...","execution_status":"succeeded","result_status":"reviewed","result_url":"...","sequence":21},"created_at":"..."}
```

Muốn thử kết nối lại, nhập `Last-Event-ID=19` vào ô header tương ứng; chỉ nhận
events có sequence lớn hơn 19. Lần kiểm tra thực tế trả đúng **hai events 20, 21**,
không phát lại 1–19. Mất kết nối theo dõi không tự hủy job.

## 8. Đọc câu trả lời và kết quả từng giai đoạn

| API | Tham số | Kết quả đúng |
| --- | --- | --- |
| `GET /api/v1/runs/{run_id}/result` | `include_intermediate=false` | 200 khi có kết quả; câu trả lời, nguồn, review, duration, usage; `intermediate=null` |
| Cùng `/result` | `include_intermediate=true` | Có `intermediate.draft_response` và `intermediate.stages` |
| `GET /api/v1/runs/{run_id}/steps` | `include_draft=false` | Các snapshot scope/coordinate/visual/knowledge/aggregate/judge và node kỹ thuật; bản nháp aggregate không có `content` |
| Cùng `/steps` | `include_draft=true` | Có thêm nội dung bản nháp aggregate |
| `GET /api/v1/runs/{run_id}/sources` | Không có body | Nguồn đã truy xuất, số thứ tự, `cited`, snippet, URL và metadata |
| `GET /api/v1/runs/{run_id}/metrics` | Không có body | Model calls, provider/model thực, duration, usage, workflow/config hash |

Trước khi run hoàn tất, `/result` trả 409/`run_not_finished`. Run bị hủy trước khi
tạo answer trả 409/`result_unavailable`. Vẫn có thể đọc trạng thái và các events đã lưu.

Kết quả thực của run demo có `status=reviewed`, một nguồn `wiki_demo` và năm lần
gọi mô phỏng cho coordinator/visual/knowledge/aggregator/judge. Tổng token là
`null`, không phải 0: provider demo không cung cấp usage thật. Điểm review trong
demo cũng là dữ liệu mô phỏng, không đo chất lượng nhận diện hay kiến thức lịch sử.

`/steps` hiện có chín mục vì gồm bảy giai đoạn được trình bày và hai node kỹ thuật
`experts_done`, `finish`; generation không được chọn có trạng thái skipped.

## 9. Xuất báo cáo, đánh dấu và phản hồi

**Xuất báo cáo:** `GET /api/v1/runs/{run_id}/export`:

- `format=json`, `include_intermediate=false`: JSON kết quả, nguồn và thông tin tóm tắt.
- `format=markdown`: báo cáo Markdown có thể tải thành file `.md`.
- `include_intermediate=true`: chủ động xuất cả nội dung trung gian chưa đánh giá.

HTTP đúng là 200; header `Content-Disposition` chứa tên file.

**Đánh dấu:** `PUT /api/v1/runs/{run_id}/bookmark`, body:

```json
{"saved": true}
```

Nhận 200 với `bookmarked=true`. Gọi `GET /api/v1/runs?saved_only=true` để tìm lại.
Dùng `{"saved":false}` để bỏ đánh dấu.

**Phản hồi:** `POST /api/v1/runs/{run_id}/feedback`, body:

```json
{
  "rating": "helpful",
  "note": "Nguồn và tiến trình dễ quan sát."
}
```

Nhận 200. `GET /api/v1/runs/{run_id}/feedback` phải trả đúng dữ liệu đã lưu.
`PUT /api/v1/runs/{run_id}/feedback` dùng cùng schema để cập nhật, ví dụ
`rating=needs_review`, `note=Cần đối chiếu thêm nguồn`. Các giá trị rating hợp lệ:
`helpful`, `needs_review`, `unrated`.

## 10. Hủy, retry và thu hồi phiên

Hai API phục vụ chẩn đoán/phục hồi:

1. Sau Authorize, mở `POST /api/v1/preflight`, nhập
   `{"roles":["coordinator","visual","aggregator","judge"],"force":false}`.
   Kiểm tra `ready` và từng phần tử `roles`. HTTP 200 với `ready=false` nghĩa là
   đã kiểm tra thành công nhưng cấu hình/kết nối chưa đạt. Không sinh nội dung.
2. Với run terminal đủ ảnh, draft và nguồn, mở `POST /api/v1/runs/{run_id}/review`,
   điền UUID run gốc và header `Idempotency-Key` mới. Không có body. HTTP 202 trả
   run con với `run_kind=review`; dùng ID con để đọc events/result/metrics.
   Metrics chỉ có Judge (và attempts retry của Judge nếu có). Run gốc giữ nguyên.

Mã lỗi cụ thể và giới hạn preflight: [API server](api-server.md#kiểm-tra-model-và-phục-hồi-judge).

| API | Cần nhập | Kết quả đúng |
| --- | --- | --- |
| `POST /api/v1/runs/{run_id}/cancel` | UUID của run thuộc phiên | 200; queued chuyển cancelled ngay; running có thể chuyển cancel_requested |
| `POST /api/v1/runs/{run_id}/retry` | UUID của run đã kết thúc và header `Idempotency-Key` mới | 202; run mới, có `parent_run_id` trỏ về run cũ |
| `DELETE /api/v1/sessions/me` | Bearer token hiện tại | 204; thu hồi phiên và yêu cầu hủy các run đang chờ/chạy |

Demo thường xong quá nhanh để hủy một run đang chạy bằng tay. Runner tự động
kiểm tra queued cancellation trước khi khởi động worker nên kết quả cancelled
là xác định. Hủy run đã kết thúc giữ nguyên trạng thái kết thúc hiện hữu.
Hủy request SDK đang chạy chỉ có hiệu lực ở các điểm kiểm tra hợp tác/timeout.

Retry thiếu key trả 422, retry run đang hoạt động trả 409/`run_active`. Chế độ
live dùng cấu hình hiện tại khi retry và sẽ thực hiện workflow mới.

Thu hồi token là bước cuối cùng. Sau đó thử `GET /sessions/me`: phải nhận 401.
Muốn tiếp tục thao tác, cấp một phiên mới và Authorize lại; tài nguyên của phiên
cũ không tự chuyển sang phiên mới.

## 11. Đọc lỗi và chạy lại toàn bộ bộ kiểm thử

Lỗi có cấu trúc:

```json
{
  "error": {
    "code": "idempotency_conflict",
    "message": "Key was already used for a different request",
    "request_id": "UUID de doi chieu log"
  }
}
```

Không phải mọi HTTP 4xx/503 đều là test thất bại. Nếu đang kiểm tra ảnh quá lớn,
413 là đúng; kiểm tra quyền truy cập sai, 404 là đúng. Đọc cả mã HTTP, `error.code`
và dữ liệu trả về thay vì chỉ nhìn màu response trên Swagger.

Chạy lại đúng bộ kiểm tra đã tạo bảng kết quả:

```powershell
uv run --locked python -m scripts.api_contract_report
```

Runner tự mở server demo trên port 18512, tạo SQLite và worker riêng, thực hiện
73 tình huống và tự dừng các tiến trình do nó tạo. Nếu port bận, dùng `--port 18515`.
Runner không sửa `.env`, không gọi server live 8000. Hai file được cập nhật:

- `reports/api-contract/results.md`: bảng theo 33 operations và 82 case.
- `reports/api-contract/results.json`: request/response đầy đủ đã che token.

Quá trình không thử Gemini thật, GPU thật, tải đồng thời nhiều người dùng, hoặc
mất mạng giữa lúc request SDK chạy. Các phần này cần bài kiểm thử riêng với điều
kiện và ngân sách cụ thể.
