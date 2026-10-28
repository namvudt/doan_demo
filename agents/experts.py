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
            temperature=0.3,
            agent_role="visual"
        )
        return response_text, meta


# ==============================================================================
# 2. KNOWLEDGE AGENT (OpenAI / Gemini - Tri thức Lịch sử & Sự kiện Văn hóa)
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
   - Các hoạt động văn hóa, triển lãm hoặc tour đêm, sự kiện hiện đại thường được tổ chức tại di tích này ngày nay.
4. Nguồn Tư Liệu & Địa Danh Tham Chiếu:
   - Trích dẫn rõ tên các bộ sử tịch cổ liên quan (Đại Việt Sử Ký Toàn Thư, Khâm Định Việt Sử Thông Giám Cương Mục, Văn bia trùng tu...).
   - Địa chỉ hành chính cụ thể và từ khóa chuẩn để định vị bản đồ vệ tinh.
   - Các cổng thông tin nghiên cứu uy tín (Wikipedia, Cục Di sản Văn hóa, Bảo tàng Lịch sử Quốc gia...)."""

from utils.heritage_search import HeritageSearchEngine

class KnowledgeAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Cultural Knowledge Expert Agent"
        self.search_engine = HeritageSearchEngine()

    def retrieve(
        self,
        query: str,
        monument_hint: str = "",
        visual_findings: str = "",
        focus_directive: str = ""
    ) -> Tuple[str, Dict[str, Any]]:
        # Kích hoạt Cơ chế tìm kiếm trực tiếp (Live Direct Search Grounding)
        search_data = self.search_engine.search_heritage(monument_hint=monument_hint, query=query)

        prompt = f"""Dựa trên di tích/công trình được nhận diện dưới đây, hãy truy xuất tri thức chuyên sâu:

[DI TÍCH / TÁC PHẨM NHẬN DIỆN]:
{monument_hint or 'Di tích lịch sử trong bức ảnh'}

[ĐẶC ĐIỂM THỊ GIÁC (NẾU CÓ)]:
{visual_findings or 'Đang được giám định song song bởi Visual Expert'}

[DỮ LIỆU TÌM KIẾM TRỰC TIẾP TỪ NGUỒN CHÍNH THỐNG (LIVE GROUNDING)]:
{search_data['context_text']}

[CÂU HỎI CỦA NGƯỜI DÙNG]:
"{query}"

[CHỈ THỊ TRỌNG TÂM]:
"{focus_directive or 'Cung cấp niên đại, sự tích, giá trị lịch sử và các sự kiện/lễ hội văn hóa liên quan'}"

Hãy kết hợp tri thức sử liệu uyên bác cùng dữ liệu tìm kiếm trực tiếp trên để cung cấp thông tin chuẩn xác nhất, có trích dẫn nguồn cụ thể."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=KNOWLEDGE_SYSTEM_PROMPT,
            image=None, # Text reasoning
            preferred_provider="openai", # Heterogeneous agent: gọi OpenAI
            temperature=0.3,
            agent_role="knowledge"
        )
        meta["live_search_sources"] = search_data.get("sources", [])
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

    def generate(
        self,
        query: str,
        monument_hint: str = "",
        visual_findings: str = "",
        knowledge_findings: str = "",
        focus_directive: str = ""
    ) -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Hãy thực hiện yêu cầu sáng tạo hoặc lập luận chuyên biệt sau:

Câu hỏi / Yêu cầu người dùng: "{query}"
Định hướng sáng tác / phân tích: "{focus_directive or 'Sáng tác nghệ thuật hoặc phân tích chuyên biệt theo đúng câu hỏi'}"

[ĐỊNH DANH DI TÍCH]:
{monument_hint or 'Di tích văn hóa lịch sử trong ảnh'}

[DỮ LIỆU THỊ GIÁC (NẾU CÓ)]:
{visual_findings or 'Xem xét trên bình diện cảnh quan tổng thể'}

[DỮ LIỆU TRI THỨC LỊCH SỬ (NẾU CÓ)]:
{knowledge_findings or 'Bối cảnh lịch sử di sản Việt Nam'}

Hãy thể hiện phong cách văn chương xuất sắc hoặc phân tích chuyên gia sâu sắc theo đúng mong muốn của người dùng."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=GENERATION_SYSTEM_PROMPT,
            image=None,
            preferred_provider="openai", # Heterogeneous agent: gọi OpenAI
            temperature=0.7, # Độ bay bổng nghệ thuật
            agent_role="generation"
        )
        return response_text, meta
