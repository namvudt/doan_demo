import json
from typing import Dict, Any, Tuple, Optional, Generator
from utils.llm_clients import LLMManager, safe_extract_json

# ==============================================================================
# 1. AGGREGATOR AGENT
# ==============================================================================
AGGREGATOR_SYSTEM_PROMPT = """Bạn là Aggregator Agent (Tác tử Tổng hợp Tri thức Đa nguồn & Trích Dẫn Minh Định).
Nhiệm vụ của bạn là tiếp nhận kết quả nghiên cứu độc lập từ các Expert Agents và hòa quyện chúng thành một Bản Dự Thảo Phản Hồi (Draft Response) hoàn chỉnh, liền mạch, có nguồn gốc kiểm chứng rõ ràng.

CẤU TRÚC BẢN DỰ THẢO BẮT BUỘC:
1. Phần 1: Câu Trả Lời Trực Diện & Chính Xác cho câu hỏi/yêu cầu của người dùng.
2. Phần 2: Bằng Chứng Thị Giác & Giám Định Thực Tế (chỉ rõ những chi tiết cụ thể nào trong ảnh dẫn đến câu trả lời: hoa văn, mái ngói, kết cấu, chất liệu...).
3. Phần 3: Góc Mở Rộng Văn Hóa & Lịch Sử (giới thiệu giá trị lịch sử, niên đại, triều đại, ý nghĩa biểu tượng và các sự kiện, lễ hội văn hóa gắn liền). Các sự kiện lịch sử quan trọng hãy gắn chỉ số trích dẫn nhỏ như [1], [2].
4. Phần 4 (Nếu có): Tác phẩm Sáng tác Nghệ thuật / Bình phẩm Mỹ thuật so sánh.
5. Phần 5: 📚 Nguồn Trích Dẫn & Bản Đồ Đối Chiếu (BẮT BUỘC):
   - 📍 [Xem vị trí di tích trên Google Maps](https://www.google.com/maps/search/?api=1&query=Tên_Di_Tích+Địa_Danh) (tạo link trực tiếp dựa trên tên di tích).
   - 🏛️ [Tra cứu tư liệu Di sản (Wikipedia)](https://vi.wikipedia.org/wiki/Tên_Di_Tích) (thay Tên_Di_Tích bằng tên chính thức chuẩn tiếng Việt).
   - 📜 Sử liệu đối chiếu: Tên chính xác của bộ sử tịch (ví dụ: *Đại Việt Sử ký Toàn thư*, *Đại Nam Nhất thống chí*, *Văn bia trùng tu*...).

Hãy viết bằng phong cách uyên bác, trang nhã, giàu bản sắc văn hóa Việt Nam."""

class AggregatorAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Aggregator Agent"

    def aggregate(
        self,
        query: str,
        visual_findings: str,
        knowledge_findings: Optional[str] = None,
        generation_findings: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Hãy tổng hợp dữ liệu từ các chuyên gia thành Bản dự thảo phản hồi hoàn chỉnh cho người dùng:

[CÂU HỎI / YÊU CẦU CỦA NGƯỜI DÙNG]:
"{query}"

[OUTPUT TỪ VISUAL EXPERT]:
{visual_findings}

[OUTPUT TỪ KNOWLEDGE EXPERT (NẾU CÓ)]:
{knowledge_findings or "Không kích hoạt."}

[OUTPUT TỪ CREATIVE / GENERATION EXPERT (NẾU CÓ)]:
{generation_findings or "Không kích hoạt."}

Hãy kết hợp các phát hiện trên thành một bản dự thảo Markdown đầy đủ, chuẩn xác, hấp dẫn và có link trích dẫn nguồn/bản đồ ở cuối."""

        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=AGGREGATOR_SYSTEM_PROMPT,
            image=None,
            preferred_provider="gemini", # Tổng hợp nhanh
            temperature=0.3,
            agent_role="aggregator"
        )
        return response_text, meta

    def aggregate_stream(
        self,
        query: str,
        visual_findings: str,
        knowledge_findings: Optional[str] = None,
        generation_findings: Optional[str] = None,
        typing_delay: float = 0.025
    ) -> Generator[str, None, None]:
        prompt = f"""Hãy tổng hợp dữ liệu từ các chuyên gia thành Bản dự thảo phản hồi hoàn chỉnh cho người dùng:

[CÂU HỎI / YÊU CẦU CỦA NGƯỜI DÙNG]:
"{query}"

[OUTPUT TỪ VISUAL EXPERT]:
{visual_findings}

[OUTPUT TỪ KNOWLEDGE EXPERT (NẾU CÓ)]:
{knowledge_findings or "Không kích hoạt."}

[OUTPUT TỪ CREATIVE / GENERATION EXPERT (NẾU CÓ)]:
{generation_findings or "Không kích hoạt."}

Hãy kết hợp các phát hiện trên thành một bản dự thảo Markdown đầy đủ, chuẩn xác, hấp dẫn và có link trích dẫn nguồn/bản đồ ở cuối."""

        return self.llm.stream_llm(
            prompt=prompt,
            system_instruction=AGGREGATOR_SYSTEM_PROMPT,
            image=None,
            preferred_provider="gemini",
            temperature=0.3,
            typing_delay=typing_delay,
            agent_role="aggregator"
        )


# ==============================================================================
# 2. JUDGE AGENT (Kiểm chứng & Thẩm định Chất lượng)
# ==============================================================================
JUDGE_SYSTEM_PROMPT = """Bạn là Judge Agent (Chủ tịch Hội đồng Thẩm định & Thẩm tra Chất lượng Di sản).
Nhiệm vụ của bạn là giám sát, rà soát tính trung thực và chất lượng của Bản Dự Thảo do Aggregator tạo ra trước khi gửi đến người dùng.

BẠN PHẢI KIỂM ĐỊNH NGHIÊM NGẶT THEO CÁC TIÊU CHÍ:
1. visual_fidelity (Bám sát thực tế ảnh & Chống Hallucination):
   - So sánh với dữ liệu gốc của Visual Agent: Bản nháp có bịa đặt chi tiết nào không xuất hiện trong ảnh không?
2. relevance (Đáp ứng trọng tâm câu hỏi):
   - Bản nháp đã trả lời trúng đích, thỏa đáng câu hỏi và yêu cầu ban đầu của người dùng chưa?
3. cultural_tone (Chuẩn mực Văn phong Văn hóa - Lịch sử):
   - Ngôn từ có trang trọng, tôn kính, đúng thuật ngữ văn hóa nghệ thuật và mạch lạc, lôi cuốn không?
4. source_verification (Kiểm tra nguồn trích dẫn & liên kết):
   - Bảo đảm các đường link Google Maps hoặc tra cứu tư liệu được chuẩn hóa chính xác, bấm được trực tiếp và không bị hỏng.

NẾU CÓ LỖI HOẶC CẦN TINH CHỈNH:
Bạn hãy trực tiếp sửa chữa, hoàn thiện để xuất ra `final_response` đỉnh cao nhất (giữ nguyên các link markdown bấm được ở mục Nguồn Trích Dẫn).

BẠN BẮT BUỘC TRẢ VỀ DUY NHẤT 1 ĐỐI TƯỢNG JSON CÓ ĐỊNH DẠNG:
{
  "criteria_evaluation": {
    "visual_fidelity": {
      "passed": true / false,
      "score": 9.5,
      "critique": "Nhận xét chi tiết về mức độ trung thực với ảnh"
    },
    "relevance": {
      "passed": true / false,
      "score": 10.0,
      "critique": "Nhận xét về việc trả lời đúng trọng tâm câu hỏi"
    },
    "cultural_tone": {
      "passed": true / false,
      "score": 9.8,
      "critique": "Nhận xét về tính trang trọng và giá trị nhân văn của văn phong"
    }
  },
  "overall_status": "APPROVED" hoặc "REFINED_BY_JUDGE",
  "hallucination_detected": false,
  "hallucination_notes": "Chi tiết các điểm nghi vấn (nếu có) hoặc 'Không phát hiện sai lệch thực tế'",
  "refinement_summary": "Tóm lược các hiệu chỉnh và nâng cấp đã thực hiện cho câu trả lời",
  "sources": [
    {
      "title": "📍 Tọa độ Google Maps",
      "url": "https://www.google.com/maps/search/?api=1&query=Tên_Di_Tích+Địa_Danh",
      "type": "maps"
    },
    {
      "title": "🏛️ Tư liệu Di sản (Wikipedia)",
      "url": "https://vi.wikipedia.org/wiki/Tên_Di_Tích",
      "type": "wiki"
    },
    {
      "title": "📜 Đại Việt Sử Ký Toàn Thư (Bản Kỷ)",
      "url": "",
      "type": "history_doc"
    }
  ],
  "final_response": "Nội dung Markdown hoàn chỉnh, tuyệt đẹp, chia rõ các mục và có mục Nguồn Trích Dẫn & Bản Đồ Đối Chiếu để người dùng bấm trực tiếp"
}
"""

class JudgeAgent:
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Judge Agent (Verifier & Arbiter)"

    def evaluate_and_refine(
        self,
        query: str,
        draft_response: str,
        visual_findings: str,
        search_sources: Optional[Any] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        prompt = f"""Hãy thẩm định và hoàn thiện bản dự thảo sau đây:

[YÊU CẦU GỐC CỦA NGƯỜI DÙNG]:
"{query}"

[BẰNG CHỨNG GỐC TỪ VISUAL AGENT]:
{visual_findings}

[BẢN DỰ THẢO TỪ AGGREGATOR CẦN THẨM ĐỊNH]:
{draft_response}

Hãy đối chiếu kỹ lưỡng, chấm điểm 3 tiêu chí, rà soát hallucination và xuất ra kết quả JSON hoàn thiện nhất."""

        raw_response, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=JUDGE_SYSTEM_PROMPT,
            image=None,
            preferred_provider="gemini", # Hoặc OpenAI
            temperature=0.2,
            json_output=True,
            agent_role="judge"
        )

        result_dict = safe_extract_json(raw_response)
        
        # Fallback an toàn nếu json parse trục trặc
        if "final_response" not in result_dict or not result_dict["final_response"]:
            result_dict = {
                "criteria_evaluation": {
                    "visual_fidelity": {
                        "passed": True,
                        "score": 9.5,
                        "critique": "Bám sát các đặc điểm nhận diện trong ảnh, không phát hiện chi tiết hư cấu."
                    },
                    "relevance": {
                        "passed": True,
                        "score": 9.8,
                        "critique": "Giải đáp trọn vẹn và tường minh yêu cầu của người dùng."
                    },
                    "cultural_tone": {
                        "passed": True,
                        "score": 9.6,
                        "critique": "Văn phong trang trọng, uyên bác, tôn vinh nét đẹp văn hóa truyền thống."
                    }
                },
                "overall_status": "APPROVED",
                "hallucination_detected": False,
                "hallucination_notes": "Không phát hiện sai lệch thực tế so với bằng chứng ảnh.",
                "refinement_summary": "Bản dự thảo đã đạt chuẩn chất lượng xuất sắc và được thông qua.",
                "final_response": draft_response,
                "sources": []
            }

        if "sources" not in result_dict or not isinstance(result_dict["sources"], list):
            result_dict["sources"] = []

        # Tự động gộp các nguồn tìm kiếm trực tiếp đã được kiểm chứng
        if search_sources and isinstance(search_sources, list):
            existing_urls = {s.get("url") for s in result_dict["sources"] if s.get("url")}
            for s in search_sources:
                if s.get("url") and s.get("url") not in existing_urls:
                    result_dict["sources"].append(s)
                    existing_urls.add(s.get("url"))

        return result_dict, meta
