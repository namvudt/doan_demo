from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from core.config import AppConfig, load_config
from core.gateway import LLMManager
from core.schemas import Criterion, ExecutionPlan


def test_partial_config_merges_defaults_and_rejects_unknown_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("parallel_workers: 1\n", encoding="utf-8")
    assert load_config(path).providers["gemini"].model == "gemini-3.8-flash"
    path.write_text("paralel_workers: 1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


@pytest.mark.parametrize("score", [True, "9.5", float("nan"), 11])
def test_criterion_scores_are_numeric_finite_and_bounded(score):
    with pytest.raises(ValidationError):
        Criterion(passed=True, score=score, critique="test")


def test_declared_capabilities_checked_before_run():
    data = AppConfig().model_dump()
    data["providers"]["gemini"]["supports_images"] = False
    with pytest.raises(ValidationError):
        AppConfig.model_validate(data)


def test_gemini_request_contains_schema_and_finite_sdk_timeout():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text='{"selected_agents": []}',
            usage_metadata=SimpleNamespace(model_dump=lambda **k: {"total_token_count": 10}),
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )

    client = SimpleNamespace(models=SimpleNamespace(generate_content=create))
    manager = LLMManager(config=AppConfig(), credentials={})
    text, usage, finish = manager._provider_call(
        "gemini", client, "test-model", "q", "system", None, 0.1, True, ExecutionPlan
    )
    assert captured["config"].response_json_schema["type"] == "object"
    assert 0 < captured["config"].http_options.timeout <= 30000
    assert captured["config"].max_output_tokens == 2048
    assert text and usage and finish == "STOP"


def test_incomplete_model_response_is_rejected():
    response = SimpleNamespace(
        text="truncated",
        usage_metadata=None,
        candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
    )
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k: response))
    with pytest.raises(ValueError):
        LLMManager(config=AppConfig(), credentials={})._provider_call(
            "gemini", client, "test", "q", None, None, 0.1, False, None
        )
