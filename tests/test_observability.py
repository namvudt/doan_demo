import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client, tracing_context

from core.config import AppConfig, BudgetConfig
from core.gateway import LLMManager, StreamInterrupted
from core.observability import (
    PrivateTracingClient,
    TraceSettings,
    token_usage,
    trace_operation,
)
from core.search import HeritageSearchEngine
from tests.conftest import FakeLLM
from workflow.service import RunService


@pytest.fixture
def recorded_traces(monkeypatch):
    records = []

    def create(self, name, inputs, run_type, **kwargs):
        records.append(
            deepcopy(
                {"op": "create", "name": name, "inputs": inputs, "run_type": run_type, **kwargs}
            )
        )

    def update(self, run_id, **kwargs):
        records.append(deepcopy({"op": "update", "id": run_id, **kwargs}))

    monkeypatch.setattr(Client, "create_run", create)
    monkeypatch.setattr(Client, "update_run", update)
    monkeypatch.setattr(Client, "flush", lambda *a, **k: None)
    client = PrivateTracingClient(api_key="test-key", auto_batch_tracing=False)
    monkeypatch.setattr("core.observability.tracing_client", lambda settings: client)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-heritage")
    yield records
    wait_for_all_tracers()


@pytest.mark.parametrize("tracing,key", [("false", "test"), ("true", "")])
def test_disabled_or_missing_key_creates_no_client(monkeypatch, tracing, key):
    monkeypatch.setenv("LANGSMITH_TRACING", tracing)
    monkeypatch.setenv("LANGSMITH_API_KEY", key)

    def unexpected(settings):
        pytest.fail("Disabled tracing must not create a client")

    monkeypatch.setattr("core.observability.tracing_client", unexpected)
    with trace_operation("disabled") as span:
        span.outputs = {"status": "success"}
    assert not TraceSettings.from_env().enabled


def test_native_graph_and_parallel_calls_share_private_trace(
    photo,
    fake_search,
    recorded_traces,
):
    # FakeLLM replaces transport; create spans here to check thread propagation too.
    def behavior(role, kwargs):
        with trace_operation(f"fake.{role}", "llm") as span:
            span.outputs = {"status": "success", "response": "PRIVATE_RESPONSE"}

    result = RunService(FakeLLM(behavior)).run(photo, "PRIVATE_QUESTION")
    wait_for_all_tracers()
    assert result.status == "reviewed"
    creates = [r for r in recorded_traces if r["op"] == "create"]
    root = next(r for r in creates if r["name"] == "heritage-vqa.run")
    assert str(root["id"]) == result.run_id
    assert root["session_name"] == "test-heritage"
    assert {"heritage-vqa.graph", "visual", "knowledge", "fake.visual", "fake.knowledge"} <= {
        r["name"] for r in creates
    }
    assert all(str(r["trace_id"]) == result.run_id for r in creates)
    assert all(r.get("parent_run_id") for r in creates if r is not root)
    assert any(
        r.get("extra", {}).get("metadata", {}).get("result_status") == "reviewed"
        for r in recorded_traces
    )
    serialized = json.dumps(recorded_traces, default=str)
    for private in ("PRIVATE_QUESTION", "PRIVATE_RESPONSE", "Test documented historical fact."):
        assert private not in serialized
    assert all(r.get("inputs", {}) == {} for r in recorded_traces)
    assert "image_data" not in serialized


def test_request_worker_context_reaches_native_and_model_traces(
    photo, fake_search, recorded_traces
):
    from uuid import uuid4

    from core.runtime_logging import log_context

    request_id, worker_id = str(uuid4()), str(uuid4())

    def behavior(role, kwargs):
        with trace_operation(f"fake.{role}", "llm"):
            pass

    with log_context(request_id=request_id, worker_id=worker_id):
        result = RunService(FakeLLM(behavior)).run(photo, "PRIVATE_QUESTION")
    wait_for_all_tracers()
    creates = [r for r in recorded_traces if r["op"] == "create"]
    assert creates
    for record in creates:
        metadata = record["extra"]["metadata"]
        assert metadata["request_id"] == request_id
        assert metadata["worker_id"] == worker_id
        assert str(record["trace_id"]) == result.run_id


def test_client_strips_attachments_events_serialized_and_exception_details(recorded_traces):
    client = PrivateTracingClient(api_key="test-key", auto_batch_tracing=False)
    client.create_run(
        "test",
        {"image": b"PRIVATE_IMAGE"},
        "chain",
        outputs={"answer": "PRIVATE_ANSWER", "status": "success"},
        serialized={"api_key": "PRIVATE_KEY"},
        attachments={"image": b"PRIVATE_IMAGE"},
        extra={
            "metadata": {"config": "PRIVATE_CONFIG", "agent_role": "visual"},
            "invocation_params": {"key": "PRIVATE_KEY"},
        },
    )
    client.update_run(
        "00000000-0000-0000-0000-000000000001",
        error="PRIVATE_ERROR",
        events=[{"text": "PRIVATE_EVENT"}],
        inputs={"query": "PRIVATE_QUERY"},
        outputs={"draft": "PRIVATE_DRAFT"},
    )
    serialized = json.dumps(recorded_traces, default=str)
    assert "PRIVATE_" not in serialized
    assert recorded_traces[0]["outputs"] == {"status": "success"}
    assert recorded_traces[1]["error"]


def test_model_attempts_record_retry_provider_and_usage(monkeypatch, recorded_traces):
    manager = LLMManager(
        config=AppConfig(budget=BudgetConfig(transient_retries=1)),
        credentials={},
    )
    monkeypatch.setattr(manager, "_client", lambda *a: object())
    attempts = 0

    def call(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("PRIVATE_PROVIDER_REQUEST")
        return (
            "PRIVATE_MODEL_RESPONSE",
            {
                "prompt_token_count": 10,
                "candidates_token_count": 4,
                "thoughts_token_count": 2,
                "total_token_count": 16,
            },
            "STOP",
        )

    monkeypatch.setattr(manager, "_provider_call", call)
    with trace_operation("test-root"):
        answer, _ = manager.call_llm("PRIVATE_PROMPT", agent_role="visual")
    assert answer == "PRIVATE_MODEL_RESPONSE"
    creates = [r for r in recorded_traces if r["op"] == "create" and r.get("run_type") == "llm"]
    assert [r["extra"]["metadata"]["retry"] for r in creates] == [0, 1]
    assert all(r["extra"]["metadata"]["ls_provider"] == "google_genai" for r in creates)
    assert any(r.get("error") for r in recorded_traces)
    assert any(
        r.get("outputs", {}).get("usage_metadata")
        == {
            "input_tokens": 10,
            "output_tokens": 6,
            "total_tokens": 16,
        }
        for r in recorded_traces
    )
    assert "PRIVATE_" not in json.dumps(recorded_traces, default=str)


def test_caught_node_failure_is_visible_without_raw_error(photo, recorded_traces):
    def fail(role, kwargs):
        raise ValueError("PRIVATE_MODEL_FAILURE")

    result = RunService(FakeLLM(fail)).run(photo, "PRIVATE_QUESTION")
    wait_for_all_tracers()
    assert result.status == "failed"
    assert any(
        r.get("extra", {}).get("metadata", {}).get("node_status") == "failed"
        for r in recorded_traces
    )
    assert any(r.get("error") for r in recorded_traces)
    assert "PRIVATE_" not in json.dumps(recorded_traces, default=str)


@pytest.mark.parametrize("outcome", ["success", "interrupted", "cancelled"])
def test_legacy_stream_is_private_and_handles_cancellation(monkeypatch, recorded_traces, outcome):
    def stream(**kwargs):
        yield SimpleNamespace(text="PRIVATE_CHUNK", usage_metadata=None)
        if outcome == "interrupted":
            raise TimeoutError("PRIVATE_PROVIDER_ERROR")

    manager = LLMManager(config=AppConfig(), credentials={})
    client = SimpleNamespace(models=SimpleNamespace(generate_content_stream=stream))
    monkeypatch.setattr(manager, "_client", lambda *a: client)
    generator = manager.stream_llm("PRIVATE_PROMPT", agent_role="visual")
    assert next(generator) == "PRIVATE_CHUNK"
    if outcome == "cancelled":
        generator.close()
    elif outcome == "interrupted":
        with pytest.raises(StreamInterrupted):
            next(generator)
    else:
        assert list(generator) == []
    assert (
        manager.calls[0]["status"]
        == {
            "success": "success",
            "interrupted": "error",
            "cancelled": "cancelled",
        }[outcome]
    )
    assert any(r["op"] == "create" and r["name"] == "model.visual.stream" for r in recorded_traces)
    assert "PRIVATE_" not in json.dumps(recorded_traces, default=str)


def test_search_timeout_has_errored_span(monkeypatch, recorded_traces):
    def fail(*args):
        raise TimeoutError("PRIVATE_SEARCH")

    monkeypatch.setattr(HeritageSearchEngine, "search_wikipedia", fail)
    result = HeritageSearchEngine().search_heritage("PRIVATE_MONUMENT", "PRIVATE_QUERY")
    assert result["status"] == "timeout"
    assert any(r.get("error") for r in recorded_traces)
    assert "PRIVATE_" not in json.dumps(recorded_traces, default=str)


def test_telemetry_outage_does_not_break_workflow_or_log_secrets(
    monkeypatch,
    photo,
    fake_search,
    recorded_traces,
    caplog,
):
    def fail(*args, **kwargs):
        raise ConnectionError("PRIVATE_NETWORK_CREDENTIAL")

    monkeypatch.setattr(Client, "create_run", fail)
    monkeypatch.setattr(Client, "update_run", fail)
    result = RunService(FakeLLM()).run(photo, "question")
    assert result.status == "reviewed"
    assert "PRIVATE_NETWORK_CREDENTIAL" not in caplog.text
    with pytest.raises(ValueError, match="original error"):
        with trace_operation("exception"):
            raise ValueError("original error")


def test_initialization_failure_runs_without_tracing(monkeypatch, photo, fake_search):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    def fail(settings):
        raise ValueError("invalid endpoint")

    monkeypatch.setattr("core.observability.tracing_client", fail)
    assert RunService(FakeLLM()).run(photo, "question").status == "reviewed"


def test_explicit_disabled_context_wins_over_env(recorded_traces):
    with tracing_context(enabled=False):
        with trace_operation("disabled-child"):
            pass
    assert recorded_traces == []


def test_usage_missing_stays_unknown_and_settings_repr_hides_key():
    assert token_usage(None, "gemini") == {}
    assert token_usage({"total_tokens": 5}, "openai") == {"total_tokens": 5}
    assert "private-key" not in repr(TraceSettings(enabled=True, api_key="private-key"))


def test_content_mode_keeps_workflow_input_reports_and_image_fingerprint(
    monkeypatch, photo, fake_search, recorded_traces
):
    monkeypatch.setenv("LANGSMITH_CAPTURE_CONTENT", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "sensitive-test-credential-12345")
    question = "Observe this monument; sensitive-test-credential-12345"
    result = RunService(FakeLLM()).run(photo, question)
    wait_for_all_tracers()
    creates = [r for r in recorded_traces if r["op"] == "create"]
    root = next(r for r in creates if r["name"] == "heritage-vqa.run")
    assert root["inputs"]["query"] == "Observe this monument; [REDACTED]"
    assert root["inputs"]["image_data"]["width"] == 40
    assert len(root["inputs"]["image_data"]["sha256"]) == 64
    updates = [r for r in recorded_traces if r["op"] == "update"]
    assert any(r.get("outputs", {}).get("final_response") == result.final_response for r in updates)
    assert any(r["inputs"].get("query") for r in creates if r["name"] == "heritage-vqa.graph")
    payload = json.dumps(recorded_traces, default=str)
    assert "sensitive-test-credential-12345" not in payload
    assert "mock visual findings" in payload


def test_failed_response_has_input_output_usage_and_diagnostics_in_trace(
    monkeypatch, recorded_traces
):
    from core.model_errors import TruncatedModelResponse

    monkeypatch.setenv("LANGSMITH_CAPTURE_CONTENT", "true")
    manager = LLMManager(
        config=AppConfig(budget=BudgetConfig(truncation_retries=0)), credentials={}
    )
    monkeypatch.setattr(manager, "_client", lambda *a: object())

    def fail(*args):
        raise TruncatedModelResponse(
            text="partial output", finish_reason="MAX_TOKENS", usage={"total_token_count": 2048}
        )

    monkeypatch.setattr(manager, "_provider_call", fail)
    with pytest.raises(TruncatedModelResponse):
        manager.call_llm(
            "Inspect the architecture",
            system_instruction="Use visual evidence",
            agent_role="visual",
        )
    creates = [r for r in recorded_traces if r["op"] == "create" and r["run_type"] == "llm"]
    assert creates[0]["inputs"]["prompt"] == "Inspect the architecture"
    assert creates[0]["inputs"]["system_instruction"] == "Use visual evidence"
    outputs = [
        r["outputs"]
        for r in recorded_traces
        if r["op"] == "update" and r.get("outputs", {}).get("finish_reason") == "MAX_TOKENS"
    ]
    assert outputs
    assert outputs[-1]["response"] == "partial output"
    assert outputs[-1]["usage_metadata"]["total_tokens"] == 2048
    assert manager.calls[0]["finish_reason"] == "MAX_TOKENS"
    assert manager.calls[0]["usage"] == {"total_token_count": 2048}


def test_content_sanitizer_bounds_nested_graph_state_and_removes_secrets(monkeypatch):
    from core.trace_content import sanitize_content

    monkeypatch.setenv("SOME_API_KEY", "abcdef-secret-credential-123456")
    raw = {
        "query": "abcdef-secret-credential-123456 and Bearer tokenXYZ",
        "api_key": "abcdef-secret-credential-123456",
        "config_snapshot": {"key": "hidden"},
        "prompt": "x" * 50000,
        "image_data": b"binary-not-for-export",
        "response": "url https://example.test/?api_key=another_secret&ok=1",
    }
    result = sanitize_content(raw)
    assert result["query"] == "[REDACTED] and Bearer [REDACTED]"
    assert "api_key" not in result and "config_snapshot" not in result
    assert result["prompt"].endswith("[TRUNCATED]")
    assert len(result["prompt"]) < 12100
    assert "another_secret" not in result["response"]
    assert isinstance(result["image_data"], dict)


def test_content_mode_handles_native_error_with_null_outputs(monkeypatch, recorded_traces):
    monkeypatch.setenv("LANGSMITH_CAPTURE_CONTENT", "true")
    client = PrivateTracingClient(api_key="test-key", auto_batch_tracing=False)
    identifier = "00000000-0000-0000-0000-000000000001"
    client.update_run(identifier, outputs=None, error="ValueError")
    assert recorded_traces[-1]["op"] == "update"
    assert recorded_traces[-1]["outputs"] == {}
    assert recorded_traces[-1]["error"] == "ValueError"
