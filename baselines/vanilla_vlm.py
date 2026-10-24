import time
from typing import Dict, Any, Tuple
from PIL import Image
from utils.llm_clients import LLMManager

class VanillaVLMBaseline:
    """
    Baseline 1: Vanilla Single-Prompt Vision-Language Model.
    Mô hình VLM cơ sở chạy trực tiếp với một Prompt đơn lẻ duy nhất,
    KHÔNG phân chia Agent, KHÔNG có công cụ hỗ trợ và KHÔNG có hội đồng kiểm chứng.
    """
    def __init__(self, llm_manager: LLMManager):
        self.llm = llm_manager
        self.name = "Baseline 1: Vanilla VLM (Single-Prompt)"

    def run(self, image: Image.Image, query: str) -> Tuple[str, Dict[str, Any]]:
        prompt = f"""Bạn là một trợ lý AI tổng quát. Hãy quan sát bức ảnh và trả lời câu hỏi sau đây của người dùng:

Câu hỏi: "{query}"

Hãy cung cấp câu trả lời rõ ràng và ngắn gọn."""

        t0 = time.time()
        response_text, meta = self.llm.call_llm(
            prompt=prompt,
            system_instruction="Bạn là trợ lý AI thông thường.",
            image=image,
            preferred_provider="gemini",
            temperature=0.3
        )
        duration = round(time.time() - t0, 2)

        meta_info = {
            "baseline": "Baseline 1 (Vanilla VLM)",
            "duration": duration,
            "provider": meta.get("actual_provider", ""),
            "model": meta.get("model_used", ""),
            "num_agents": 1,
            "has_verifier": False,
            "has_tools": False
        }

        return response_text, meta_info
