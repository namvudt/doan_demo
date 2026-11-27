# Đánh giá bản đồ và bố cục giao diện

Ngày kiểm tra: 15/11/2026. Phạm vi: frontend nhánh `fe`, UI Preview; bản đồ dùng Leaflet và tile raster. Những số đo bên dưới là quan sát trên máy local, không phải cam kết độ trễ mạng hoặc FPS trên mọi thiết bị.

## Kết luận từ bản trước khi sửa

| Quan sát | Bằng chứng | Ý nghĩa |
| --- | --- | --- |
| Kéo bản đồ không tải lại trang hoặc tạo lại Leaflet | Kiểm tra trực tiếp giữ nguyên `.leaflet-map-pane`, 1 document request. Sau một lần kéo, tile request tăng từ 20 lên 25 và 20 tile cũ vẫn còn. | Tile mới cho vùng mới là hoạt động bình thường; cảm giác tải lại khi kéo không đồng nghĩa với reload trang. |
| Nền bản đồ chịu độ trễ mạng đáng kể trong lần kiểm tra | Trong chuỗi thao tác local với provider DE, 41 resource entry được ghi nhận; thời gian từng tile khoảng 266–1468 ms. | Đây là thời gian tải resource trong môi trường kiểm tra, không phải đo độ trễ tương tác hoặc FPS. Đổi bố cục đơn thuần không loại bỏ độ trễ provider. |
| Chế độ chỉ danh sách làm mất bản đồ | Quan sát trực tiếp pane bị gỡ khỏi DOM; khi hiện lại, pane mới được tạo. `MapPage.tsx` trước đây render `MapCanvas` có điều kiện. | Mất camera và tile đã tải; đây là một nguồn tải lại thực sự. |
| Chọn địa điểm dựng lại marker | Kiểm tra mã nguồn: effect phụ thuộc `selectedId` gọi `clearLayers()` và tạo lại mọi marker. | Công việc thừa cho một thay đổi trạng thái chọn; chưa có số đo FPS chứng minh riêng ảnh hưởng của nó. |
| Thử lại nền bản đồ dựng lại toàn bộ Leaflet | Kiểm tra mã nguồn: effect tạo map phụ thuộc `attempt`. | Retry có thể làm mất camera và marker dù chỉ cần thay tile layer. |
| Resize gây cập nhật liên tục | Kiểm tra mã nguồn: `ResizeObserver` gọi thẳng `invalidateSize()` cho từng callback. | Khi thêm chuyển động thay đổi kích thước, cần gom callback và giữ tâm địa lý. Đây là nguy cơ từ mã nguồn, không phải số đếm request đã đo. |
| Mobile dành phần lớn màn hình đầu cho danh sách | Fresh context 390×844: map stage bắt đầu ở khoảng y=675 px, toàn trang cao 1381 px; không tràn ngang. Xem [ảnh mobile trước sửa](../frontend/artifacts/screenshots/map-performance/map-before-mobile.png). | Người dùng phải cuộn mới có đủ không gian thao tác bản đồ. Không tràn ngang chưa đủ để kết luận bố cục mobile thuận tiện. |

Bản cũ còn đặt một viewport mặc định trước khi fit dữ liệu. Mã nguồn cho thấy khả năng có viewport trung gian, nhưng lần ghi nhận resource không chứng minh được request thừa tại zoom mặc định; không dùng điều này làm kết luận định lượng.

Ảnh baseline: [desktop trước sửa](../frontend/artifacts/screenshots/map-performance/map-before-desktop.png), [mobile trước sửa](../frontend/artifacts/screenshots/map-performance/map-before-mobile.png).

## Thay đổi trong đợt này

- Giữ một Leaflet instance khi thu gọn danh sách, chỉ xem danh sách, mở rộng bản đồ hoặc thay đổi kết quả lọc; chỉ hủy khi rời trang.
- Cập nhật marker theo ID; trạng thái chọn thay đổi class và thuộc tính truy cập trên node sẵn có.
- Retry thay tile layer, giữ camera; chuyển sang sơ đồ rồi quay lại nền khỏe giữ cả layer và tile đã tải.
- Kiểm thử lỗi mạng đã phát hiện thêm hai lỗi vòng đời: gỡ tile layer ngay trong callback của Leaflet gây truy cập map `null`; đổi `className` bằng React trên node Leaflet quản lý xóa các class native của Leaflet. Việc gỡ layer được đưa ra ngoài callback bằng frame có thể hủy, còn class của node map được giữ ổn định.
- Chỉ yêu cầu tile sau khi thao tác di chuyển kết thúc; giữ vùng tile đã ghé gần viewport. Không tải trước tile ngoài viewport.
- Gom resize bằng `requestAnimationFrame`, bù kích thước không animation để giữ tâm địa lý, bỏ xử lý map đang ẩn. Điều khiển zoom dùng chuyển động có thể dừng khi unmount; tôn trọng reduced motion.
- Danh sách và thông tin địa điểm có nút thu gọn/mở rộng; thẻ địa điểm nằm trong hàng riêng dưới map surface để không che nền, điểm hoặc attribution. Bản đồ có chế độ mở rộng và Escape để quay lại. Mobile ưu tiên vùng bản đồ, mở danh sách theo nhu cầu; các điều khiển chính cao ít nhất 44 px, chữ cốt lõi khoảng 12–13 px.

Các nguồn triển khai chính: [MapCanvas.tsx](../frontend/src/ui/MapCanvas.tsx), [MapPage.tsx](../frontend/src/pages-v2/MapPage.tsx), [map-experience.css](../frontend/src/ui/map-experience.css).

Quan sát sau sửa ở 390×844: map surface bắt đầu ở y≈165 px, cao khoảng 505 px; thẻ địa điểm có hàng riêng cao khoảng 118 px; toàn trang cao 844 px. Trước đó vùng bản đồ bắt đầu ở y≈675 px, trang cao 1381 px. Khi chuyển sang landscape thấp 844×390, map surface giữ cao 280 px và chart sơ đồ cao 145 px; trang cho cuộn dọc thay vì ép chart về 0 px.

Ảnh sau sửa: [desktop](../frontend/artifacts/screenshots/map-performance/map-after-desktop.png), [mobile](../frontend/artifacts/screenshots/map-performance/map-after-mobile.png), [danh sách mobile](../frontend/artifacts/screenshots/map-performance/map-after-mobile-sheet.png), [landscape thấp](../frontend/artifacts/screenshots/map-performance/map-short-landscape.png).

## Kiểm chứng

Suite [map-performance.spec.ts](../frontend/tests/e2e/map-performance.spec.ts) chặn mọi host ngoài local, cấp tile PNG xác định qua route interception và không gọi model AI. Chạy trong PowerShell:

```powershell
cd frontend
$env:RUN_MAP_PERF = '1'
npm run test:e2e
Remove-Item Env:RUN_MAP_PERF
```

Suite kiểm tra thao tác kéo chuột thật và zoom, danh tính pane/layer/marker, document request, tile DOM/request khi viewport không đổi, camera khi thu gọn/mở rộng, network fallback và retry, callback sau khi rời trang, cùng kích thước mobile. Không đặt ngưỡng thời gian chạy phụ thuộc phần cứng.

Kết quả cuối: **7/7 E2E đạt**, khoảng 1.1 phút cho toàn suite local. Đây là thời gian thực thi kiểm thử, không phải benchmark tốc độ bản đồ.

| Tình huống | Kết quả kiểm tra |
| --- | --- |
| Kéo chuột thật và zoom | Pane và tile layer giữ nguyên, chỉ 1 document request. |
| Chọn địa điểm, chọn lại cùng điểm | Giữ các marker node; viewport không đổi không thêm tile request hoặc thay tile DOM. |
| Mở thông tin, thu gọn danh sách, chỉ danh sách, mở rộng bản đồ, Escape | Giữ pane và zoom; vị trí marker so với tâm viewport sai khác tối đa 2 px khi đổi kích thước và khi khôi phục. |
| Tile lỗi mạng thật qua route abort, sau đó retry thành công | Giữ camera và marker, không còn lỗi callback Leaflet. |
| Chuyển sang sơ đồ rồi quay lại nền khỏe | Giữ tile layer/tile DOM, không thêm request. |
| Rời trang khi map đang chuyển động, lặp 3 lần | Không có page error sau khi unmount. |
| Mobile | Danh sách có thể mở/thu gọn; dialog mở rộng nằm trong viewport, không tràn ngang, giữ pane. |
| Resize 320×600 → landscape 844×390 | Map surface cao ít nhất 280 px, các điều khiển nằm trong vùng map, chart sơ đồ vẫn có kích thước, mở rộng/quay lại giữ pane; không tràn ngang hoặc page error. |

Suite không kiểm tra độ trễ của nhà cung cấp tile ngoài Internet hoặc hiệu năng thiết bị mobile thật. Map ở chế độ API vẫn phụ thuộc catalog có tọa độ từ backend.

## Tự đánh giá và ưu tiên tiếp theo

| Ưu tiên | Đánh giá | Cải tiến đề xuất | Cách xác nhận |
| --- | --- | --- | --- |
| P1 | Bản đồ, danh sách và thẻ địa điểm có ngôn ngữ hình ảnh nhất quán; bản cũ thiếu quyền chủ động phân bổ không gian. Đợt này bổ sung thu gọn và mở rộng. | Kiểm tra với người dùng việc mở danh sách, chọn điểm rồi trở lại bản đồ; có thể lưu lựa chọn bố cục theo phiên nếu họ thường thay đổi. | Đếm bước hoàn thành tác vụ trên desktop/mobile; không tự động lưu viewport khi người dùng đang cần liên kết chia sẻ có ý nghĩa khác. |
| P1 | Một số chữ phụ rất nhỏ: root 14 px, nhiều label/meta dùng 0.55–0.72 rem, tương đương khoảng 7.7–10.1 px trước zoom trình duyệt. Đây là số từ CSS, chưa phải đánh giá thị lực người dùng. | Chuẩn hóa cỡ chữ phụ khoảng 12 px trở lên, tăng độ tương phản sau khi đo; rà soát kích thước nút chạm và focus bàn phím. | Đo contrast trên màu thực; kiểm tra 200% zoom, 320 px và bàn phím, giữ đủ nội dung và không che hành động chính. |
| P2 | Sidebar shell 246 px cộng danh sách bản đồ cố định trước đây chiếm nhiều chiều ngang; banner trạng thái 35 px và footer 56 px chiếm không gian dọc. | Thêm sidebar shell gọn, ưu tiên nội dung làm việc; rút gọn thông tin chế độ lặp lại nhưng giữ dấu hiệu Preview/AI live và trạng thái lỗi rõ ràng. | So sánh không gian hữu ích và khả năng nhận biết chế độ; không ẩn thông tin model có thể tính phí. |
| P2 | Trang Chat có lịch sử 330 px cố định ở desktop, uploader tối thiểu 215 px và vùng nhập lớn. Quan sát local 1366×768: toàn trang cao 1011 px, tiêu đề xuống hai dòng và nút “Khám phá” ở dưới màn hình đầu; xem [ảnh Chat](../frontend/artifacts/screenshots/map-performance/layout-chat-audit.png). | Cho phép thu gọn lịch sử, giảm chiều cao tiêu đề, gọn uploader sau khi đã chọn ảnh, giữ câu hỏi/hành động gửi trong vùng nhìn thấy. | Kiểm tra câu hỏi dài, ảnh lỗi, màn hình laptop thấp và mobile. |
| P2 | Trang kết quả đã có `<details>` cho stage/model attempt, nhưng toàn cột thực thi vẫn chiếm không gian; tiêu đề câu hỏi có thể lên 2.8 rem. | Ưu tiên câu trả lời, chứng cứ và hành động hỏi tiếp; cho thu gọn cả cột thực thi, giữ lỗi quan trọng dễ thấy. | Kiểm tra run đang chạy, thành công, thất bại và không có chứng cứ; tách rõ thông tin người dùng cần với JSON phục vụ debug. |
| P2 | Khoảng trống catalog/tọa độ của lần đánh giá ban đầu đã được xử lý bằng migration0005 và API catalog dùng chung. | Duy trì ID ổn định, tọa độ có mức xác minh, media và phân trang; xem [triển khai DB](CATALOG_DATABASE.md). | Contract/integration test bằng dữ liệu backend; seed vẫn minh họa, không suy đoán tọa độ từ tên hoặc câu trả lời AI. |
| P3 | Bộ dữ liệu Preview chỉ có vài điểm; danh sách hiện đủ gọn, ảnh local đã có kiểm thử phục hồi lỗi. | Khi có catalog lớn, đo rồi mới thêm clustering/virtualization; bổ sung lựa chọn sắp xếp hoặc “tìm trong vùng này” khi nhu cầu rõ ràng. | Dùng dữ liệu đại diện và thiết bị mobile thật; theo dõi số marker, bộ nhớ, tốc độ lọc và độ chính xác kết quả. |

Ngoài bản đồ, Chat có quan sát ảnh local như ghi trên; những nhận xét khác chủ yếu dựa trên cấu trúc JSX/CSS. Chưa có user study hoặc phép đo hiệu năng riêng cho Chat, kết quả run và toàn bộ catalog trong đợt này.
