import time
from typing import Dict, Any, Tuple
from PIL import Image
from utils.llm_clients import LLMManager

GENERIC_AGENT_PROMPT = """Bạn là một Generic Tool-Calling AI Agent (Tác tử sử dụng công cụ thông thường theo mô hình ReAct / Tool-Use cơ bản).

Bạn có quyền truy cập vào các công cụ mô phỏng sau:
1. generic_ocr(image): Đọc văn bản tiếng Latinh / tiếng Anh thông thường trong ảnh.
2. general_search(keyword): Tra cứu thông tin trên Internet.

QUY TRÌNH XỬ LÝ (ReAct Paradigm):
1. Thought: Suy nghĩ xem cần công cụ gì để trả lời câu hỏi của người dùng.
2. Action: Gọi công cụ tương ứng (mô phỏng).
3. Observation: Nhận kết quả từ công cụ.
4. Final Answer: Đưa ra câu trả lời cuối cùng.

"""

class GenericToolAgentBaseline:
    """
    Baseline 2: Generic Tool-Calling Agent (Mô hình Agentic cơ sở theo chuẩn OWLViz).
    Sử dụng cơ chế Tool-use cơ bản, nhưng thiếu sự phối hợp chuyên môn hóa (Heterogeneous)
    và không có cơ chế thẩm định kiểm soát ảo giác (No Judge / Verifier).
    """
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Baseline 2: Generic Tool-Calling Agent"

    def run(self, image: Image.Image, query: str) -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Hãy thực hiện quy trình Tool-Calling để giải quyết yêu cầu sau của người dùng:

Câu hỏi: "{query}"

Hãy thực hiện từng bước Thought, Action, Observation và đưa ra Final Answer."""

        t0 = time.time()
        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction=GENERIC_AGENT_PROMPT,
            image=image,
            preferred_provider="gemini",
            temperature=0.3
        )
        duration = round(time.time() - t0, 2)

        meta_info = {
            "baseline": "Baseline 2 (Generic Tool-Calling Agent)",
            "duration": duration,
            "provider": meta.get("actual_provider", ""),
            "model": meta.get("model_used", ""),
            "num_agents": 1,
            "has_verifier": False,
            "has_tools": True
        }

        return response_text, meta_info
