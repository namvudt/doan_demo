from types import SimpleNamespace

import pytest
import requests

from core.config import ROLES, AppConfig, BudgetConfig
from core.gateway import BudgetExceeded, LLMManager, StreamInterrupted
from core.search import HeritageSearchEngine


def test_dedicated_keys_work_without_global_and_prefix_does_not_select_provider():
    credentials = {f"{role.upper()}_API_KEY": "sk-dummy-gemini-role-key" for role in ROLES}
    status = LLMManager(config=AppConfig(), credentials=credentials).get_status()
    assert status["ready"]
    assert all(binding["provider"] == "gemini" for binding in status["roles"].values())


def test_fallback_reports_actual_provider_and_both_attempts(monkeypatch):
    config = AppConfig(fallback_providers=["openai"], budget=BudgetConfig(transient_retries=0))
    manager = LLMManager(
        config=config, credentials={"GEMINI_API_KEY": "dummy", "OPENAI_API_KEY": "dummy"}
    )
    monkeypatch.setattr(manager, "_client", lambda *args: object())

    def call(provider, *args):
        if provider == "gemini":
            raise TimeoutError()
        return "fallback", {"total_tokens": 12}, "stop"

    monkeypatch.setattr(manager, "_provider_call", call)
    text, meta = manager.call_llm("question")
    assert text == "fallback"
    assert meta["actual_provider"] == "openai"
    assert meta["model_used"] == "gpt-4o-mini"
    assert meta["fallback_used"]
    assert len(meta["attempts"]) == 2
    assert manager.calls[0]["usage"] is None


def test_nonretryable_error_not_fallback(monkeypatch):
    manager = LLMManager(config=AppConfig(fallback_providers=["openai"]), credentials={})
    monkeypatch.setattr(manager, "_client", lambda *args: object())

    def fail(*args):
        raise ValueError("bad request")

    monkeypatch.setattr(manager, "_provider_call", fail)
    with pytest.raises(ValueError):
        manager.call_llm("q")
    assert len(manager.calls) == 1


def test_all_retries_count_toward_budget(monkeypatch):
    manager = LLMManager(config=AppConfig(budget=BudgetConfig(max_llm_calls=1)), credentials={})
    monkeypatch.setattr(manager, "_client", lambda *args: object())
    monkeypatch.setattr(
        manager, "_provider_call", lambda *args: (_ for _ in ()).throw(TimeoutError())
    )
    with pytest.raises(BudgetExceeded):
        manager.call_llm("q")
    assert len(manager.calls) == 1


def test_stream_partial_failure_never_restarts(monkeypatch):
    def stream(**kwargs):
        yield SimpleNamespace(text="ANSWER ", usage_metadata=None)
        raise TimeoutError()

    client = SimpleNamespace(models=SimpleNamespace(generate_content_stream=stream))
    manager = LLMManager(config=AppConfig(), credentials={})
    monkeypatch.setattr(manager, "_client", lambda *args: client)
    generator = manager.stream_llm("q")
    assert next(generator) == "ANSWER "
    with pytest.raises(StreamInterrupted):
        next(generator)
    assert len(manager.calls) == 1
    assert manager.calls[0]["status"] == "error"


def test_benchmark_disables_cross_provider_fallback():
    manager = LLMManager(config=AppConfig(fallback_providers=["openai"]), credentials={})
    assert manager.for_run(benchmark=True).config.fallback_providers == []
    assert manager.config.fallback_providers == ["openai"]


@pytest.mark.parametrize(
    "exception,status", [(requests.Timeout(), "timeout"), (requests.ConnectionError(), "error")]
)
def test_search_failure_is_explicit_navigation_is_not_evidence(monkeypatch, exception, status):
    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr("core.search.requests.get", fail)
    result = HeritageSearchEngine().search_heritage("Test site", "q")
    assert result["status"] == status
    assert result["error"]
    assert result["sources"] == []
    assert result["context_text"] == ""
    assert result["navigation_links"][0]["type"] == "maps"


def test_wikipedia_records_have_provenance(monkeypatch):
    responses = iter(
        [
            {"query": {"search": [{"title": "Site"}]}},
            {
                "query": {
                    "pages": {
                        "1": {
                            "title": "Site",
                            "extract": "History",
                            "lastrevid": 42,
                            "fullurl": "https://vi.wikipedia.org/wiki/Site",
                        }
                    }
                }
            },
        ]
    )

    def get(*args, **kwargs):
        value = next(responses)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: value)

    monkeypatch.setattr("core.search.requests.get", get)
    result = HeritageSearchEngine().search_heritage("Site", "q")
    source = result["sources"][0]
    assert source["source_id"].startswith("wiki_")
    assert source["revision_id"] == "42"
    assert source["retrieved_at"]


def test_search_does_not_start_after_deadline(monkeypatch):
    engine = HeritageSearchEngine(remaining_seconds=lambda: 0)
    result = engine.search_heritage("Site", "q")
    assert result["status"] == "timeout"
    assert not result["sources"]
