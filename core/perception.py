"""Configurable perception instructions, independent of benchmark reference answers."""

from core.evidence import is_count_question, normalized_text

SCENE_INSTRUCTIONS = """
Đánh giá riêng hai trục: scene_visibility là khả năng nhìn hình dạng/bố cục/chi tiết công trình;
text_readability chỉ là khả năng đọc chữ. Không có chữ thì text_readability=not_applicable.
readability cũ phải bằng scene_visibility. Không biết lịch sử, tên địa điểm hay chữ trên biển
không phải lý do đặt scene_visibility=unreadable. Chỉ unreadable khi không thể quan sát cảnh;
nếu vẫn thấy một số đặc điểm thì limited, thấy rõ thì adequate. Giữ bất định nhận diện riêng.
Nhận xét khả năng quan sát ảnh không phụ thuộc việc câu hỏi đòi hỏi kiến thức ngoài ảnh.
Box dùng [x_trái,y_trên,x_phải,y_dưới], gốc (0,0) ở góc trên trái; x tăng sang phải,
y tăng xuống dưới. Vật thể phía dưới có y lớn; vật thể bên phải có x lớn.
Kiểm tra box thực sự chứa vật thể được mô tả. Không đổi x/y; không đoán box khi chưa chắc,
khi đó trả box=null. Với câu hỏi đếm, phân biệt đúng loại đối tượng và không đếm bóng phản chiếu.
Với slot đếm thuần thị giác, điền count_findings theo slot_id được cung cấp. Mỗi instance trỏ
observation_index, nêu object_class và classification confirmed/uncertain/excluded. Box instance
dùng các tên x_min,y_min,x_max,y_max; x là trái/phải, y là trên/dưới. Chỉ đếm instance confirmed
đúng loại được hỏi; thanh đứng chưa rõ công dụng không tự coi là cột cờ. Đối tượng uncertain
phải giữ bất định, không gộp vào tổng chắc chắn. Không tạo nhiều instance cho cùng một vật thể.
"""

CONCISE_INSTRUCTIONS = """
Hợp đồng trích dẫn bắt buộc: claims[].evidence_ids và quotations[].evidence_id chỉ lấy
từ valid_evidence_ids. source_id/display_source_id (thường wiki_...) là nhãn hiển thị,
không phải evidence_id. Dùng source_evidence_index để tìm evidence_id tương ứng rồi
chép quotation nguyên văn từ evidence.text của chính evidence_id đó. Không tự tạo ID.
Ưu tiên trả lời ngắn, trực tiếp đúng điều từng slot hỏi; không lặp câu hỏi trong claim.
Chỉ tạo claim góp phần trả lời slot, không biến toàn bộ quan sát nền thành câu trả lời.
Câu hỏi tên gọi cần tên; màu sắc cần màu; số lượng cần số và đơn vị nếu cần.
Vẫn giữ mức bất định, giới hạn và quotation cần thiết; không hy sinh bằng chứng để trả lời ngắn.
Đối chiếu ảnh: nếu box của evidence không chứa đối tượng được mô tả thì không coi box đó là
bằng chứng định vị hợp lệ. Không đọc được chữ không tự phủ định nhận diện bằng bố cục cảnh.
Với số lượng, đối chiếu riêng từng instance, loại đối tượng và box. Đếm evidence_ids không
thay cho đếm vật thể; vật giống cột cờ nhưng chưa rõ công dụng phải giữ bất định. Chỉ supported
khi số trong claim khớp tổng instance confirmed có vùng đúng; không tự đổi x/y của box.
"""


def asks_counting(query):
    return is_count_question(query)


def asks_text_reading(query):
    text = " " + normalized_text(query) + " "
    terms = (
        "doc chu",
        "dong chu",
        "chu tren",
        "chu nao",
        "chu gi",
        "chu so",
        "bien ten",
        "bien hieu",
        "bang hieu",
        "duoc viet",
        "ghi gi",
        "noi dung bang",
        "ngon ngu",
        "phien am",
        "dich chu",
        "text",
        "inscription",
        "sign says",
        "written",
        "letter",
    )
    return any(" " + term + " " in text for term in terms)
