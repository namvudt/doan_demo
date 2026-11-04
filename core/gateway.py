"""Explicit provider routing and bounded calls; no credentials in run metadata."""

import base64
import json
import os
import re
import threading
import time
from io import BytesIO

from dotenv import load_dotenv

from core.config import AppConfig, load_config
from core.observability import token_usage, trace_operation


class BudgetExceeded(RuntimeError):
    pass


class StreamInterrupted(RuntimeError):
    pass


class LLMManager:
    def __init__(self, gemini_api_key=None, openai_api_key=None, *, config=None, credentials=None):
        if credentials is None:
            load_dotenv()
        self.config: AppConfig = config or load_config()
        self._credentials = dict(os.environ if credentials is None else credentials)
        for name, key in (("GEMINI_API_KEY", gemini_api_key), ("OPENAI_API_KEY", openai_api_key)):
            if key is not None:
                self._credentials[name] = key
        self._clients = {}
        self._lock = threading.RLock()
        self._started = time.monotonic()
        self.calls = []
        self._attempt_count = 0
        self.cancel_check = None

    def for_run(self, *, benchmark=False):
        config = self.config.model_copy(deep=True)
        if benchmark:
            config = config.model_copy(update={"fallback_providers": []})
        return LLMManager(config=config, credentials=self._credentials)

    def _binding(self, role, preferred_provider):
        binding = self.config.roles.get(role)
        provider = binding.provider if binding else preferred_provider
        pc = self.config.providers[provider]
        dedicated_env = binding.api_key_env if binding else None
        legacy_env = f"{role.upper()}_API_KEY" if role else ""
        key = self._credentials.get(dedicated_env or legacy_env, "").strip()
        return (
            provider,
            (binding.model if binding else None) or pc.model,
            key or self._credentials.get(pc.api_key_env, "").strip(),
            bool(key),
        )

    def get_status(self):
        roles = {}
        for role in self.config.roles:
            provider, model, key, dedicated = self._binding(role, "gemini")
            pc = self.config.providers[provider]
            endpoint = provider != "gpu" or bool(self._credentials.get(pc.base_url_env or ""))
            roles[role] = {
                "provider": provider,
                "model": model,
                "configured": bool(key) and endpoint,
                "dedicated": dedicated,
            }
        missing = [
            r
            for r, value in roles.items()
            if not value["configured"] and (r != "generation" or self.config.enable_generation)
        ]
        return {
            "ready": not missing,
            "missing_roles": missing,
            "roles": roles,
            "description": "Đã cấu hình không đồng nghĩa đã kiểm tra kết nối.",
        }

    def _client(self, provider, model, key):
        pc = self.config.providers[provider]
        base_url = self._credentials.get(pc.base_url_env or "", "").strip()
        if not key or (provider == "gpu" and not base_url):
            raise ValueError(f"Thiếu cấu hình credential/endpoint cho {provider}.")
        cache_key = (provider, model, key, base_url)
        with self._lock:
            if cache_key not in self._clients:
                if provider == "gemini":
                    from google import genai
                    from google.genai import types

                    client = genai.Client(
                        api_key=key,
                        http_options=types.HttpOptions(
                            timeout=int(self.config.budget.request_timeout_seconds * 1000),
                            retry_options=types.HttpRetryOptions(attempts=1),
                        ),
                    )
                else:
                    from openai import OpenAI

                    client = OpenAI(
                        api_key=key,
                        base_url=base_url or None,
                        max_retries=0,
                        timeout=self.config.budget.request_timeout_seconds,
                    )
                self._clients[cache_key] = client
            return self._clients[cache_key]

    def close(self):
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()

    def remaining_seconds(self):
        return self.config.budget.deadline_seconds - (time.monotonic() - self._started)

    def _admit(self):
        if self.cancel_check:
            self.cancel_check()
        with self._lock:
            if self.remaining_seconds() <= 0:
                raise BudgetExceeded("Đã hết thời gian của lượt xử lý.")
            if self._attempt_count >= self.config.budget.max_llm_calls:
                raise BudgetExceeded("Đã hết ngân sách gọi model.")
            self._attempt_count += 1
            return self._attempt_count

    @staticmethod
    def _retryable(exc):
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        return code in (429, 500, 502, 503, 504) or isinstance(exc, (TimeoutError, ConnectionError))

    def _record(self, record):
        with self._lock:
            self.calls.append(record)

    def _provider_call(
        self,
        provider,
        client,
        model,
        prompt,
        system_instruction,
        image,
        temperature,
        json_output,
        response_schema,
    ):
        timeout = min(self.config.budget.request_timeout_seconds, self.remaining_seconds())
        if provider == "gemini":
            from google.genai import types

            kwargs = {
                "temperature": temperature,
                "system_instruction": system_instruction,
                "max_output_tokens": self.config.budget.max_output_tokens,
                "http_options": types.HttpOptions(timeout=max(1, int(timeout * 1000))),
            }
            if json_output:
                kwargs["response_mime_type"] = "application/json"
            if response_schema:
                kwargs["response_json_schema"] = response_schema.model_json_schema()
            response = client.models.generate_content(
                model=model,
                contents=[image.convert("RGB"), prompt] if image else [prompt],
                config=types.GenerateContentConfig(**kwargs),
            )
            text = response.text or ""
            usage = (
                response.usage_metadata.model_dump(mode="json") if response.usage_metadata else None
            )
            finish = str(response.candidates[0].finish_reason) if response.candidates else None
        else:
            content = prompt
            if image:
                buffer = BytesIO()
                image.convert("RGB").save(buffer, format="PNG")
                encoded = base64.b64encode(buffer.getvalue()).decode()
                content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ]
            messages = [{"role": "user", "content": content}]
            if system_instruction:
                messages.insert(0, {"role": "system", "content": system_instruction})
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": self.config.budget.max_output_tokens,
                "timeout": timeout,
            }
            if json_output:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            text = response.choices[0].message.content or ""
            usage = response.usage.model_dump(mode="json") if response.usage else None
            finish = response.choices[0].finish_reason
        if not text.strip():
            raise ValueError("Model không trả nội dung.")
        if finish and finish not in {"STOP", "FinishReason.STOP", "stop"}:
            raise ValueError(f"Model kết thúc chưa hoàn chỉnh: {finish}")
        return text, usage, finish

    def call_llm(
        self,
        prompt,
        system_instruction=None,
        image=None,
        preferred_provider="gemini",
        temperature=0.3,
        json_output=False,
        agent_role=None,
        response_schema=None,
    ):
        requested, requested_model, requested_key, dedicated = self._binding(
            agent_role, preferred_provider
        )
        providers = [requested, *[p for p in self.config.fallback_providers if p != requested]]
        attempts = []
        last_error = None
        for provider in providers:
            pc = self.config.providers[provider]
            if image is not None and not pc.supports_images:
                if provider != requested:
                    continue
                raise ValueError(f"Provider {provider} không hỗ trợ ảnh theo cấu hình.")
            if json_output and not pc.supports_json:
                if provider != requested:
                    continue
                raise ValueError(f"Provider {provider} không hỗ trợ JSON theo cấu hình.")
            model = requested_model if provider == requested else pc.model
            key = (
                requested_key
                if provider == requested
                else self._credentials.get(pc.api_key_env, "")
            )
            for retry in range(self.config.budget.transient_retries + 1):
                attempt = self._admit()
                start = time.monotonic()
                record = {
                    "attempt": attempt,
                    "agent_role": agent_role or "general",
                    "actual_provider": provider,
                    "model_used": model,
                    "usage": None,
                }
                try:
                    with trace_operation(
                        f"model.{agent_role or 'general'}",
                        "llm",
                        metadata={
                            "agent_role": agent_role or "general",
                            "actual_provider": provider,
                            "ls_provider": "google_genai" if provider == "gemini" else "openai",
                            "ls_model_name": model,
                            "ls_model_type": "chat",
                            "attempt": attempt,
                            "retry": retry,
                            "fallback_used": provider != requested,
                        },
                    ) as span:
                        client = self._client(provider, model, key)
                        text, usage, finish = self._provider_call(
                            provider,
                            client,
                            model,
                            prompt,
                            system_instruction,
                            image,
                            temperature,
                            json_output,
                            response_schema,
                        )
                        span.outputs = {
                            "status": "success",
                            "usage_metadata": token_usage(usage, provider),
                        }
                    record.update(
                        status="success",
                        usage=usage,
                        finish_reason=finish,
                        duration=time.monotonic() - start,
                    )
                    self._record(record)
                    return text, {
                        **record,
                        "requested_provider": requested,
                        "dedicated_key": dedicated and provider == requested,
                        "fallback_used": provider != requested,
                        "attempts": [*attempts, record],
                    }
                except Exception as exc:
                    # Exception text can contain request data or credentials.
                    record.update(
                        status="error",
                        error_type=type(exc).__name__,
                        duration=time.monotonic() - start,
                    )
                    self._record(record)
                    attempts.append(record)
                    last_error = exc
                    if not self._retryable(exc):
                        raise
                    if retry < self.config.budget.transient_retries:
                        time.sleep(min(0.25 * 2**retry, max(0, self.remaining_seconds())))
        raise RuntimeError("Các provider tạm thời không khả dụng.") from last_error

    def stream_llm(
        self,
        prompt,
        system_instruction=None,
        image=None,
        preferred_provider="gemini",
        temperature=0.3,
        typing_delay=0,
        agent_role=None,
    ):
        """Legacy draft stream; interrupted output is never concatenated with a retry."""
        provider, model, key, _ = self._binding(agent_role, preferred_provider)
        if image is not None and not self.config.providers[provider].supports_images:
            raise ValueError(f"Provider {provider} không hỗ trợ ảnh theo cấu hình.")
        if provider != "gemini":
            text, _ = self.call_llm(
                prompt,
                system_instruction,
                image,
                preferred_provider,
                temperature,
                agent_role=agent_role,
            )
            yield text
            return
        attempt = self._admit()
        emitted = False
        start = time.monotonic()
        record = {
            "attempt": attempt,
            "agent_role": agent_role or "general",
            "actual_provider": provider,
            "model_used": model,
            "usage": None,
        }
        with trace_operation(
            f"model.{agent_role or 'general'}.stream",
            "llm",
            metadata={
                "agent_role": agent_role or "general",
                "actual_provider": provider,
                "ls_provider": "google_genai",
                "ls_model_name": model,
                "ls_model_type": "chat",
                "attempt": attempt,
            },
        ) as span:
            try:
                client = self._client(provider, model, key)
                from google.genai import types

                response = client.models.generate_content_stream(
                    model=model,
                    contents=[image.convert("RGB"), prompt] if image else [prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=temperature,
                        max_output_tokens=self.config.budget.max_output_tokens,
                        http_options=types.HttpOptions(
                            timeout=max(
                                1,
                                int(
                                    min(
                                        self.remaining_seconds(),
                                        self.config.budget.request_timeout_seconds,
                                    )
                                    * 1000
                                ),
                            )
                        ),
                    ),
                )
                for chunk in response:
                    if chunk.text:
                        emitted = True
                        yield chunk.text
                    if getattr(chunk, "usage_metadata", None):
                        record["usage"] = chunk.usage_metadata.model_dump(mode="json")
                    candidates = getattr(chunk, "candidates", [])
                    if candidates and candidates[0].finish_reason:
                        record["finish_reason"] = str(candidates[0].finish_reason)
                if not emitted:
                    raise ValueError("Stream không trả nội dung.")
                if record.get("finish_reason") not in {None, "STOP", "FinishReason.STOP", "stop"}:
                    raise ValueError("Stream kết thúc chưa hoàn chỉnh.")
                record["status"] = "success"
            except Exception as exc:
                record.update(status="error", error_type=type(exc).__name__)
                if emitted:
                    raise StreamInterrupted(
                        "Stream gián đoạn; bỏ bản nháp trước khi thử lại."
                    ) from exc
                raise
            finally:
                record["duration"] = time.monotonic() - start
                record.setdefault("status", "cancelled")
                self._record(record)
                span.outputs = {
                    "status": record["status"],
                    "usage_metadata": token_usage(record["usage"], provider),
                }


def safe_extract_json(text: str) -> dict:
    """Decode one JSON object; malformed/scalar outputs are explicit failures."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Phản hồi JSON trống.")
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        stripped = match.group(1)
    result = json.loads(stripped)
    if not isinstance(result, dict):
        raise ValueError("Phản hồi phải là một JSON object.")
    return result
