import json
from typing import Dict, Any, Tuple
from PIL import Image
from utils.llm_clients import LLMManager, safe_extract_json

COORDINATOR_SYSTEM_PROMPT = """Bạn là Coordinator Agent (Kiến trúc sư Trưởng Điều phối Hệ thống) của Hệ thống Multi-Agent VQA Di tích Lịch sử & Văn hóa Nghệ thuật Việt Nam.

NHIỆM VỤ CỦA BẠN:
1. Quan sát bức ảnh và phân tích câu hỏi / yêu cầu của người dùng.
2. Phân loại yêu cầu vào 1 hoặc nhiều nhóm tác vụ sau:
   - QA_Fact: Hỏi đáp thông tin sự kiện, nhân vật, tên địa danh, niên đại, tác giả.
   - Visual_Description: Phân tích kiến trúc (mái đao, hoa văn, kết cấu gỗ), bố cục, màu sắc, hiện trạng di tích hoặc phong cách mỹ thuật.
   - OCR_Translation: Đọc, giải nghĩa và dịch chữ Hán, Nôm, chữ Quốc ngữ cổ, bia đá, hoành phi, câu đối, biển chỉ dẫn xuất hiện trong ảnh.
   - Creative: Yêu cầu sáng tác thơ ca (thất ngôn, lục bát), cảm tác nghệ thuật, lời bình truyền cảm hứng, viết lời thuyết minh du lịch.
   - Knowledge_Search: Truy xuất tri thức lịch sử sâu, bối cảnh triều đại (Lý, Trần, Lê, Nguyễn...), giai thoại tâm linh, phong tục và các sự kiện, lễ hội văn hóa diễn ra tại địa điểm đó.

3. LẬP KẾ HOẠCH THỰC THI (Execution Plan) - Chọn những Expert Agents cần thiết:
   - "visual_agent": BẮT BUỘC hầu như luôn cần để quan sát thị giác, nhận diện đặc điểm kiến trúc và định danh di tích.
   - "ocr_agent": CHỈ KÍCH HOẠT khi phát hiện hoặc nghi ngờ có chữ viết (Hán Nôm, thư pháp, hoành phi, câu đối, bia đá, biển tên) trong ảnh HOẶC người dùng có yêu cầu đọc/dịch chữ. Nếu ảnh chỉ là phong cảnh thuần túy không có chữ, KHÔNG kích hoạt để tiết kiệm tài nguyên.
   - "knowledge_agent": KÍCH HOẠT khi cần thông tin lịch sử, niên đại, bối cảnh văn hóa, câu chuyện di sản, hoặc sự kiện/lễ hội hiện tại.
   - "tool_gen_agent": KÍCH HOẠT khi có yêu cầu sáng tác thơ văn (Creative), so sánh phong cách nghệ thuật đối chiếu, hoặc tổng hợp câu hỏi phức tạp.

BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT ĐỐI TƯỢNG JSON chuẩn xác có định dạng sau:
{
  "query_intent": "Tóm tắt ngắn gọn ý định cốt lõi của người dùng",
  "task_categories": ["QA_Fact", "Visual_Description", ...],
  "has_text_or_inscriptions": true / false,
  "selected_agents": ["visual_agent", "ocr_agent", "knowledge_agent", ...],
  "plan_reasoning": "Giải thích chi tiết vì sao chọn hoặc không chọn các agent này",
  "focus_directives": {
    "visual_focus": "Điểm cần quan sát kỹ nhất trong ảnh",
    "knowledge_focus": "Khía cạnh lịch sử/văn hóa cần đào sâu",
    "generation_focus": "Định hướng phong cách sáng tạo hoặc giải thích (nếu có)"
  }
}
"""

class CoordinatorAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Coordinator Agent (Planner/Router)"

    def plan(self, image: Image.Image, query: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Nhận ảnh và câu hỏi, lập Kế hoạch điều phối JSON.
        Trả về: (execution_plan_dict, meta_info)
        """
        prompt = f"""Hãy phân tích bức ảnh và câu hỏi sau đây của người dùng để lập Kế hoạch Điều phối Multi-Agent:

Câu hỏi / Yêu cầu người dùng: "{query}"

Hãy quan sát ảnh kỹ lưỡng, kiểm tra sự hiện diện của chữ viết/câu đối/hoành phi/bia ký, phân loại tác vụ và chọn chính xác các Expert Agents cần gọi."""

        raw_response, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=COORDINATOR_SYSTEM_PROMPT,
            image=image,
            preferred_provider="gemini", # Multimodal quan sát ảnh để định tuyến
            temperature=0.2,
            json_output=True
        )

        plan = safe_extract_json(raw_response)
        
        # Đảm bảo fallback an toàn nếu LLM parse lỗi
        if "selected_agents" not in plan or not isinstance(plan["selected_agents"], list):
            # Fallback mặc định an toàn
            query_lower = query.lower()
            selected = ["visual_agent", "knowledge_agent"]
            categories = ["QA_Fact", "Visual_Description"]
            
            if any(w in query_lower for w in ["chữ", "dịch", "đọc", "đối", "hoành phi", "hán", "nôm", "bia"]):
                selected.append("ocr_agent")
                categories.append("OCR_Translation")
            if any(w in query_lower for w in ["thơ", "sáng tác", "bài thơ", "văn", "cảm tác"]):
                selected.append("tool_gen_agent")
                categories.append("Creative")
                
            plan = {
                "query_intent": query,
                "task_categories": categories,
                "has_text_or_inscriptions": "ocr_agent" in selected,
                "selected_agents": selected,
                "plan_reasoning": "Kế hoạch dự phòng: Kích hoạt các tác tử trọng tâm dựa trên từ khóa ngữ nghĩa của câu hỏi.",
                "focus_directives": {
                    "visual_focus": "Nhận diện di tích và kiến trúc tổng quan",
                    "knowledge_focus": "Lịch sử và giá trị văn hóa",
                    "generation_focus": "Giải đáp yêu cầu đặc thù"
                }
            }

        # Đảm bảo visual_agent luôn có mặt để cung cấp giác quan thị giác
        if "visual_agent" not in plan["selected_agents"]:
            plan["selected_agents"].insert(0, "visual_agent")

        return plan, meta
