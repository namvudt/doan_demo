import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from core.config import AppConfig
from core.evaluation import validate_manifest
from core.evaluation_runtime import (
    EvaluationGate,
    EvaluationPaused,
    EvaluationPolicy,
    PacedLLMManager,
    retry_after_seconds,
)
from core.gateway import BudgetExceeded
from scripts.evaluate import run_predictions


class Clock:
    def __init__(self):
        self.now = 1000.0

    def sleep(self, seconds):
        self.now += seconds


def gate(policy=None):
    clock = Clock()
    policy = policy or EvaluationPolicy()
    return EvaluationGate(
        policy, monotonic=lambda: clock.now, wall=lambda: clock.now, sleep=clock.sleep
    )


def test_parallel_model_requests_are_serialized_and_spaced():
    paced = gate()
    starts = []

    def request():
        return paced.request(
            lambda: starts.append(paced.monotonic()), remaining_seconds=lambda: 600
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: request(), range(3)))
    assert starts == [1000, 1030, 1060]
    assert paced.provider_calls == 3


def test_429_stops_later_requests_and_honors_provider_retry_hint():
    paced = gate()

    class QuotaError(Exception):
        code = 429
        response_json = {
            "error": {
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "180s"}
                ]
            }
        }

    def limited():
        raise QuotaError("must not persist request or credential text")

    with pytest.raises(QuotaError):
        paced.request(limited, remaining_seconds=lambda: 600)
    with pytest.raises(EvaluationPaused):
        paced.request(lambda: pytest.fail("Must not call provider"), remaining_seconds=lambda: 600)
    snapshot = paced.snapshot()
    assert {
        k: snapshot[k]
        for k in ("provider_calls", "stop_reason", "retry_not_before", "request_start_times")
    } == {
        "provider_calls": 1,
        "stop_reason": "provider_429",
        "retry_not_before": 1180,
        "request_start_times": [1000],
    }


def test_call_budget_and_deadline_refuse_before_spending():
    paced = gate(EvaluationPolicy(max_provider_calls=1))
    paced.request(lambda: None, remaining_seconds=lambda: 600)
    with pytest.raises(EvaluationPaused):
        paced.request(lambda: pytest.fail("budget"), remaining_seconds=lambda: 600)
    paced = gate()
    paced.request(lambda: None, remaining_seconds=lambda: 600)
    with pytest.raises(BudgetExceeded):
        paced.request(lambda: pytest.fail("deadline"), remaining_seconds=lambda: 5)
    assert paced.provider_calls == 1


def test_retry_hints_and_clone_policy():
    error = SimpleNamespace(
        response=SimpleNamespace(headers={"retry-after": "120"}), response_json={"error": "bad"}
    )
    assert retry_after_seconds(error, 1000) == 120
    manager = PacedLLMManager(gate=gate(), config=AppConfig(), credentials={})
    clone = manager.for_run(benchmark=True)
    assert clone.gate is manager.gate
    assert not clone.config.fallback_providers and clone.config.budget.transient_retries == 0
    clone.close()
    manager.close()


def test_evaluation_profile_completes_graph_stream_with_demo():
    script = """
from pathlib import Path
from api.demo import DemoManager, DemoSearch
from core.config import load_config
from workflow.service import RunService
config = load_config('config/evaluation/hanoi-paced.yaml')
result = RunService(DemoManager(config), search_engine_factory=DemoSearch).run(
    Path('samples/chua_huong.jpg').read_bytes(), 'Identify this monument')
assert result.status in {'reviewed', 'insufficient_evidence'}
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_interrupted_case_is_not_silently_replayed(tmp_path):
    policy, paced = EvaluationPolicy(), gate()

    def interrupted(*_):
        raise KeyboardInterrupt()

    service = SimpleNamespace(config=AppConfig(), run=interrupted)
    cases, output = inputs(tmp_path), tmp_path / "predictions.json"
    options = dict(output=output, policy=policy, model_mode="live", sleep=lambda _: None)
    with pytest.raises(KeyboardInterrupt):
        run_predictions(cases, service, gate=paced, **options)
    service.run = lambda *_: pytest.fail("Do not replay interrupted paid cases")
    with pytest.raises(ValueError, match="Interrupted case"):
        run_predictions(cases, service, gate=gate(policy), resume=True, **options)


def test_resume_refuses_unknown_budget_when_checkpoint_is_missing(tmp_path):
    output = tmp_path / "predictions.json"
    output.write_text("[]", encoding="utf-8")
    service = SimpleNamespace(config=AppConfig(), run=lambda *_: pytest.fail("Unknown budget"))
    with pytest.raises(ValueError, match="provider budget is unknown"):
        run_predictions(
            inputs(tmp_path),
            service,
            output=output,
            policy=EvaluationPolicy(),
            gate=gate(),
            model_mode="live",
            resume=True,
        )


def inputs(tmp_path):
    image = tmp_path / "image.png"
    stream = BytesIO()
    Image.new("RGB", (64, 64), "red").save(stream, format="PNG")
    image.write_bytes(stream.getvalue())
    return validate_manifest(
        [
            {
                "case_id": f"case-{i}",
                "image_path": str(image),
                "image_family": "same-image",
                "entity_group": "same-entity",
                "question": f"Synthetic question {i}",
                "slots": [{"slot_id": "s", "question": "Feature?", "kind": "visual"}],
            }
            for i in range(3)
        ],
        allow_draft=True,
    )


def test_resume_skips_attempted_cases_and_rejects_changed_image(tmp_path):
    calls, sleeps = [], []
    policy = EvaluationPolicy(max_cases=1, case_spacing_seconds=60)

    def run(content, question):
        calls.append(question)
        return SimpleNamespace(model_dump=lambda **_: {"status": "reviewed"})

    service = SimpleNamespace(config=AppConfig(), run=run)
    cases, output = inputs(tmp_path), tmp_path / "predictions.json"
    options = dict(output=output, policy=policy, model_mode="live", sleep=sleeps.append)
    run_predictions(cases, service, gate=gate(policy), **options)
    run_predictions(cases, service, gate=gate(policy), resume=True, **options)
    assert calls == ["Synthetic question 0", "Synthetic question 1"] and sleeps == [60]
    assert len(json.loads(output.read_text())) == 2
    cases[0].question = "Changed question"
    with pytest.raises(ValueError, match="changed"):
        run_predictions(cases, service, gate=gate(policy), resume=True, **options)
    cases = inputs(tmp_path)
    image = tmp_path / "image.png"
    stream = BytesIO()
    Image.new("RGB", (64, 64), "blue").save(stream, format="PNG")
    image.write_bytes(stream.getvalue())
    with pytest.raises(ValueError, match="image content changed"):
        run_predictions(cases, service, gate=gate(policy), resume=True, **options)
    assert len(calls) == 2


def test_batch_checkpoints_failed_429_and_does_not_send_next_case(tmp_path):
    policy = EvaluationPolicy()
    paced, calls = gate(policy), []

    class QuotaError(Exception):
        code = 429

    def run(content, question):
        calls.append(question)
        paced.stop_reason = "provider_429"
        paced.retry_not_before = 2000
        return SimpleNamespace(
            model_dump=lambda **_: {"status": "failed", "errors": [{"provider_status_code": 429}]}
        )

    service = SimpleNamespace(config=AppConfig(), run=run)
    cases, output = inputs(tmp_path), tmp_path / "predictions.json"
    options = dict(output=output, policy=policy, model_mode="live", sleep=lambda _: None)
    records = run_predictions(cases, service, gate=paced, wall=lambda: 1000, **options)
    assert len(records) == len(calls) == 1
    progress = json.loads(output.with_suffix(".run.json").read_text())
    assert progress["status"] == "paused" and progress["remaining_case_ids"] == ["case-1", "case-2"]
    with pytest.raises(ValueError, match="cooldown"):
        run_predictions(
            cases, service, gate=gate(policy), resume=True, wall=lambda: 1000, **options
        )
    assert len(calls) == 1


def test_preflight_exception_is_checkpointed_and_stops_the_batch(tmp_path):
    policy, paced = EvaluationPolicy(), gate()

    class QuotaError(Exception):
        code = 429

    def run(*_):
        raise QuotaError("secret diagnostic must not be written")

    service = SimpleNamespace(config=AppConfig(), run=run)
    output = tmp_path / "predictions.json"
    records = run_predictions(
        inputs(tmp_path), service, output=output, policy=policy, gate=paced, model_mode="live"
    )
    assert len(records) == 1 and records[0]["result"]["errors"][0]["provider_status_code"] == 429
    assert "secret diagnostic" not in output.read_text()


def test_operator_pause_stops_after_current_case_without_replaying(tmp_path):
    policy = EvaluationPolicy(case_spacing_seconds=0)
    calls = []

    def run(content, question):
        calls.append(question)
        return SimpleNamespace(model_dump=lambda **_: {"status": "reviewed"})

    output = tmp_path / "predictions.json"
    service = SimpleNamespace(config=AppConfig(), run=run)
    paced = gate(policy)
    records = run_predictions(
        inputs(tmp_path),
        service,
        output=output,
        policy=policy,
        gate=paced,
        model_mode="live",
        pause_check=lambda: bool(calls),
    )
    assert len(records) == 1 and len(calls) == 1 and paced.stop_reason == "operator_pause"


def test_pause_requested_during_case_sleep_stops_next_case(tmp_path):
    policy = EvaluationPolicy(case_spacing_seconds=2)
    calls, paused = [], []

    def run(content, question):
        calls.append(question)
        return SimpleNamespace(model_dump=lambda **_: {"status": "reviewed"})

    paced = gate(policy)
    run_predictions(
        inputs(tmp_path),
        SimpleNamespace(config=AppConfig(), run=run),
        output=tmp_path / "p.json",
        policy=policy,
        gate=paced,
        model_mode="live",
        sleep=lambda _: paused.append(True),
        pause_check=lambda: bool(paused),
    )
    assert len(calls) == 1 and paced.stop_reason == "operator_pause"
