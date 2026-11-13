import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings
from api.telemetry import persist_attempt
from core.config import AppConfig, BudgetConfig, RoleConfig
from core.gateway import BudgetExceeded, LLMManager
from core.model_errors import BlockedModelResponse, EmptyModelResponse, TruncatedModelResponse
from tests.test_api import enqueue, identity, upload


def response(text, finish="STOP", block=None):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=finish)],
        usage_metadata=SimpleNamespace(
            model_dump=lambda **k: {
                "prompt_token_count": 10,
                "candidates_token_count": 5,
                "thoughts_token_count": 20,
                "total_token_count": 35,
            }
        ),
        prompt_feedback=SimpleNamespace(block_reason=block),
    )


def manager_with_responses(monkeypatch, responses, config=None):
    captured = []
    iterator = iter(responses)

    def generate(**kwargs):
        captured.append(kwargs["config"])
        return next(iterator)

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    manager = LLMManager(config=config or AppConfig(), credentials={})
    monkeypatch.setattr(manager, "_client", lambda *a: client)
    return manager, captured


@pytest.mark.parametrize("text", ["", "truncated"])
def test_max_tokens_recovers_once_and_preserves_both_attempts(monkeypatch, text):
    manager, captured = manager_with_responses(
        monkeypatch, [response(text, "MAX_TOKENS"), response("complete")]
    )
    answer, meta = manager.call_llm("q", agent_role="visual")
    assert answer == "complete" and len(captured) == 2
    assert [c.max_output_tokens for c in captured] == [2048, 4096]
    assert manager.calls[0]["error_type"] == "TruncatedModelResponse"
    assert manager.calls[0]["response_has_text"] == bool(text)
    assert manager.calls[0]["usage"]["total_token_count"] == 35
    assert meta["attempts"][0]["finish_reason"] == "MAX_TOKENS"


def test_repeat_truncation_is_bounded_and_does_not_return_partial(monkeypatch):
    manager, captured = manager_with_responses(
        monkeypatch, [response("part", "MAX_TOKENS"), response("part2", "MAX_TOKENS")]
    )
    with pytest.raises(TruncatedModelResponse):
        manager.call_llm("q", agent_role="visual")
    assert len(captured) == 2


def test_unspecified_block_reason_is_not_a_safety_block(monkeypatch):
    manager, captured = manager_with_responses(
        monkeypatch, [response("complete", block="BLOCKED_REASON_UNSPECIFIED")]
    )
    assert manager.call_llm("q", agent_role="visual")[0] == "complete"


@pytest.mark.parametrize(
    "payload,exception",
    [
        (response("", "STOP"), EmptyModelResponse),
        (response("", "SAFETY"), BlockedModelResponse),
        (response("", None, "SAFETY"), BlockedModelResponse),
    ],
)
def test_empty_or_blocked_response_is_not_automatically_retried(monkeypatch, payload, exception):
    manager, captured = manager_with_responses(monkeypatch, [payload])
    with pytest.raises(exception):
        manager.call_llm("q", agent_role="visual")
    assert len(captured) == 1
    assert manager.calls[0]["usage"]["total_token_count"] == 35
    assert not manager.calls[0]["response_has_text"]


def test_truncation_recovery_respects_global_call_budget(monkeypatch):
    manager, captured = manager_with_responses(
        monkeypatch,
        [response("part", "MAX_TOKENS")],
        AppConfig(budget=BudgetConfig(max_llm_calls=1)),
    )
    with pytest.raises(BudgetExceeded):
        manager.call_llm("q", agent_role="visual")
    assert len(captured) == 1


def test_truncation_does_not_start_a_new_request_after_deadline(monkeypatch):
    manager = LLMManager(config=AppConfig(), credentials={})
    attempts = []

    def generate(**kwargs):
        attempts.append(1)
        manager._started = time.monotonic() - manager.config.budget.deadline_seconds - 1
        return response("partial", "MAX_TOKENS")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    monkeypatch.setattr(manager, "_client", lambda *args: client)
    with pytest.raises(BudgetExceeded):
        manager.call_llm("q", agent_role="visual")
    assert len(attempts) == 1
    assert manager.calls[0]["finish_reason"] == "MAX_TOKENS"


def test_per_role_limit_ceiling_and_thinking_are_configurable(monkeypatch):
    roles = dict(AppConfig().roles)
    roles["visual"] = RoleConfig(max_output_tokens=4096, thinking_level="low")
    manager, captured = manager_with_responses(
        monkeypatch, [response("part", "MAX_TOKENS"), response("answer")], AppConfig(roles=roles)
    )
    manager.call_llm("q", agent_role="visual")
    assert [c.max_output_tokens for c in captured] == [4096, 8192]
    assert captured[0].thinking_config.thinking_level.value.lower() == "low"


def test_sdk_text_extraction_error_preserves_finish_reason_and_usage(monkeypatch):
    class NonTextResponse:
        candidates = [SimpleNamespace(finish_reason="MAX_TOKENS")]
        prompt_feedback = None
        usage_metadata = SimpleNamespace(model_dump=lambda **k: {"total_token_count": 2048})

        @property
        def text(self):
            raise ValueError("no text part")

    manager, captured = manager_with_responses(
        monkeypatch, [NonTextResponse()], AppConfig(budget=BudgetConfig(truncation_retries=0))
    )
    with pytest.raises(TruncatedModelResponse):
        manager.call_llm("q", agent_role="visual")
    assert manager.calls[0]["finish_reason"] == "MAX_TOKENS"
    assert manager.calls[0]["usage"]["total_token_count"] == 2048


def test_error_diagnostics_and_usage_survive_in_api_database(tmp_path, monkeypatch, photo):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'api.sqlite').as_posix()}",
        data_dir=tmp_path / "data",
        model_mode="demo",
        embedded_worker=False,
    )
    with TestClient(create_app(settings)) as client:
        auth = identity(client)
        rid = enqueue(client, auth, upload(client, auth, photo))
        manager, captured = manager_with_responses(
            monkeypatch,
            [response("", "MAX_TOKENS")],
            AppConfig(budget=BudgetConfig(truncation_retries=0)),
        )
        manager.attempt_observer = lambda record: persist_attempt(
            client.app.state.runtime.db, rid, record
        )
        with pytest.raises(TruncatedModelResponse):
            manager.call_llm("q", agent_role="visual")
        call = client.get(f"/api/v1/runs/{rid}/metrics", headers=auth).json()["calls"][0]
        assert call["finish_reason"] == "MAX_TOKENS"
        assert call["error_code"] == "output_token_limit"
        assert call["max_output_tokens"] == 2048
        assert call["usage"]["total_tokens"] == 35
        assert call["status"] == "error"


def test_provider_status_is_recorded_without_raw_error_message(monkeypatch, caplog):
    class ProviderFailure(Exception):
        code = 400

    manager = LLMManager(config=AppConfig(), credentials={})
    monkeypatch.setattr(manager, "_client", lambda *args: object())

    def fail(*args):
        raise ProviderFailure("PRIVATE_RESPONSE_BODY_WITH_CREDENTIAL")

    monkeypatch.setattr(manager, "_provider_call", fail)
    with pytest.raises(ProviderFailure):
        manager.call_llm("query", agent_role="visual")
    assert manager.calls[0]["provider_status_code"] == 400
    assert manager.calls[0]["error_code"] == "provider_request_failed"
    assert "PRIVATE_RESPONSE_BODY_WITH_CREDENTIAL" not in caplog.text
