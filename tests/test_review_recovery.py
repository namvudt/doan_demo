import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PIL import Image

from agents.review import JudgeAgent
from api.worker import Worker
from core.config import AppConfig, RoleConfig
from core.gateway import LLMManager
from core.images import image_bytes
from core.model_errors import failure_info
from core.preflight import PreflightFailed
from tests.conftest import FakeLLM, valid_review
from tests.test_api import client as client
from tests.test_api import enqueue, identity, upload
from tests.test_api import settings as settings
from workflow.service import RunService


class InvalidCredential(Exception):
    code = 400
    response_json = {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}


def metadata_manager(monkeypatch, get, *, judge_key="test-judge", config=None):
    manager = LLMManager(
        config=config or AppConfig(),
        credentials={"GEMINI_API_KEY": "test-shared", "JUDGE_API_KEY": judge_key},
    )
    monkeypatch.setattr(
        manager, "_client", lambda *args: SimpleNamespace(models=SimpleNamespace(get=get))
    )
    return manager


def test_preflight_deduplicates_shared_bindings_and_cache_invalidates(monkeypatch):
    seen = []
    lock = threading.Lock()

    def get(**kwargs):
        with lock:
            seen.append(kwargs)
        time.sleep(0.02)

    manager = metadata_manager(monkeypatch, get)
    # Isolate this test from the process-global cache using unique metadata identity.
    manager._credentials["GEMINI_API_KEY"] = "unique-cache-test"
    manager._credentials["JUDGE_API_KEY"] = "unique-cache-test"
    with ThreadPoolExecutor(2) as pool:
        reports = list(pool.map(lambda _: manager.preflight(), range(2)))
    assert all(r["ready"] for r in reports)
    assert len(seen) == 1 and not manager.calls
    assert all(r["cached"] for r in manager.preflight()["roles"])
    manager.preflight(["judge"], force=True)
    assert len(seen) == 2
    manager._credentials["JUDGE_API_KEY"] = "unique-cache-replacement"
    manager.preflight(["judge"])
    assert len(seen) == 3
    assert "unique-cache" not in json.dumps(reports)


def test_invalid_judge_preflight_stops_before_any_generation(monkeypatch, photo):
    manager = metadata_manager(
        monkeypatch,
        lambda **kw: (_ for _ in ()).throw(InvalidCredential("PRIVATE_BODY")),
        judge_key="test-invalid-preflight",
    )
    monkeypatch.setattr(manager, "for_run", lambda **kw: manager)

    def models_for(provider, model, credential):
        def get(**kwargs):
            if credential == "test-invalid-preflight":
                raise InvalidCredential("PRIVATE_BODY")

        return SimpleNamespace(models=SimpleNamespace(get=get))

    monkeypatch.setattr(manager, "_client", models_for)
    with pytest.raises(PreflightFailed) as caught:
        RunService(manager).run(photo, "test")
    assert not manager.calls
    assert caught.value.failures[0]["error_code"] == "credential_invalid"
    assert [item["role"] for item in caught.value.failures] == ["judge"]
    assert "PRIVATE_BODY" not in json.dumps(caught.value.report)
    assert caught.value.report["generation_verified"] is False


@pytest.mark.parametrize(
    "mutate,code,category",
    [
        (lambda r: r.update(cited_source_ids=["wiki_fake"]), "unknown_citation", "evidence"),
        (lambda r: r.update(cited_source_ids=[]), "unregistered_inline_citation", "evidence"),
        (
            lambda r: r.update(final_response="Uncited", cited_source_ids=[]),
            "missing_citation",
            "evidence",
        ),
        (
            lambda r: r.update(final_response="https://unregistered.invalid [wiki_a]"),
            "model_generated_url",
            "evidence",
        ),
        (lambda r: r.update(overall_status="invalid"), "review_schema_invalid", "review_format"),
    ],
)
def test_judge_errors_are_typed(mutate, code, category, source):
    review = valid_review()
    mutate(review)
    manager = FakeLLM(lambda *args: json.dumps(review))
    report, meta = JudgeAgent(manager).evaluate_and_refine(
        "q", "draft", "visual", [source], Image.new("RGB", (2, 2)), True
    )
    assert report["verification_status"] == "unverified"
    assert report["error_code"] == meta["error_code"] == code
    assert report["error_category"] == category


def test_judge_provider_failure_is_not_a_content_rejection(source):
    def fail(*args):
        raise InvalidCredential("private response")

    report, _ = JudgeAgent(FakeLLM(fail)).evaluate_and_refine(
        "q", "draft", "visual", [source], Image.new("RGB", (2, 2)), True
    )
    assert report["error_code"] == "credential_invalid"
    assert report["error_category"] == "configuration"
    assert report["provider_reason"] == "API_KEY_INVALID"
    assert report["retryable"] is False
    assert "private response" not in json.dumps(report)
    assert failure_info(TimeoutError())["retryable"] is True


def test_exhausted_provider_retries_preserve_original_failure_code():
    class QuotaError(Exception):
        status_code = 429

    try:
        try:
            raise QuotaError("private quota body")
        except QuotaError as error:
            raise RuntimeError("Providers unavailable") from error
    except RuntimeError as error:
        info = failure_info(error, "judge")
    assert info["error_code"] == "provider_unavailable"
    assert info["provider_status_code"] == 429 and info["retryable"]
    assert "private quota body" not in json.dumps(info)


def test_gpu_preflight_checks_configured_model_without_generating(monkeypatch):
    config = AppConfig()
    config = config.model_copy(
        update={"roles": {**config.roles, "judge": RoleConfig(provider="gpu")}}
    )
    manager = LLMManager(
        config=config,
        credentials={
            "LOCAL_INFERENCE_API_KEY": "gpu-preflight-test",
            "LOCAL_INFERENCE_URL": "http://127.0.0.1:9999/v1",
        },
    )
    monkeypatch.setattr(
        manager,
        "_client",
        lambda *args: SimpleNamespace(
            models=SimpleNamespace(
                list=lambda **kwargs: SimpleNamespace(data=[SimpleNamespace(id="local-vlm")])
            )
        ),
    )
    assert manager.preflight(["judge"])["ready"]
    assert not manager.calls
    manager._credentials["LOCAL_INFERENCE_URL"] = "http://127.0.0.1:9998/v1"
    monkeypatch.setattr(
        manager,
        "_client",
        lambda *args: SimpleNamespace(
            models=SimpleNamespace(list=lambda **kwargs: SimpleNamespace(data=[]))
        ),
    )
    report = manager.preflight(["judge"])
    assert report["ready"] is False
    assert report["roles"][0]["error_code"] == "model_not_found"


def test_judge_only_run_reuses_evidence_and_preserves_parent(photo, fake_search):
    parent = RunService(FakeLLM(lambda role, kw: "invalid" if role == "judge" else None)).run(
        photo, "q"
    )
    original = parent.model_dump()
    llm = FakeLLM()
    events = list(RunService(llm).review_stream(photo, parent))
    result = events[-1].result
    assert result.status == "reviewed"
    assert result.run_id != parent.run_id and result.parent_run_id == parent.run_id
    assert result.run_kind == "review"
    assert result.expert_results == parent.expert_results
    assert result.draft_response == parent.draft_response
    assert result.plan == parent.plan and not result.errors
    assert [call["agent_role"] for call in llm.history] == ["judge"]
    assert len(result.calls) == 1
    reused = [event for event in events if event.payload.get("reused")]
    assert {event.node for event in reused} == set(result.reused_nodes)
    assert all(
        event.duration == 0 and event.payload["source_run_id"] == parent.run_id for event in reused
    )
    assert parent.model_dump() == original
    with pytest.raises(ValueError, match="image does not match"):
        list(RunService(FakeLLM()).review_stream(image_bytes(Image.new("RGB", (4, 4))), parent))
    incomplete = deepcopy(original)
    incomplete["expert_results"]["knowledge"]["meta"]["live_search_sources"] = []
    with pytest.raises(ValueError, match="source evidence"):
        list(RunService(FakeLLM()).review_stream(photo, incomplete))


def test_preflight_api_is_authenticated_and_validated(client):
    assert client.post("/api/v1/preflight", json={}).status_code == 401
    auth = identity(client)
    report = client.post("/api/v1/preflight", headers=auth, json={}).json()
    assert report["ready"] and report["scope"] == "offline_demo"
    assert len(report["roles"]) == 4 and not report["generation_verified"]
    assert client.post("/api/v1/preflight", headers=auth, json={"roles": []}).status_code == 422
    assert (
        client.post("/api/v1/preflight", headers=auth, json={"roles": ["unknown"]}).status_code
        == 422
    )


def test_invalid_role_configuration_rejects_admission_without_queueing(client, photo, monkeypatch):
    auth = identity(client)
    asset = upload(client, auth, photo)
    report = {
        "ready": False,
        "scope": "model_metadata",
        "generation_verified": False,
        "roles": [
            {
                "role": "judge",
                "provider": "gemini",
                "model": "mock",
                "ready": False,
                "cached": False,
                "error_code": "credential_invalid",
                "error_category": "configuration",
                "retryable": False,
                "provider_reason": "API_KEY_INVALID",
            }
        ],
    }
    manager = SimpleNamespace(preflight=lambda *a, **k: report, close=lambda: None)
    monkeypatch.setattr(client.app.state.runtime, "manager", lambda: manager)
    response = client.post(
        "/api/v1/runs", headers=auth, json={"asset_id": asset, "question": "test"}
    )
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "credential_invalid"
    assert error["details"]["roles"][0]["role"] == "judge"
    assert client.get("/api/v1/runs", headers=auth).json()["total"] == 0


def test_review_api_is_durable_owned_idempotent_and_judge_only(client, photo):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    base = f"/api/v1/runs/{identifier}"
    review_headers = {**auth, "Idempotency-Key": "review-test"}
    assert client.post(base + "/review", headers=review_headers).status_code == 409
    worker = Worker(client.app.state.runtime)
    assert worker.process_one()
    parent = client.get(base + "/result", headers=auth).json()
    assert client.post(base + "/review", headers=identity(client)).status_code == 422
    other = {**identity(client), "Idempotency-Key": "other"}
    assert client.post(base + "/review", headers=other).status_code == 404
    response = client.post(base + "/review", headers=review_headers)
    assert response.status_code == 202, response.text
    child = response.json()
    assert child["parent_run_id"] == identifier and child["run_kind"] == "review"
    assert client.post(base + "/review", headers=review_headers).json()["run_id"] == child["run_id"]
    # Same key must not alias the full retry operation.
    assert client.post(base + "/retry", headers=review_headers).status_code == 409
    assert worker.process_one()
    path = f"/api/v1/runs/{child['run_id']}"
    result = client.get(
        path + "/result", headers=auth, params={"include_intermediate": True}
    ).json()
    assert result["status"] == "reviewed" and result["run_kind"] == "review"
    assert result["sources"] == parent["sources"]
    assert result["intermediate"]["stages"]["aggregate"]["payload"]["reused"]
    metrics = client.get(path + "/metrics", headers=auth).json()
    assert [c["agent_role"] for c in metrics["calls"]] == ["judge"]
    assert client.get(base + "/result", headers=auth).json() == parent
