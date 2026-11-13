"""Explicit provider routing and bounded calls; no credentials in run metadata."""

import base64
import json
import logging
import os
import re
import threading
import time
from io import BytesIO

from dotenv import load_dotenv

from core.config import AppConfig, load_config
from core.model_errors import (
    ModelResponseError,
    TruncatedModelResponse,
    enum_name,
    provider_error_diagnostics,
    validate_response,
)
from core.observability import token_usage, trace_operation
from core.runtime_logging import log_event
from core.trace_content import image_info


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
        self.attempt_observer = None

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

    def _record(self, record, *, error=None):
        with self._lock:
            self.calls.append(record)
        self._notify_attempt(record, required=False)
        log_event(
            "model." + record["status"],
            level=logging.ERROR if record["status"] == "error" else logging.INFO,
            error=error,
            **{k: v for k, v in record.items() if k != "usage"},
            duration_ms=round(record.get("duration", 0) * 1000, 3),
            **token_usage(record.get("usage"), record.get("actual_provider")),
        )

    def _notify_attempt(self, record, *, required):
        if self.attempt_observer:
            try:
                self.attempt_observer(dict(record))
            except Exception as exc:
                log_event(
                    "model.persistence_failed",
                    level=logging.ERROR,
                    error=exc,
                    attempt=record["attempt"],
                )
                if required:
                    # Refuse a paid request if its start cannot be recorded durably.
                    raise

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
        options=None,
    ):
        options = options or {}
        output_limit = options.get("max_output_tokens", self.config.budget.max_output_tokens)
        timeout = min(self.config.budget.request_timeout_seconds, self.remaining_seconds())
        if provider == "gemini":
            from google.genai import types

            kwargs = {
                "temperature": temperature,
                "system_instruction": system_instruction,
                "max_output_tokens": output_limit,
                "http_options": types.HttpOptions(timeout=max(1, int(timeout * 1000))),
            }
            if json_output:
                kwargs["response_mime_type"] = "application/json"
            if response_schema:
                kwargs["response_json_schema"] = response_schema.model_json_schema()
            if options.get("thinking_level"):
                kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_level=options["thinking_level"]
                )
            response = client.models.generate_content(
                model=model,
                contents=[image.convert("RGB"), prompt] if image else [prompt],
                config=types.GenerateContentConfig(**kwargs),
            )
            usage = (
                response.usage_metadata.model_dump(mode="json") if response.usage_metadata else None
            )
            finish = (
                enum_name(response.candidates[0].finish_reason) if response.candidates else None
            )
            block = enum_name(
                getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
            )
            try:
                text = response.text or ""
            except ValueError:
                text = ""  # Preserve finish/usage even when the SDK cannot extract a text part.
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
                "max_tokens": output_limit,
                "timeout": timeout,
            }
            if json_output:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            usage = response.usage.model_dump(mode="json") if response.usage else None
            text = response.choices[0].message.content or "" if response.choices else ""
            finish = response.choices[0].finish_reason if response.choices else None
            block = None
        validate_response(text, usage, finish, block)
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
        binding = self.config.roles.get(agent_role)
        initial_limit = (
            binding.max_output_tokens if binding else None
        ) or self.config.budget.max_output_tokens
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
            output_limit = initial_limit
            transient_count, truncation_count = 0, 0
            for retry in range(
                self.config.budget.transient_retries + self.config.budget.truncation_retries + 1
            ):
                attempt = self._admit()
                start = time.monotonic()
                record = {
                    "attempt": attempt,
                    "agent_role": agent_role or "general",
                    "actual_provider": provider,
                    "model_used": model,
                    "usage": None,
                    "retry": retry,
                    "fallback_used": provider != requested,
                    "started_at": time.time(),
                    "status": "running",
                    "max_output_tokens": output_limit,
                }
                self._notify_attempt(record, required=True)
                log_event("model.started", **{k: v for k, v in record.items() if k != "usage"})
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
                            "max_output_tokens": output_limit,
                        },
                        inputs={
                            "prompt": prompt,
                            "system_instruction": system_instruction,
                            "image_info": image_info(image),
                            "max_output_tokens": output_limit,
                        },
                    ) as span:
                        client = self._client(provider, model, key)
                        try:
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
                                {
                                    "max_output_tokens": output_limit,
                                    "thinking_level": binding.thinking_level if binding else None,
                                },
                            )
                        except ModelResponseError as exc:
                            span.metadata.update(exc.diagnostics)
                            span.outputs = {
                                "status": "error",
                                **exc.diagnostics,
                                "response": exc.partial_response,
                                "usage_metadata": token_usage(exc.usage, provider),
                            }
                            raise
                        except Exception as exc:
                            diagnostic = provider_error_diagnostics(exc)
                            span.metadata.update(diagnostic)
                            span.outputs = {
                                "status": "error",
                                "error_type": type(exc).__name__,
                                **diagnostic,
                            }
                            raise
                        span.outputs = {
                            "status": "success",
                            "response": text,
                            "finish_reason": finish,
                            "response_has_text": bool(text.strip()),
                            "usage_metadata": token_usage(usage, provider),
                        }
                    record.update(
                        status="success",
                        usage=usage,
                        finish_reason=finish,
                        response_has_text=bool(text.strip()),
                        duration=time.monotonic() - start,
                        finished_at=time.time(),
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
                    record.update(provider_error_diagnostics(exc))
                    if isinstance(exc, ModelResponseError):
                        record.update(exc.diagnostics, usage=exc.usage)
                    # Exception text can contain request data or credentials.
                    record.update(
                        status="error",
                        error_type=type(exc).__name__,
                        duration=time.monotonic() - start,
                        finished_at=time.time(),
                    )
                    self._record(record, error=exc)
                    attempts.append(record)
                    last_error = exc
                    if isinstance(exc, TruncatedModelResponse):
                        ceiling = max(initial_limit, self.config.budget.max_output_tokens_ceiling)
                        larger = min(ceiling, output_limit * 2)
                        if (
                            truncation_count < self.config.budget.truncation_retries
                            and larger > output_limit
                        ):
                            truncation_count += 1
                            output_limit = larger
                            log_event(
                                "model.output_limit_retry",
                                attempt=attempt,
                                max_output_tokens=larger,
                                agent_role=agent_role,
                            )
                            continue
                        raise
                    if not self._retryable(exc):
                        raise
                    if transient_count < self.config.budget.transient_retries:
                        time.sleep(min(0.25 * 2**transient_count, max(0, self.remaining_seconds())))
                        transient_count += 1
                        continue
                    break
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
        stream_error = None
        pieces = []
        binding = self.config.roles.get(agent_role)
        output_limit = (
            binding.max_output_tokens if binding else None
        ) or self.config.budget.max_output_tokens
        start = time.monotonic()
        record = {
            "attempt": attempt,
            "agent_role": agent_role or "general",
            "actual_provider": provider,
            "model_used": model,
            "usage": None,
            "started_at": time.time(),
            "retry": 0,
            "fallback_used": False,
            "max_output_tokens": output_limit,
        }
        self._notify_attempt({**record, "status": "running"}, required=True)
        log_event("model.started", **{k: v for k, v in record.items() if k != "usage"})
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
            inputs={
                "prompt": prompt,
                "system_instruction": system_instruction,
                "image_info": image_info(image),
                "max_output_tokens": output_limit,
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
                        max_output_tokens=output_limit,
                        thinking_config=types.ThinkingConfig(thinking_level=binding.thinking_level)
                        if binding and binding.thinking_level
                        else None,
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
                    if getattr(chunk, "usage_metadata", None):
                        record["usage"] = chunk.usage_metadata.model_dump(mode="json")
                    candidates = getattr(chunk, "candidates", [])
                    if candidates and candidates[0].finish_reason:
                        record["finish_reason"] = enum_name(candidates[0].finish_reason)
                    if chunk.text:
                        emitted = True
                        pieces.append(chunk.text)
                        yield chunk.text
                validate_response("".join(pieces), record["usage"], record.get("finish_reason"))
                record["status"] = "success"
            except Exception as exc:
                stream_error = exc
                if isinstance(exc, ModelResponseError):
                    record.update(exc.diagnostics)
                record.update(status="error", error_type=type(exc).__name__)
                if emitted:
                    raise StreamInterrupted(
                        "Stream gián đoạn; bỏ bản nháp trước khi thử lại."
                    ) from exc
                raise
            finally:
                record["response_has_text"] = emitted
                record["duration"] = time.monotonic() - start
                record["finished_at"] = time.time()
                record.setdefault("status", "cancelled")
                self._record(record, error=stream_error)
                span.outputs = {
                    "status": record["status"],
                    "response": "".join(pieces),
                    "finish_reason": record.get("finish_reason"),
                    "response_has_text": emitted,
                    "error_code": record.get("error_code"),
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
