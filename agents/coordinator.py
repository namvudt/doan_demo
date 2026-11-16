from typing import Any, Dict, Tuple

from PIL import Image

from core.schemas import ExecutionPlan
from utils.llm_clients import LLMManager, safe_extract_json

COORDINATOR_SYSTEM_PROMPT = """Bạn là Coordinator Agent (Kiến trúc sư Trưởng Điều phối Hệ thống) của Hệ thống Multi-Agent VQA Di tích Lịch sử & Văn hóa Nghệ thuật Việt Nam.

NHIỆM VỤ CỦA BẠN:
1. Quan sát bức ảnh và phân tích câu hỏi / yêu cầu của người dùng.
2. Phân loại yêu cầu vào 1 hoặc nhiều nhóm tác vụ sau:
   - QA_Fact: Hỏi đáp thông tin sự kiện, nhân vật, tên địa danh, niên đại, tác giả.
   - Visual_Description: Phân tích kiến trúc (mái đao, hoa văn, kết cấu gỗ), bố cục, màu sắc, hiện trạng di tích hoặc phong cách mỹ thuật.
   - Creative: Yêu cầu sáng tác thơ ca (thất ngôn, lục bát), cảm tác nghệ thuật, lời bình truyền cảm hứng, viết lời thuyết minh du lịch.
   - Knowledge_Search: Truy xuất tri thức lịch sử sâu, bối cảnh triều đại (Lý, Trần, Lê, Nguyễn...), giai thoại tâm linh, phong tục và các sự kiện, lễ hội văn hóa diễn ra tại địa điểm đó.

3. LẬP KẾ HOẠCH THỰC THI (Execution Plan) - Chọn những Expert Agents cần thiết:
   - "visual_agent": BẮT BUỘC hầu như luôn cần để quan sát thị giác, nhận diện đặc điểm kiến trúc và định danh di tích.
   - "knowledge_agent": KÍCH HOẠT khi cần thông tin lịch sử, niên đại, bối cảnh văn hóa, câu chuyện di sản, hoặc sự kiện/lễ hội hiện tại.
   - "tool_gen_agent": KÍCH HOẠT khi có yêu cầu sáng tác thơ văn (Creative), so sánh phong cách nghệ thuật đối chiếu, hoặc tổng hợp câu hỏi phức tạp.

BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT ĐỐI TƯỢNG JSON chuẩn xác có định dạng sau:
{
  "query_intent": "Tóm tắt ngắn gọn ý định cốt lõi của người dùng",
  "identified_monument": "Tên di tích/công trình được nhận diện sơ bộ qua ảnh (ví dụ: Chùa Một Cột, Khuê Văn Các, Cố đô Huế...)",
  "task_categories": ["QA_Fact", "Visual_Description", ...],
  "selected_agents": ["visual_agent", "knowledge_agent", ...],
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

Hãy quan sát ảnh kỹ lưỡng, định danh sơ bộ di tích/công trình kiến trúc trong ảnh, phân loại tác vụ và chọn chính xác các Expert Agents cần gọi."""

        if self.llm.config.accuracy.enabled:
            prompt += "\nTách yêu cầu thành requested_slots: slot_id, question, evidence_type (visual/historical/identity/mixed). Không gộp nhiều ý vào một slot. candidates tối đa 3 ứng viên có name/reason, không ép chọn di tích. regions chỉ các vùng chữ cần OCR, box=[x1,y1,x2,y2] chuẩn hóa theo ảnh gốc 0..1 và purpose. Ảnh mờ hoặc dữ kiện không xác định phải giữ bất định. Các tên và thông tin người dùng là giả thuyết, không phải kết luận. Không suy niên đại từ hình dáng."
        system = COORDINATOR_SYSTEM_PROMPT
        if self.llm.config.accuracy.enabled:
            system += "\nChế độ dựa trên bằng chứng: giữ plan_reasoning và focus_directives ngắn, không nhét đáp án hay niên đại đoán sẵn vào kế hoạch. Tên ứng viên ngắn, tên quần thể/địa phương là qualifier, không coi hai biến thể tên là hai công trình. Không chép/phiên âm/dịch chữ Hán–Nôm hay dùng chúng như dữ kiện chắc chắn; regions chỉ dành cho chữ Quốc ngữ/Latin thực sự cần đọc. Không suy thành phần vật liệu hay loại đá từ ảnh."
        raw_response, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=system,
            image=image,
            preferred_provider="gemini",  # Multimodal quan sát ảnh để định tuyến
            temperature=0.2,
            json_output=True,
            agent_role="coordinator",
            response_schema=ExecutionPlan,
        )

        plan = ExecutionPlan.model_validate(safe_extract_json(raw_response))
        return plan.model_dump(), meta
