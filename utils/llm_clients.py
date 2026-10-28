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
        
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        self._gemini_client = None
        self._openai_client = None

        # Bể chứa API Key riêng cho từng Agent (Agent Key Pool)
        self.agent_keys = {
            "coordinator": os.getenv("COORDINATOR_API_KEY", "").strip(),
            "visual": os.getenv("VISUAL_API_KEY", "").strip(),
            "knowledge": os.getenv("KNOWLEDGE_API_KEY", "").strip(),
            "generation": os.getenv("GENERATION_API_KEY", "").strip(),
            "aggregator": os.getenv("AGGREGATOR_API_KEY", "").strip(),
            "judge": os.getenv("JUDGE_API_KEY", "").strip(),
        }
        self._agent_clients: Dict[str, Any] = {}

    def reload_env(self):
        """Tự động nạp lại các biến môi trường từ file .env."""
        load_dotenv(override=True)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._gemini_client = None
        self._openai_client = None

        # Tải lại bể API key cho từng agent
        self.agent_keys = {
            "coordinator": os.getenv("COORDINATOR_API_KEY", "").strip(),
            "visual": os.getenv("VISUAL_API_KEY", "").strip(),
            "knowledge": os.getenv("KNOWLEDGE_API_KEY", "").strip(),
            "generation": os.getenv("GENERATION_API_KEY", "").strip(),
            "aggregator": os.getenv("AGGREGATOR_API_KEY", "").strip(),
            "judge": os.getenv("JUDGE_API_KEY", "").strip(),
        }
        self._agent_clients.clear()

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

        # Đếm số lượng Agent đã có key riêng
        dedicated_count = sum(1 for k in self.agent_keys.values() if k)
        
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

        # Thống kê chi tiết bể khóa từng Agent
        agent_status = {}
        role_labels = {
            "coordinator": "Coordinator (Điều phối)",
            "visual": "Visual (Thị giác)",
            "knowledge": "Knowledge (Sử liệu)",
            "generation": "Generation (Sáng tác)",
            "aggregator": "Aggregator (Tổng hợp)",
            "judge": "Judge (Thẩm định)"
        }
        for role, label in role_labels.items():
            k = self.agent_keys.get(role, "")
            if k:
                prov = "xKiro/OpenAI" if k.startswith("sk-") else "Gemini"
                agent_status[role] = {"label": label, "status": f"Khóa riêng ({prov})", "has_custom": True}
            else:
                agent_status[role] = {"label": label, "status": "Dùng khóa mặc định chung", "has_custom": False}

        return {
            "has_gemini": has_gemini,
            "has_openai": has_openai,
            "mode": mode,
            "description": description,
            "gemini_model": self.gemini_model,
            "openai_model": self.openai_model,
            "dedicated_keys_count": dedicated_count,
            "agent_keys_status": agent_status
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

    def _resolve_agent_client(self, agent_role: Optional[str], preferred_provider: str) -> Tuple[str, Any, str, bool]:
        """
        Xác định Client và Model tương ứng cho Agent cụ thể.
        Nếu Agent có API Key riêng trong agent_keys -> Dùng key riêng đó.
        Nếu không -> Dùng khóa mặc định của hệ thống theo preferred_provider hoặc fallback.
        Trả về: (actual_provider, client_instance, model_name, is_dedicated)
        """
        role = (agent_role or "").lower().strip()
        custom_key = self.agent_keys.get(role, "")

        if custom_key:
            if custom_key.startswith("sk-"):
                if role not in self._agent_clients:
                    from openai import OpenAI
                    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
                    kwargs = {"api_key": custom_key}
                    if base_url:
                        kwargs["base_url"] = base_url
                    self._agent_clients[role] = OpenAI(**kwargs)
                return "openai", self._agent_clients[role], self.openai_model, True
            else:
                if role not in self._agent_clients:
                    from google import genai
                    self._agent_clients[role] = genai.Client(api_key=custom_key)
                return "gemini", self._agent_clients[role], self.gemini_model, True

        # Fallback về cấu hình chung
        actual_provider = preferred_provider
        if preferred_provider == "gemini":
            if not self.gemini_api_key and self.openai_api_key:
                actual_provider = "openai"
        elif preferred_provider == "openai":
            if not self.openai_api_key and self.gemini_api_key:
                actual_provider = "gemini"

        if actual_provider == "gemini":
            client = self._get_gemini_client()
            if not client:
                raise ValueError("Thiếu Gemini API Key. Vui lòng cấu hình GEMINI_API_KEY.")
            return "gemini", client, self.gemini_model, False
        else:
            client = self._get_openai_client()
            if not client:
                raise ValueError("Thiếu OpenAI API Key. Vui lòng cấu hình OPENAI_API_KEY.")
            return "openai", client, self.openai_model, False

    def call_llm(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image: Optional[Image.Image] = None,
        preferred_provider: str = "gemini",
        temperature: float = 0.4,
        json_output: bool = False,
        agent_role: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Gọi LLM với cơ chế phân bổ API Key chuyên biệt theo Agent hoặc Fallback tự động.
        Trả về: (response_text, metadata_info)
        """
        actual_provider, client, model_name, is_dedicated = self._resolve_agent_client(agent_role, preferred_provider)

        meta = {
            "agent_role": agent_role or "general",
            "requested_provider": preferred_provider,
            "actual_provider": actual_provider,
            "dedicated_key": is_dedicated,
            "model_used": model_name
        }

        if actual_provider == "gemini":
            res_text = self._call_gemini(
                prompt=prompt,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                json_output=json_output,
                client=client,
                model_name=model_name
            )
        else:
            res_text = self._call_openai(
                prompt=prompt,
                system_instruction=system_instruction,
                image=image,
                temperature=temperature,
                json_output=json_output,
                client=client,
                model_name=model_name
            )

        return res_text, meta

    def stream_llm(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image: Optional[Image.Image] = None,
        preferred_provider: str = "gemini",
        temperature: float = 0.3,
        typing_delay: float = 0.025,
        agent_role: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        Gọi LLM và phát trực tiếp (Stream) từng token/chunk nội dung.
        Hỗ trợ phân bổ API Key chuyên biệt cho từng Agent nếu có.
        """
        actual_provider, client, model_name, is_dedicated = self._resolve_agent_client(agent_role, preferred_provider)

        if actual_provider == "gemini":
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
                    model=model_name,
                    contents=contents,
                    config=config
                )
                for chunk in response:
                    if chunk.text:
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
                    temperature=temperature,
                    agent_role=agent_role
                )
                tokens = re.split(r'(\s+)', res_text)
                for token in tokens:
                    if token:
                        yield token
                        if typing_delay > 0:
                            time.sleep(typing_delay)
        else:
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
                    model=model_name,
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
                    temperature=temperature,
                    agent_role=agent_role
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
        json_output: bool,
        client: Optional[Any] = None,
        model_name: Optional[str] = None
    ) -> str:
        from utils.logger import log_api_call, log_api_success, log_error
        import time

        gemini_client = client or self._get_gemini_client()
        active_model = model_name or self.gemini_model
        from google.genai import types

        config_args = {"temperature": temperature}
        if system_instruction:
            config_args["system_instruction"] = system_instruction
        if json_output:
            config_args["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_args)

        contents = []
        if image is not None:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            contents.append(image)
        contents.append(prompt)

        log_api_call("Gemini", active_model, has_image=(image is not None), prompt_len=len(prompt))
        t0 = time.time()
        try:
            response = gemini_client.models.generate_content(
                model=active_model,
                contents=contents,
                config=config
            )
            res_text = response.text or ""
            dur = time.time() - t0
            log_api_success("Gemini", active_model, dur, len(res_text))
            return res_text
        except Exception as e:
            # Tự động Fallback sang OpenAI/xKiro nếu Gemini gặp sự cố (quá tải 503/429)
            if self.openai_api_key:
                from utils.logger import log_warning
                log_warning(f"Gemini API gặp lỗi ({type(e).__name__}), tự động kích hoạt OpenAI/xKiro Fallback...")
                try:
                    return self._call_openai(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        image=image,
                        temperature=temperature,
                        json_output=json_output
                    )
                except Exception:
                    pass

            log_error(
                caller_name="LLMManager._call_gemini",
                error=e,
                details=f"Model: {active_model} | Has Image: {image is not None} | JSON Mode: {json_output}"
            )
            raise e

    def _call_openai(
        self,
        prompt: str,
        system_instruction: Optional[str],
        image: Optional[Image.Image],
        temperature: float,
        json_output: bool,
        client: Optional[Any] = None,
        model_name: Optional[str] = None
    ) -> str:
        from utils.logger import log_api_call, log_api_success, log_error
        import time

        openai_client = client or self._get_openai_client()
        active_model = model_name or self.openai_model

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
            "model": active_model,
            "messages": messages,
            "temperature": temperature
        }
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}

        log_api_call("OpenAI", active_model, has_image=(image is not None), prompt_len=len(prompt))
        t0 = time.time()
        try:
            response = openai_client.chat.completions.create(**kwargs)
            res_text = response.choices[0].message.content or ""
            dur = time.time() - t0
            log_api_success("OpenAI", active_model, dur, len(res_text))
            return res_text
        except Exception as e:
            log_error(
                caller_name="LLMManager._call_openai",
                error=e,
                details=f"Model: {active_model} | Has Image: {image is not None} | JSON Mode: {json_output}"
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
