from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from core.config import AppConfig
from core.evaluation_runtime import EvaluationPolicy, PacedLLMManager
from core.gateway import LLMManager
from core.trace_content import redact_text
from tests.test_evaluation_runtime import gate


class ProviderError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("private synthetic provider detail")


def test_new_credential_format_is_redacted_without_environment_lookup():
    token = "AQ." + "synthetic0123456789" * 2
    assert token not in redact_text("credential " + token, secrets=[])


def manager(monkeypatch, outcomes):
    policy = EvaluationPolicy(fallback_api_key_env="GEMINI_FALLBACK_API_KEY")
    paced = gate(policy)
    instance = PacedLLMManager(
        gate=paced,
        config=AppConfig(),
        credentials={
            "GEMINI_API_KEY": "synthetic-primary",
            "GEMINI_FALLBACK_API_KEY": "synthetic-backup",
        },
    )
    monkeypatch.setattr(
        LLMManager, "_client", lambda self, provider, model, key: SimpleNamespace(marker=key)
    )
    seen = []

    def call(self, provider, client, *args, **kwargs):
        seen.append(client.marker)
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result, None, "STOP"

    monkeypatch.setattr(LLMManager, "_provider_call", call)
    return instance, paced, seen


def test_503_waits_then_uses_backup_and_keeps_it_across_roles(monkeypatch):
    instance, paced, seen = manager(monkeypatch, [ProviderError(503), "ok", "next"])
    response, metadata = instance.call_llm("synthetic", agent_role="visual")
    assert response == "ok" and metadata["credential_fallback_used"]
    assert seen == ["synthetic-primary", "synthetic-backup"]
    assert paced.request_start_times == [1000, 1060]
    clone = instance.for_run(benchmark=True)
    clone.call_llm("another synthetic", agent_role="judge")
    assert seen[-1] == "synthetic-backup" and paced.provider_calls == 3
    assert "synthetic-backup" not in str(paced.snapshot())
    assert "private synthetic provider detail" not in str(paced.snapshot())


def test_429_never_switches_key(monkeypatch):
    instance, paced, seen = manager(monkeypatch, [ProviderError(429)])
    with pytest.raises(RuntimeError):
        instance.call_llm("synthetic", agent_role="visual")
    assert seen == ["synthetic-primary"]
    assert paced.stop_reason == "provider_429" and paced.credential_slot == "primary"


def test_503_on_both_keys_pauses_without_more_requests(monkeypatch):
    instance, paced, seen = manager(monkeypatch, [ProviderError(503), ProviderError(503)])
    with pytest.raises(RuntimeError):
        instance.call_llm("synthetic", agent_role="visual")
    assert paced.stop_reason == "provider_503" and len(seen) == 2
    with pytest.raises(RuntimeError):
        instance.call_llm("do not send", agent_role="judge")
    assert len(seen) == 2


def test_concurrent_graph_calls_cannot_overtake_503_fallback(monkeypatch):
    instance, paced, seen = manager(monkeypatch, [ProviderError(503), "ok", "next"])
    entered, release = Event(), Event()
    original = LLMManager._provider_call

    def call(self, provider, client, *args, **kwargs):
        if client.marker == "synthetic-primary":
            entered.set()
            assert release.wait(timeout=5)
        return original(self, provider, client, *args, **kwargs)

    monkeypatch.setattr(LLMManager, "_provider_call", call)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(instance.call_llm, "first", agent_role="visual")
        assert entered.wait(timeout=5)
        second = executor.submit(instance.call_llm, "second", agent_role="judge")
        release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert seen == ["synthetic-primary", "synthetic-backup", "synthetic-backup"]
    assert paced.request_start_times == [1000, 1060, 1090]
