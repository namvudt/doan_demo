# Phân tích và cải thiện độ mượt khi cuộn

Ngày: 15/11/2026. Phạm vi: frontend nhánh `fe`, build production ở local,
UI Preview. Không gọi backend hay model AI trong phép đo này.

## Cách đo

[profile-scroll.mjs](../frontend/scripts/profile-scroll.mjs) chạy Chrome headless,
giảm tốc CPU 4 lần qua CDP, thực hiện bốn thao tác cuộn xuống/lên bằng
`Input.synthesizeScrollGesture`. Mỗi kịch bản được lặp ba lần:

- Catalog desktop 1366×768 và mobile 390×844.
- Hồ sơ Văn Miếu, trang nhập Chat và danh sách bản đồ trên desktop.
- Catalog với request ảnh được giữ lại để mô phỏng ảnh tải chậm.

Các kịch bản cuộn ổn định hoàn tất decode ảnh local trước khi đo. Kịch bản ảnh
chờ tải giữ nguyên sáu placeholder. Request ngoài local bị chặn; tile bản đồ
được cấp PNG fixture tại browser, không tải từ nhà cung cấp tile. Thời gian
fixture không đại diện cho độ trễ bản đồ thật.

Trace chỉ được xử lý trong bộ nhớ, lưu số paint/raster, thời gian main thread,
khoảng cách callback `requestAnimationFrame`, long task và vị trí cuộn thực tế.
Không lưu trace chứa nội dung phiên làm việc. Khoảng cách rAF không phải phép
đo độ trễ input-to-display, FPS phần cứng hoặc benchmark thiết bị mobile thật.
Main-thread/script time bao gồm cả instrumentation. Máy local có nhiễu từ
hệ điều hành; không suy diễn cải thiện mọi trang từ một mẫu tốt.

## Phát hiện

1. Không thấy handler scroll/wheel trong Catalog hoặc Chat gây cập nhật React
   theo mỗi lần cuộn. Ảnh đã lazy-load, decode bất đồng bộ và có khung kích
   thước ổn định; chưa có bằng chứng cần viết lại React hoặc thêm memoization
   hàng loạt.
2. Placeholder ảnh cũ animate `background-position` trên gradient. Khi sáu
   ảnh chờ tải, trace ghi nhận hơn một nghìn paint trong một lượt cuộn. Đây là
   công việc render có thể loại bỏ và đã tái hiện được.
3. Header sticky dùng nền trong suốt và `backdrop-filter: blur(14px)` trên mọi
   trang. Đổi sang nền đặc giữ cùng tông màu loại bỏ việc lọc nền đang chuyển
   động. Phép đo này chưa tách riêng mức ảnh hưởng của blur khỏi shimmer.
4. Khi ảnh đã tải xong, phần lớn mẫu trước sửa có p95 khoảng cách rAF khoảng
   16,8 ms. Chưa tái hiện độ trễ lớn thường trực trên toàn web trong trạng thái
   này. Không quy lỗi mọi hiện tượng lag cho mạng, React hoặc header.

## Thay đổi

- [ResilientImage.css](../frontend/src/ui/ResilientImage.css): nền loader tĩnh;
  gradient nằm trên pseudo-element chỉ animate `transform`, thay vì vẽ lại nền
  mỗi frame. Tôn trọng `prefers-reduced-motion`, giữ nguyên lazy loading,
  trạng thái lỗi và retry.
- [styles.css](../frontend/src/styles.css): header sticky dùng nền đặc, bỏ blur
  nền. Không thêm handler scroll hoặc thay đổi nội dung/bố cục.
- Bổ sung [scroll-performance.spec.ts](../frontend/tests/e2e/scroll-performance.spec.ts)
  để kiểm tra cuộn thật trên desktop/mobile, danh sách bản đồ, feedback tải
  ảnh và reduced motion. Không đặt ngưỡng FPS hoặc thời gian chạy trong E2E.

## Kết quả

Mỗi ô là trung vị của ba lượt đo, cùng máy, cùng viewport, cùng kịch bản và
CPU slowdown 4×. Cột rAF là trung vị của p95 từng lượt, không phải p95 gộp.

| Kịch bản | Paint trước → sau | Tổng thời gian Paint trước → sau (ms) | p95 rAF trước → sau (ms) |
| --- | --- | --- | --- |
| Catalog, ảnh đã tải | 8 → 8 | 2,98 → 2,12 | 16,8 → 16,8 |
| Catalog mobile, ảnh đã tải | 9 → 9 | 3,96 → 5,93 | 16,8 → 16,8 |
| Hồ sơ Văn Miếu | 2 → 2 | 1,22 → 1,27 | 16,8 → 16,9 |
| Trang nhập Chat | 0 → 0 | 0 → 0 | 16,8 → 16,8 |
| Danh sách bản đồ | 10 → 10 | 4,56 → 3,98 | 16,8 → 16,8 |
| Catalog, sáu ảnh chờ tải | **1.258 → 2** | **639,03 → 1,83** | **33,3 → 16,8** |

Trường hợp ảnh chờ tải giảm rõ công việc paint; số khoảng cách rAF trên 32 ms
giảm từ trung vị 17 xuống 2 trong mỗi lượt cuộn. Tổng Paint là tổng duration
của trace events, không phải thời gian tải trang. Một mẫu catalog ảnh đã tải
sau sửa vẫn có p95 33,2 ms trong khi hai mẫu còn lại là 16,8 ms; đây là lý do
giữ đầy đủ dữ liệu và không khẳng định web luôn đạt 60 FPS hoặc mọi trang
nhanh gấp đôi. Mobile ảnh đã tải cũng không có cải thiện đồng đều ở mọi chỉ
số. Hiệu quả đã tái hiện rõ nhất nằm ở loader ảnh.

Đã đạt trên cây mã sau tích hợp Mapbox: typecheck, lint, build, 41 unit tests
và **21/21 E2E** (7 luồng Preview, 7 bản đồ, 4 cuộn, 3 Mapbox). Các E2E kiểm
tra cuộn native xuống/lên, header, danh sách map không zoom theo wheel bên
ngoài canvas, loader transform/reduced motion, không document reload hoặc
page error. Luồng ảnh lỗi/thử lại, admin CRUD, map fallback/retry và xoay màn
hình đều đã chạy lại thành công sau sửa CSS.

Kiểm tra trực quan sau cuộn 600 px: [desktop](../frontend/artifacts/screenshots/scroll-performance/catalog-desktop-after.png),
[mobile](../frontend/artifacts/screenshots/scroll-performance/catalog-mobile-after.png).
Header còn hiển thị và mobile không tràn ngang.

Dữ liệu thô: [trước sửa](../frontend/artifacts/performance/scroll-before.json),
[sau sửa](../frontend/artifacts/performance/scroll-after.json).

## Chạy lại

```powershell
cd frontend
$env:VITE_FRONTEND_MODE = 'preview'
$env:VITE_MAP_TILE_URL = 'https://tiles.test/{z}/{x}/{y}.png'
npm run build
npm run preview -- --port 5175 --strictPort
```

Ở terminal khác:

```powershell
cd frontend
node scripts/profile-scroll.mjs --label=local --runs=3 --cpu=4
$env:RUN_SCROLL_PERF = '1'
npm run test:e2e
Remove-Item Env:RUN_SCROLL_PERF
```

URL `tiles.test` chỉ là host fixture, harness cấp tile tại browser,
không phát request tới máy chủ bản đồ. Cờ `RUN_SCROLL_PERF` ưu tiên hơn các
cờ backend/live cũ trong process để không vô tình chạy model AI.

Độ trễ nguồn bản đồ được xử lý riêng tại
[MAP_PROVIDER_EXPERIMENT.md](MAP_PROVIDER_EXPERIMENT.md). Sau phép đo cuộn,
Mapbox đã được thử với nguồn tile thật bằng token local do người dùng cung
cấp. Chưa có phép đo so sánh đồng điều kiện giữa các provider.

## Phần cần đo tiếp nếu vẫn chậm trên máy người dùng

- Profile Chrome trên thiết bị và phiên sử dụng thực tế, nhất là khi đang nhận
  SSE hoặc hiển thị kết quả dài; phiên đo hiện tại dùng Chat ở trạng thái nhập.
- Tách cold load, ảnh lỗi/tải chậm, steady scroll và độ trễ tile. Không dùng
  thời gian tải mạng để kết luận tốc độ cuộn.
- Chỉ tối ưu tiếp phần render, image variants, clustering hoặc virtualization
  khi có dữ liệu đại diện và trace chứng minh cần thiết.
