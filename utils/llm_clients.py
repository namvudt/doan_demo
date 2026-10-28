import os
import json
import re
import time
import base64
from io import BytesIO
from typing import Optional, Any, Dict, Tuple, Generator
from PIL import Image
from dotenv import load_dotenv

# Tải biến môi trường từ .env nếu có
load_dotenv()

class LLMManager:
    """
    Quản lý tập trung các kết nối LLM (Gemini và OpenAI) với cơ chế fallback thông minh.
    Cho phép cấu hình API keys linh hoạt từ biến môi trường hoặc nhập trực tiếp trên giao diện UI.
    """
    def __init__(self, gemini_api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.gemini_api_key = (gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.openai_api_key = (openai_api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        self._gemini_client = None
        self._openai_client = None

    def reload_env(self):
        """Tự động nạp lại các biến môi trường từ file .env."""
        load_dotenv(override=True)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._gemini_client = None
        self._openai_client = None

    def update_keys(self, gemini_api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        """Cập nhật API Key từ giao diện người dùng hoặc mã nguồn."""
        if gemini_api_key is not None:
            self.gemini_api_key = gemini_api_key.strip()
            self._gemini_client = None
        if openai_api_key is not None:
            self.openai_api_key = openai_api_key.strip()
            self._openai_client = None

    def get_status(self) -> Dict[str, Any]:
        """Kiểm tra trạng thái sẵn sàng của các API và kiến trúc hoạt động."""
        has_gemini = bool(self.gemini_api_key)
        has_openai = bool(self.openai_api_key)
        
        if has_gemini and has_openai:
            mode = "Heterogeneous (Gemini Multimodal + OpenAI Reasoning)"
            description = "Tận dụng tối đa sức mạnh đa mô hình: Gemini xử lý thị giác kiến trúc, OpenAI phân tích chuyên sâu."
        elif has_gemini:
            mode = "Single-API Fallback (Google Gemini toàn bộ)"
            description = "Chỉ có Gemini Key: Tất cả tác tử tự động chuyển sang vận hành bằng Gemini."
        elif has_openai:
            mode = "Single-API Fallback (OpenAI toàn bộ)"
            description = "Chỉ có OpenAI Key: Tất cả tác tử tự động chuyển sang vận hành bằng OpenAI."
        else:
            mode = "Missing API Keys"
            description = "Chưa cung cấp API Key. Vui lòng nhập Gemini hoặc OpenAI API Key để kích hoạt."

        return {
            "has_gemini": has_gemini,
            "has_openai": has_openai,
            "mode": mode,
            "description": description,
            "gemini_model": self.gemini_model,
            "openai_model": self.openai_model
        }

    def _get_gemini_client(self):
        if not self._gemini_client and self.gemini_api_key:
            from google import genai
            self._gemini_client = genai.Client(api_key=self.gemini_api_key)
        return self._gemini_client

    def _get_openai_client(self):
        if not self._openai_client and self.openai_api_key:
            from openai import OpenAI
            base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
            kwargs = {"api_key": self.openai_api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._openai_client = OpenAI(**kwargs)
        return self._openai_client

    def call_llm(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image: Optional[Image.Image] = None,
        preferred_provider: str = "gemini",
        temperature: float = 0.4,
        json_output: bool = False
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Gọi LLM với cơ chế fallback tự động.
        Trả về: (response_text, metadata_info)
        """
        # Xác định provider thực tế sẽ chạy
        actual_provider = preferred_provider
        fallback_used = False

        if preferred_provider == "gemini":
            if not self.gemini_api_key and self.openai_api_key:
                actual_provider = "openai"
                fallback_used = True
        elif preferred_provider == "openai":
            if not self.openai_api_key and self.gemini_api_key:
                actual_provider = "gemini"
                fallback_used = True

        # Kiểm tra xem có key nào dùng được không
        if actual_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("Thiếu Gemini API Key. Vui lòng cấu hình GEMINI_API_KEY hoặc OPENAI_API_KEY.")
        if actual_provider == "openai" and not self.openai_api_key:
            raise ValueError("Thiếu OpenAI API Key. Vui lòng cấu hình OPENAI_API_KEY hoặc GEMINI_API_KEY.")

        meta = {
            "requested_provider": preferred_provider,
            "actual_provider": actual_provider,
            "fallback_used": fallback_used,
            "model_used": self.gemini_model if actual_provider == "gemini" else self.openai_model
        }

        if actual_provider == "gemini":
            res_text = self._call_gemini(
                prompt=prompt,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                json_output=json_output
            )
        else:
            res_text = self._call_openai(
                prompt=prompt,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                json_output=json_output
            )

        return res_text, meta

    def stream_llm(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image: Optional[Image.Image] = None,
        preferred_provider: str = "gemini",
        temperature: float = 0.3,
        typing_delay: float = 0.025
    ) -> Generator[str, None, None]:
        """
        Gọi LLM và phát trực tiếp (Stream) từng token/chunk nội dung.
        Có độ trễ nhẹ typing_delay giữa các từ để tạo hiệu ứng gõ chữ mượt mà, tự nhiên.
        """
        actual_provider = preferred_provider
        if preferred_provider == "gemini":
            if not self.gemini_api_key and self.openai_api_key:
                actual_provider = "openai"
        elif preferred_provider == "openai":
            if not self.openai_api_key and self.gemini_api_key:
                actual_provider = "gemini"

        if actual_provider == "gemini":
            client = self._get_gemini_client()
            from google.genai import types
            config_args = {"temperature": temperature}
            if system_instruction:
                config_args["system_instruction"] = system_instruction
            config = types.GenerateContentConfig(**config_args)

            contents = []
            if image is not None:
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                contents.append(image)
            contents.append(prompt)

            try:
                response = client.models.generate_content_stream(
                    model=self.gemini_model,
                    contents=contents,
                    config=config
                )
                for chunk in response:
                    if chunk.text:
                        # Chia nhỏ thành các từ và khoảng trắng để gõ nhịp nhàng tự nhiên
                        tokens = re.split(r'(\s+)', chunk.text)
                        for token in tokens:
                            if token:
                                yield token
                                if typing_delay > 0:
                                    time.sleep(typing_delay)
            except Exception as e:
                # Fallback sang gọi thông thường nếu stream bị lỗi
                res_text, _ = self.call_llm(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    image=image,
                    preferred_provider=actual_provider,
                    temperature=temperature
                )
                tokens = re.split(r'(\s+)', res_text)
                for token in tokens:
                    if token:
                        yield token
                        if typing_delay > 0:
                            time.sleep(typing_delay)
        else:
            client = self._get_openai_client()
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            user_content = []
            if image is not None:
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                buffered = BytesIO()
                image.save(buffered, format="JPEG", quality=85)
                img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                })
            user_content.append({"type": "text", "text": prompt})
            messages.append({"role": "user", "content": user_content if image is not None else prompt})

            try:
                response = client.chat.completions.create(
                    model=self.openai_model,
                    messages=messages,
                    temperature=temperature,
                    stream=True
                )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        tokens = re.split(r'(\s+)', chunk.choices[0].delta.content)
                        for token in tokens:
                            if token:
                                yield token
                                if typing_delay > 0:
                                    time.sleep(typing_delay)
            except Exception as e:
                res_text, _ = self.call_llm(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    image=image,
                    preferred_provider=actual_provider,
                    temperature=temperature
                )
                tokens = re.split(r'(\s+)', res_text)
                for token in tokens:
                    if token:
                        yield token
                        if typing_delay > 0:
                            time.sleep(typing_delay)

    def _call_gemini(
        self,
        prompt: str,
        system_instruction: Optional[str],
        image: Optional[Image.Image],
        temperature: float,
        json_output: bool
    ) -> str:
        from utils.logger import log_api_call, log_api_success, log_error
        import time

        client = self._get_gemini_client()
        from google.genai import types

        config_args = {"temperature": temperature}
        if system_instruction:
            config_args["system_instruction"] = system_instruction
        if json_output:
            config_args["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_args)

        contents = []
        if image is not None:
            # Chuyển ảnh RGB nếu là RGBA hoặc P để tương thích
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            contents.append(image)
        contents.append(prompt)

        log_api_call("Gemini", self.gemini_model, has_image=(image is not None), prompt_len=len(prompt))
        t0 = time.time()
        try:
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=contents,
                config=config
            )
            res_text = response.text or ""
            dur = time.time() - t0
            log_api_success("Gemini", self.gemini_model, dur, len(res_text))
            return res_text
        except Exception as e:
            log_error(
                caller_name="LLMManager._call_gemini",
                error=e,
                details=f"Model: {self.gemini_model} | Has Image: {image is not None} | JSON Mode: {json_output}"
            )
            raise e

    def _call_openai(
        self,
        prompt: str,
        system_instruction: Optional[str],
        image: Optional[Image.Image],
        temperature: float,
        json_output: bool
    ) -> str:
        from utils.logger import log_api_call, log_api_success, log_error
        import time

        client = self._get_openai_client()

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        user_content = []
        if image is not None:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffered = BytesIO()
            image.save(buffered, format="JPEG", quality=85)
            img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
        
        user_content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": user_content if image is not None else prompt})

        kwargs = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": temperature
        }
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}

        log_api_call("OpenAI", self.openai_model, has_image=(image is not None), prompt_len=len(prompt))
        t0 = time.time()
        try:
            response = client.chat.completions.create(**kwargs)
            res_text = response.choices[0].message.content or ""
            dur = time.time() - t0
            log_api_success("OpenAI", self.openai_model, dur, len(res_text))
            return res_text
        except Exception as e:
            log_error(
                caller_name="LLMManager._call_openai",
                error=e,
                details=f"Model: {self.openai_model} | Has Image: {image is not None} | JSON Mode: {json_output}"
            )
            raise e


def safe_extract_json(text: str) -> Dict[str, Any]:
    """
    Trích xuất và parse JSON an toàn từ phản hồi của LLM.
    Xử lý các trường hợp markdown codeblocks ```json ... ``` hoặc văn bản kèm theo.
    """
    if not text or not isinstance(text, str):
        return {}
    
    # 1. Thử parse trực tiếp
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    # 2. Tìm khối code ```json ... ``` hoặc ``` ... ```
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except Exception:
            pass

    # 3. Tìm khối từ dấu ngoặc nhọn đầu tiên đến ngoặc nhọn cuối cùng { ... }
    bracket_match = re.search(r'(\{[\s\S]*\})', text)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(1).strip())
        except Exception:
            pass

    return {"error": "Không thể trích xuất JSON hợp lệ", "raw_content": text}
