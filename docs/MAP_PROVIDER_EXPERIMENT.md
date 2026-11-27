# Thử nghiệm nguồn nền bản đồ

Ngày: 15/11/2026. Phạm vi này đo tải tile raster trong một viewer Leaflet cố định. Hiệu năng cuộn toàn ứng dụng được đo riêng; thời gian tải tile không được dùng làm chỉ số FPS hoặc độ trễ React.

## Kết quả hiện có

| Phần kiểm tra | Kết quả |
| --- | --- |
| Kiểm tra cấu hình có thể dùng | Public token Mapbox đã hoạt động từ `frontend/.env.map.local`, file được Git bỏ qua. Không đọc `.env` backend; token không được lưu trong mã nguồn hoặc báo cáo. |
| `--check` | Mapbox có `credentialConfigured: true`, `browserTokenType: public`; ba provider còn lại chưa có key khả dụng. Chỉ báo trạng thái, không in token và không phát request mạng. |
| Fixture local HTTP 200 | Cả hai adapter đạt. MapTiler 256: 15 tile cold + 15 cache hit warm, tổng 30 attempts. Mapbox 512: 6 tile cold + 6 cache hit warm, tổng 12 attempts. Đều dưới giới hạn 64, không có host ngoài local hoặc page error. |
| Fixture local HTTP 403 | Cả hai adapter đạt: MapTiler 15 response 403, Mapbox 6 response 403; không tile nào tải thành công, decoded-ready là `null`, dừng trước warm reload. Kiểm tra che key/query và token `pk.`/`sk.` bằng sentinel đạt. |
| MapTiler thật | Chưa chạy vì chưa có browser API key do người dùng cung cấp. Không dùng key từ demo công khai hoặc đăng ký tài khoản thay người dùng. |
| Mapbox thật | **Đã chạy thành công** sau khi người dùng lưu public token vào file frontend được Git bỏ qua. Cold: 6 tile HTTP 200, toàn viewport decode-ready 1.561 ms. Warm reload: 6 browser cache hit, decode-ready 34,6 ms. Không có tile lỗi hoặc page error. |
| Goong, VIETMAP thật | Chưa có key hoặc adapter trong harness, chưa có phép đo so sánh. |
| Tile cộng đồng OSM | Không chạy bot benchmark hoặc quét tile; các số đo trước đây từ phiên kiểm tra bản đồ được ghi trong [MAP_LAYOUT_REVIEW.md](MAP_LAYOUT_REVIEW.md), không phải kết quả xếp hạng provider. |

Không có đủ dữ liệu để kết luận MapTiler, Mapbox, Google Maps, Goong hoặc VIETMAP nhanh hơn trên mạng hiện tại.

## Kết quả Mapbox local ngày 15/11/2026

Nguồn: [báo cáo Mapbox thật](../frontend/artifacts/performance/mapbox-live.json).
Viewport 960×540, Hà Nội, zoom Leaflet 12; Streets v12, tile 512px và zoom offset -1.

| Chỉ số | Context mới | Reload cùng context |
| --- | --- | --- |
| Số tile request | 6 | 6 |
| Browser cache hit | 0 | 6 |
| HTTP lỗi | 0 | 0 |
| Thời gian hoàn tất tile p50 / p95 | 780,4 / 1.542,2 ms | Không có mẫu mạng uncached |
| Toàn viewport decode-ready | 1.561 ms | 34,6 ms |

Context mới không đồng nghĩa CDN của Mapbox chưa có cache. Warm reload dùng
cache bình thường và không đại diện cho tải khu vực mới. Chỉ sáu tile mỗi
lượt là mẫu nhỏ; p95 này không đại diện mọi nhà mạng hoặc khu vực Việt Nam.
Không so trực tiếp với số đo OSM cũ vì khác viewport, tile size và phương pháp.

Đã thử nguồn thật trong ứng dụng ở `http://127.0.0.1:5175/map`: desktop có
18 request tile qua tải đầu và zoom, mobile có 2; không có lỗi tile hoặc
JavaScript. Pan/zoom, chỉ danh sách, sơ đồ/quay lại giữ map instance và cả
bảy marker. Mỗi trang chỉ có một document request. Logo và đủ ba credit
hiển thị; mobile 390px không chồng logo/credit và không tràn ngang.
[Bộ đếm UI thật](../frontend/artifacts/performance/mapbox-app-live.json),
[ảnh desktop](../frontend/artifacts/screenshots/mapbox/mapbox-desktop-live.png),
[ảnh mobile](../frontend/artifacts/screenshots/mapbox/mapbox-mobile-live.png).

Ứng dụng dùng raster qua Leaflet để giữ phần tối ưu và bố cục hiện có; đây
chưa phải phép đo Mapbox GL JS/vector. Static Tiles được tính theo API request,
khác đơn vị map load của GL JS. Chọn 512px thay 256px để giảm số request cần
cho cùng vùng nhìn. [Static Tiles API](https://docs.mapbox.com/api/maps/static-tiles/).

Token nằm trong `frontend/.env.map.local`, được Git bỏ qua; không lưu token
hoặc tile URL có query trong báo cáo. Asset logo được lấy nguyên bản từ
[repository chính thức của Mapbox](https://github.com/mapbox/mcp-server/blob/main/assets/mapbox-logo-white.svg).

Chạy giao diện thử nghiệm từ thư mục `frontend`:

```powershell
npm run dev -- --mode map --port 5175 --strictPort
```

Mở `http://127.0.0.1:5175/map`. Mode `map` đọc file frontend local đã cấu hình,
giữ UI Preview và tắt AI live; chế độ dev thông thường trên 5173 vẫn giữ
cấu hình riêng. Phần catalog/toạ độ là dữ liệu Preview, nền tile là Mapbox thật.

Đã đạt typecheck, lint, build và 41 unit tests. Hồi quy hiện tại đạt
**21/21 E2E**: 7 luồng Preview, 7 map, 4 scroll và 3 Mapbox riêng. Các test
Mapbox dùng `pk.fixture` và intercept tile, kiểm tra 512px/zoom offset,
pan/zoom, lỗi 403 rồi retry, giữ camera/marker, logo/credit ở 390px và 320px.
Không dùng token thật trong E2E hoặc trace. Snapshot zoom đọc tile level
đang có scale 1 thay vì tile đầu tiên còn giữ tạm trong DOM khi chuyển cảnh.

```powershell
$env:RUN_MAPBOX_UI = '1'
npm run test:e2e
Remove-Item Env:RUN_MAPBOX_UI
```

## Harness có thể chạy lại

[map-provider-benchmark.mjs](../frontend/scripts/map-provider-benchmark.mjs) dùng Leaflet đang có trong dự án, phục vụ viewer local độc lập và không sửa cấu hình ứng dụng. Script không tự đọc bất kỳ file `.env` nào.

```powershell
cd frontend

# Chỉ kiểm tra có cấu hình hay chưa; không in key, không gọi provider.
node scripts/map-provider-benchmark.mjs --check

# Kiểm tra cơ chế đo bằng PNG fixture local; không gọi provider.
node scripts/map-provider-benchmark.mjs --self-test
node scripts/map-provider-benchmark.mjs --self-test-denied
node scripts/map-provider-benchmark.mjs --provider=mapbox --self-test
node scripts/map-provider-benchmark.mjs --provider=mapbox --self-test-denied

# Sau khi MAPTILER_API_KEY đã được đặt trong process bằng key của người dùng:
node scripts/map-provider-benchmark.mjs --run --output test-results/map-provider/maptiler.json

# Kiểm tra public token Mapbox đã điền ở frontend/.env.map.local:
node --env-file=.env.map.local scripts/map-provider-benchmark.mjs --provider=mapbox --check

# Chỉ chạy sau khi token pk. của người dùng đã được cấu hình:
node --env-file=.env.map.local scripts/map-provider-benchmark.mjs --provider=mapbox --run --output test-results/map-provider/mapbox.json
```

Mặc định vẫn là MapTiler với `MAPTILER_API_KEY`. `--provider=mapbox` đọc `MAPBOX_ACCESS_TOKEN` hoặc `VITE_MAPBOX_ACCESS_TOKEN` từ process, yêu cầu public token bắt đầu `pk.`; `sk.` và kiểu token khác bị từ chối trước khi mở browser hoặc gọi mạng. Node `--env-file` là thao tác nạp file được chỉ định rõ, không phải script tự tìm/đọc `.env`. [Mapbox token types](https://docs.mapbox.com/help/dive-deeper/access-tokens/).

Browser key cần cho phép origin thử nghiệm `http://127.0.0.1:5177`; có thể đổi cổng bằng `MAP_BENCH_PORT`. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` dùng khi cần chọn Chrome/Edge cụ thể. Thêm `--headed` để quan sát viewer; không bật trace, HAR hay screenshot chứa URL cấu hình.

Viewer sử dụng endpoint raster 256 px chính thức của MapTiler, hiển thị logo và credit MapTiler/OpenStreetMap. Cấu hình đó độc lập với MapCanvas của sản phẩm. Nếu đưa provider vào sản phẩm, cần giữ attribution/logo tương ứng và kiểm thử lại layout, key restrictions, fallback và quota. [Maps API](https://docs.maptiler.com/cloud/api/maps/), [Leaflet và attribution](https://docs.maptiler.com/guides/map-design/attribution/add-attribution/).

Mapbox dùng Static Tiles API với style `mapbox/streets-v12`, tile 512 px và Leaflet `zoomOffset: -1`. Cách này theo khuyến nghị Mapbox để tránh tăng request tính phí khi dùng tile 256 px. Viewer giữ logo chính thức không chỉnh sửa từ file public dùng chung của ứng dụng, cùng ba link Mapbox/OpenStreetMap/Improve this map. [Static Tiles API](https://docs.mapbox.com/api/maps/static-tiles/), [Attribution](https://docs.mapbox.com/help/dive-deeper/attribution/), [Nguồn logo chính thức](https://raw.githubusercontent.com/mapbox/mcp-server/main/assets/mapbox-logo-white.svg).

## Phương pháp và giới hạn

- Giữ viewport 960×540, tâm Hà Nội `[21.0285, 105.8542]`, mức zoom Leaflet 12. MapTiler dùng tile 256/offset 0; Mapbox dùng tile 512/offset -1. Báo cáo ghi rõ `tileSize` và `zoomOffset`; số request, byte hay độ trễ từng tile không đại diện cùng lượng công việc. Không xếp hạng provider bằng các con số này. Không pan/zoom tự động, không tải trước, không tải hàng loạt.
- Một lần tải trong browser context mới, sau đó reload trong cùng context. Giữ HTTP cache mặc định; không dùng `no-cache`, không route interception. Ngưỡng cứng là 64 tile attempts cho cả phiên. HTTP 401/403 dừng trước lượt reload tiếp theo.
- CDP ghi số request, HTTP status, cache hits và thời gian tới response header/hoàn tất. Báo cáo p50/p95 chỉ tính các tile HTTP 200 không được phục vụ từ browser cache; số mẫu được ghi kèm.
- Đo riêng thời điểm toàn bộ tile đã settled và đã decode; nếu có tile lỗi thì `allTilesDecodedReadyMs` là `null`.
- Báo cáo chỉ chứa thống kê và hostname, không có tile URL, query string hoặc giá trị key. Lỗi được che key/URL query trước khi in.
- “Cold” chỉ là context browser mới, không xóa cache CDN/server. “Warm” phụ thuộc header cache thực tế. Một viewport và hai lượt tải là mẫu nhỏ; p95 không đại diện toàn bộ Việt Nam, mọi nhà mạng hoặc thời điểm trong ngày.
- Prototype này không đo thời gian khởi tạo SDK vector, tìm địa chỉ, chỉ đường, GPU hay cuộn giao diện. Không lấy tốc độ fixture local làm tốc độ MapTiler.

Để so sánh provider thật cần key hợp lệ, cùng khu vực, cùng loại nền/dữ liệu và cùng điều kiện mạng. Nên thu thêm mẫu trong các phiên sử dụng bình thường thay vì tăng số tile hoặc bỏ qua cache.

## Vì sao không benchmark tự động máy chủ tile cộng đồng

Chính sách OSM.org giới hạn dịch vụ ở khả năng cung cấp tốt nhất, không có SLA; cấm tải hàng loạt, bypass cache và bot headless pan/zoom để ép tải tile. OSM Germany nêu giới hạn băng thông, việc giảm tốc theo IP và dẫn chiếu chính sách tile. Vì vậy harness không dùng các máy chủ này cho bot so sánh. [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/), [OSM Germany](https://openstreetmap.de/germanstyle/).
