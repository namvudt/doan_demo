from typing import Dict, Any, Tuple, Optional
from PIL import Image
from utils.llm_clients import LLMManager

# ==============================================================================
# 1. VISUAL AGENT (Gemini Multimodal)
# ==============================================================================
VISUAL_SYSTEM_PROMPT = """Bạn là Visual Expert Agent (Chuyên gia Giám định Thị giác & Kiến trúc Di sản Việt Nam).
Vai trò của bạn là quan sát kỹ lưỡng bức ảnh di tích/tác phẩm nghệ thuật và cung cấp báo cáo phân tích thị giác chuẩn xác, khoa học.

YÊU CẦU PHÂN TÍCH:
1. Nhận diện Di tích / Tác phẩm: Nêu rõ tên di tích, công trình kiến trúc hoặc cổ vật/tác phẩm trong ảnh (kèm mức độ tự tin nhận diện).
2. Chi tiết Kiến trúc & Mỹ thuật:
   - Kết cấu & Kiến trúc: Mái ngói (mái đao cong, ngói âm dương, mũi hài), bờ nóc, bờ dải gắn kìm nóc, rồng chầu mặt nguyệt, hệ vì kèo, cột gỗ, đấu củng...
   - Chất liệu & Màu sắc: Gỗ lim, gạch Bát Tràng, đá xanh Ninh Bình, vôi vữa cổ truyền, sơn son thếp vàng, rêu phong thời gian...
   - Bố cục & Góc máy: Toàn cảnh, cận cảnh, ánh sáng, cảnh quan xung quanh (hồ nước, cây đa, sân gạch...).
3. Bằng chứng thị giác trực tiếp (Visual Evidences): Chỉ ra chính xác các chi tiết nhìn thấy bằng mắt thường trong ảnh để trả lời cho câu hỏi cụ thể của người dùng.
4. Phát hiện chữ viết/văn bản: Báo cáo xem có nhìn thấy chữ Hán, chữ Nôm, hoành phi, câu đối, biển bảng nào trong ảnh hay không.
Trình bày mạch lạc bằng Markdown với tiêu đề rõ ràng, ngôn từ chuẩn xác về mặt mỹ thuật học cổ truyền."""

class VisualAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Visual Expert Agent"

    def analyze(self, image: Image.Image, query: str, focus_directive: str = "") -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Hãy quan sát bức ảnh di tích/tác phẩm nghệ thuật này và giải đáp yêu cầu:

Câu hỏi của người dùng: "{query}"
Chỉ thị trọng tâm quan sát: "{focus_directive or 'Tập trung bóc tách các đặc điểm thị giác then chốt phục vụ câu hỏi'}"

Hãy bóc tách toàn bộ đặc điểm thị giác, nhận diện công trình và cung cấp bằng chứng thị giác xác đáng."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=VISUAL_SYSTEM_PROMPT,
            image=image,
            preferred_provider="gemini", # Ưu tiên Gemini Multimodal
            temperature=0.3
        )
        return response_text, meta


# ==============================================================================
# 2. OCR AGENT (Gemini Multimodal - Chuyên Hán Nôm & Chữ cổ)
# ==============================================================================
OCR_SYSTEM_PROMPT = """Bạn là OCR & Hán Nôm Specialist Agent (Chuyên gia Giải mã Văn tự & Thư pháp Di sản).
Vai trò của bạn là bóc tách mọi văn bản, chữ viết xuất hiện trong ảnh (chữ Hán, chữ Nôm, chữ Quốc ngữ cổ, văn bia, hoành phi, câu đối, biển hiệu chỉ dẫn di tích).

YÊU CẦU GIẢI MÃ:
1. Phát hiện Vị trí & Dạng văn bản: Nằm ở đâu trong ảnh? (Trên hoành phi, đôi câu đối ở hai cột, trên trán bia đá, hay biển gỗ/đồng?).
2. Trích xuất Nguyên văn (Transcribe):
   - Chữ Hán/Nôm: Ghi rõ chữ gốc (nếu đọc được rõ) và Phiên âm Hán-Việt chuẩn xác.
   - Chữ Quốc ngữ / Tiếng nước ngoài (nếu có trên biển chỉ dẫn): Trích xuất chính xác.
3. Dịch nghĩa Tiếng Việt: Diễn giải nghĩa của câu chữ sang tiếng Việt hiện đại một cách văn nhã, chuẩn mực.
4. Phân tích Ý nghĩa Văn hóa & Triết lý: Ý nghĩa của dòng chữ đó đối với di tích (thể hiện đạo lý uống nước nhớ nguồn, tinh thần hiếu học, ca ngợi cảnh đẹp, hay tôn vinh thần thánh/danh nhân).

Nếu trong ảnh không có chữ viết hoặc ảnh quá mờ không đọc được, hãy giải thích trung thực tình trạng đó."""

class OCRAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "OCR & Epigraphy Agent"

    def extract_and_translate(self, image: Image.Image, query: str) -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Hãy kiểm tra kỹ bức ảnh và trích xuất/dịch toàn bộ chữ viết, văn bia, hoành phi, câu đối hoặc biển hiệu có trong ảnh:

Yêu cầu cụ thể của người dùng: "{query}"

Vui lòng đọc chữ, phiên âm, dịch nghĩa và giải thích ý nghĩa văn hóa sâu sắc."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=OCR_SYSTEM_PROMPT,
            image=image,
            preferred_provider="gemini", # Multimodal đọc ảnh
            temperature=0.2
        )
        return response_text, meta


# ==============================================================================
# 3. KNOWLEDGE AGENT (OpenAI / Gemini - Tri thức Lịch sử & Sự kiện Văn hóa)
# ==============================================================================
KNOWLEDGE_SYSTEM_PROMPT = """Bạn là Cultural & Historical Knowledge Expert Agent (Chuyên gia Nghiên cứu Lịch sử & Di sản Văn hóa Việt Nam).
Nhiệm vụ của bạn là bổ sung bối cảnh tri thức uyên bác, chính xác về di tích, nhân vật, triều đại và các sự kiện văn hóa liên quan.

YÊU CẦU CUNG CẤP TRI THỨC:
1. Lịch sử & Niên đại:
   - Địa điểm/công trình này được khởi dựng vào thời gian nào? Dưới triều đại nào (Lý, Trần, Lê sơ, Mạc, Lê Trung Hưng, Nguyễn...)?
   - Ai là người khởi xướng xây dựng hoặc nhân vật lịch sử/vị thần nào được thờ phụng tại đây?
2. Vị thế Di sản & Giá trị Văn hóa:
   - Công trình có được xếp hạng Di tích Quốc gia đặc biệt hay Di sản Thế giới UNESCO không?
   - Giá trị biểu tượng tinh thần trong tâm thức người Việt Nam.
3. Các Sự kiện Văn hóa, Lễ hội & Hoạt động thực tế:
   - Lễ hội truyền thống diễn ra vào thời gian nào (ngày âm lịch/dương lịch)? Các nghi thức độc đáo (rước kiệu, tế lễ, diễn xướng dân gian...).
   - Các hoạt động văn hóa, triển lãm hoặc tour đêm, sự kiện hiện đại thường được tổ chức tại di tích này ngày nay."""

class KnowledgeAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Cultural Knowledge Expert Agent"

    def retrieve(self, visual_findings: str, ocr_findings: Optional[str], query: str, focus_directive: str = "") -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Dựa trên kết quả quan sát thị giác và chữ viết trích xuất dưới đây, hãy truy xuất tri thức chuyên sâu về di tích/tác phẩm này:

[BÁO CÁO THỊ GIÁC TỪ VISUAL AGENT]:
{visual_findings}

[BÁO CÁO VĂN TỰ TỪ OCR AGENT (NẾU CÓ)]:
{ocr_findings or "Không có văn tự đặc biệt được ghi nhận."}

[CÂU HỎI CỦA NGƯỜI DÙNG]:
"{query}"

[CHỈ THỊ TRỌNG TÂM]:
"{focus_directive or 'Cung cấp niên đại, sự tích, giá trị lịch sử và các sự kiện/lễ hội văn hóa liên quan'}"

Hãy tổng hợp nguồn tri thức văn hóa, lịch sử và sự kiện chuẩn xác nhất của Việt Nam."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=KNOWLEDGE_SYSTEM_PROMPT,
            image=None, # Text reasoning
            preferred_provider="openai", # Heterogeneous agent: gọi OpenAI
            temperature=0.3
        )
        return response_text, meta


# ==============================================================================
# 4. TOOL / GENERATION AGENT (OpenAI / Gemini - Sáng tạo & Lập luận chuyên biệt)
# ==============================================================================
GENERATION_SYSTEM_PROMPT = """Bạn là Creative & Analytical Generation Agent (Tác tử Sáng tạo & Lập luận Chuyên biệt).
Bạn đảm nhận các yêu cầu cao cấp cần ngòi bút tài hoa hoặc tư duy đối sánh nghệ thuật tinh tế:

CÁC NĂNG LỰC ĐẶC BIỆT:
1. Thi ca Cổ phong & Tản văn: Sáng tác các bài thơ (thất ngôn bát cú Đường luật, thất ngôn tứ tuyệt, lục bát hoặc song thất lục bát) chuẩn niêm luật, giàu tính tạo hình và chiều sâu triết lý, cảm tác trực tiếp từ cảnh vật trong ảnh.
2. Bình phẩm Mỹ thuật so sánh: So sánh đường nét kiến trúc trong ảnh với phong cách các thời kỳ lịch sử khác (ví dụ nét đẫy đà, hoành tráng thời Lý - Trần so với nét chạm khắc rồng mây tinh xảo thời Lê Trung Hưng hay phong cách hoàng cung thời Nguyễn).
3. Lập luận giải quyết câu hỏi hóc búa: Phân tích lập luận chặt chẽ cho các câu hỏi thử thách tư duy của người dùng.

Hãy giữ giọng văn truyền cảm hứng, giàu chất thơ và đậm đà phong vị văn hóa dân tộc."""

class GenerationAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Creative & Synthesis Generation Agent"

    def generate(self, query: str, visual_findings: str, knowledge_findings: str, focus_directive: str = "") -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Hãy thực hiện yêu cầu sáng tạo hoặc lập luận chuyên biệt sau:

Câu hỏi / Yêu cầu người dùng: "{query}"
Định hướng sáng tác / phân tích: "{focus_directive or 'Sáng tác nghệ thuật hoặc phân tích chuyên biệt theo đúng câu hỏi'}"

[DỮ LIỆU THỊ GIÁC]:
{visual_findings}

[DỮ LIỆU TRI THỨC LỊCH SỬ]:
{knowledge_findings}

Hãy thể hiện phong cách văn chương xuất sắc hoặc phân tích chuyên gia sâu sắc theo đúng mong muốn của người dùng."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=GENERATION_SYSTEM_PROMPT,
            image=None,
            preferred_provider="openai", # Heterogeneous agent: gọi OpenAI
            temperature=0.7 # Độ bay bổng nghệ thuật
        )
        return response_text, meta
