"""Evaluation-only pacing shared by every role and run in one batch process."""

import threading
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.gateway import BudgetExceeded, LLMManager


class EvaluationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_spacing_seconds: float = Field(default=30, ge=0, le=600)
    case_spacing_seconds: float = Field(default=60, ge=0, le=3600)
    quota_cooldown_seconds: float = Field(default=90, ge=1, le=86400)
    max_cases: int = Field(default=3, ge=1, le=100)
    max_provider_calls: int = Field(default=24, ge=1, le=1000)
    fallback_api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    high_demand_backoff_seconds: float = Field(default=60, ge=1, le=3600)
    max_consecutive_failures: int = Field(default=3, ge=1, le=20)


class EvaluationPaused(RuntimeError):
    """No more provider requests may be sent by this batch."""


def retry_after_seconds(error, now):
    """Read structured retry hints only; never persist raw provider exception text."""
    delays = []
    headers = getattr(getattr(error, "response", None), "headers", {}) or {}
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value:
        try:
            delays.append(float(value))
        except (ValueError, TypeError):
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                delays.append(parsed.timestamp() - now)
            except (ValueError, TypeError, OverflowError):
                pass
    payload = getattr(error, "response_json", None)
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        details = payload["error"].get("details", [])
        for detail in details if isinstance(details, list) else []:
            if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
                value = detail.get("retryDelay")
                try:
                    if isinstance(value, str) and value.endswith("s"):
                        delays.append(float(value[:-1]))
                    elif isinstance(value, dict):
                        delays.append(float(value.get("seconds", 0)))
                except (ValueError, TypeError):
                    pass
    return max([0, *[delay for delay in delays if 0 <= delay < float("inf")]])


class EvaluationGate:
    def __init__(self, policy, *, monotonic=time.monotonic, wall=time.time, sleep=time.sleep):
        self.policy = policy
        self.monotonic, self.wall, self.sleep = monotonic, wall, sleep
        self._lock = threading.RLock()
        self._next_start = 0.0
        self.provider_calls = 0
        self.stop_reason = None
        self.retry_not_before = None
        self.request_start_times = []
        self.on_change = None
        self.credential_slot = "primary"
        self.provider_events = []
        self.failure_streak = 0

    def snapshot(self):
        with self._lock:
            return {
                "provider_calls": self.provider_calls,
                "stop_reason": self.stop_reason,
                "retry_not_before": self.retry_not_before,
                "request_start_times": list(self.request_start_times),
                "credential_slot": self.credential_slot,
                "provider_events": [dict(event) for event in self.provider_events],
                "failure_streak": self.failure_streak,
            }

    def defer(self, seconds):
        with self._lock:
            self._next_start = max(self._next_start, self.monotonic() + seconds)

    def request(
        self, callback, *, remaining_seconds, cancel_check=None, call_id=None, slot="primary"
    ):
        # Hold the lock through the request: graph branches cannot overlap generation.
        with self._lock:
            if self.stop_reason:
                raise EvaluationPaused("Evaluation batch is paused")
            if self.provider_calls >= self.policy.max_provider_calls:
                self.stop_reason = "provider_call_budget"
                raise EvaluationPaused("Evaluation provider-call budget exhausted")
            while self.monotonic() < self._next_start:
                wait = self._next_start - self.monotonic()
                if remaining_seconds() <= wait:
                    raise BudgetExceeded("Evaluation pacing exceeds remaining run deadline")
                if cancel_check:
                    cancel_check()
                self.sleep(min(wait, 1.0))
            if cancel_check:
                cancel_check()
            if remaining_seconds() <= 0:
                raise BudgetExceeded("Evaluation run deadline exhausted")
            self.provider_calls += 1
            self._next_start = self.monotonic() + self.policy.request_spacing_seconds
            self.request_start_times.append(self.wall())
            event = {
                "request": self.provider_calls,
                "call_id": call_id,
                "credential_slot": slot,
                "started_at": self.wall(),
                "status": "running",
            }
            self.provider_events.append(event)
            if self.on_change:
                self.on_change()
            try:
                result = callback()
                event.update(status="success", finished_at=self.wall())
                if self.on_change:
                    self.on_change()
                return result
            except Exception as error:
                code = getattr(error, "status_code", None) or getattr(error, "code", None)
                event.update(status="error", finished_at=self.wall())
                if isinstance(code, int) and 100 <= code <= 599:
                    event["provider_status_code"] = code
                if str(code) == "429":
                    self.stop_reason = "provider_429"
                    self.retry_not_before = self.wall() + max(
                        self.policy.quota_cooldown_seconds,
                        retry_after_seconds(error, self.wall()),
                    )
                    if self.on_change:
                        self.on_change()
                raise


class PacedLLMManager(LLMManager):
    def __init__(self, *, gate, config, credentials=None):
        if config.parallel_workers < 2:
            raise ValueError("Evaluation streaming requires at least two graph workers")
        config = config.model_copy(
            deep=True,
            update={
                "fallback_providers": [],
                "budget": config.budget.model_copy(update={"transient_retries": 0}),
            },
        )
        super().__init__(config=config, credentials=credentials)
        self.gate = gate
        self._evaluation_local = threading.local()

    def for_run(self, *, benchmark=False):
        config = self.config.model_copy(deep=True)
        return PacedLLMManager(gate=self.gate, config=config, credentials=self._credentials)

    def _binding(self, role, preferred_provider):
        provider, model, key, dedicated = super()._binding(role, preferred_provider)
        backup = self._credentials.get(self.gate.policy.fallback_api_key_env or "", "").strip()
        if provider == "gemini" and self.gate.credential_slot == "fallback" and backup:
            return provider, model, backup, False
        return provider, model, key, dedicated

    def _provider_call(self, *args, **kwargs):
        # Keep credential choice, 503 handling and cooldown atomic across graph threads.
        with self.gate._lock:
            return self._paced_provider_call(*args, **kwargs)

    def _paced_provider_call(self, *args, **kwargs):
        call = super()._provider_call
        provider, _, model = args[:3]
        identifier = str(uuid4())
        self._evaluation_local.call_id = identifier
        backup = self._credentials.get(self.gate.policy.fallback_api_key_env or "", "").strip()

        def invoke(slot):
            params = list(args)
            if slot == "fallback" and provider == "gemini" and backup:
                params[1] = self._client(provider, model, backup)
            return self.gate.request(
                lambda: call(*params, **kwargs),
                remaining_seconds=self.remaining_seconds,
                cancel_check=self.cancel_check,
                call_id=identifier,
                slot=slot,
            )

        slot = self.gate.credential_slot if provider == "gemini" else "primary"
        try:
            return invoke(slot)
        except Exception as error:
            code = getattr(error, "status_code", None) or getattr(error, "code", None)
            if str(code) == "503" and provider == "gemini" and backup and slot == "primary":
                delay = max(
                    self.gate.policy.high_demand_backoff_seconds,
                    retry_after_seconds(error, self.gate.wall()),
                )
                self.gate.credential_slot = "fallback"
                self.gate.defer(delay)
                try:
                    return invoke("fallback")
                except Exception as fallback_error:
                    self._pause_provider_error(fallback_error)
                    raise
            self._pause_provider_error(error)
            raise

    def _pause_provider_error(self, error):
        code = getattr(error, "status_code", None) or getattr(error, "code", None)
        if str(code) == "503":
            self.gate.stop_reason = "provider_503"
            self.gate.retry_not_before = self.gate.wall() + max(
                self.gate.policy.high_demand_backoff_seconds,
                retry_after_seconds(error, self.gate.wall()),
            )
        elif self.gate.credential_slot == "fallback" and str(code) in {"400", "401", "403"}:
            self.gate.stop_reason = "fallback_credential_rejected"
        if self.gate.stop_reason and self.gate.on_change:
            self.gate.on_change()

    def _record(self, record, *, error=None):
        identifier = getattr(self._evaluation_local, "call_id", None)
        events = [dict(e) for e in self.gate.provider_events if e.get("call_id") == identifier]
        record["credential_fallback_used"] = any(e["credential_slot"] == "fallback" for e in events)
        record["credential_attempts"] = events
        return super()._record(record, error=error)
