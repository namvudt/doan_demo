import hashlib
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.demo import DemoManager, DemoSearch, evidence_demo_response
from api.main import create_app
from api.worker import Worker
from core.config import AccuracyPolicy, AppConfig, load_config
from core.evidence import EvidenceReview, Region, check_claims, parse_visual_findings
from core.search import HeritageSearchEngine, relevant_passage
from core.tools import ToolExecutor, crop_root
from tests.conftest import FakeLLM
from tests.test_api import client as client
from tests.test_api import enqueue, identity, upload
from tests.test_api import settings as settings
from workflow.service import RunService


def config():
    return load_config("config/hanoi-evidence.yaml")


def ambiguous(role, kwargs):
    schema = kwargs.get("response_schema")
    name = getattr(schema, "__name__", "")
    if name == "ExecutionPlan":
        result = evidence_demo_response(schema, kwargs["prompt"])
        if "Thông tin người dùng bổ sung" not in kwargs["prompt"]:
            result["candidates"].append({"name": "OTHER"})
        return json.dumps(result)
    if name == "VisualFindings":
        result = evidence_demo_response(schema, kwargs["prompt"])
        result["candidates"] = ["DEMO", "OTHER"]
        return json.dumps(result)


def test_inherited_configuration_is_opt_in_and_env_override_is_validated(monkeypatch, tmp_path):
    assert not AppConfig().accuracy.enabled
    assert config().accuracy.enabled
    assert config().roles["visual"].max_output_tokens == 4096
    legacy = AppConfig().model_dump()
    legacy["providers"]["gpu"]["supports_json"] = False
    legacy["roles"]["visual"]["provider"] = "gpu"
    assert not AppConfig.model_validate(legacy).accuracy.enabled
    legacy["accuracy"]["enabled"] = True
    with pytest.raises(ValueError, match="JSON support"):
        AppConfig.model_validate(legacy)
    monkeypatch.setenv("HERITAGE_ACCURACY_ENABLED", "false")
    assert not config().accuracy.enabled
    monkeypatch.setenv("HERITAGE_ACCURACY_ENABLED", "invalid")
    with pytest.raises(ValueError):
        config()
    monkeypatch.delenv("HERITAGE_ACCURACY_ENABLED")
    a = tmp_path / "a.yaml"
    a.write_text("extends: a.yaml", encoding="utf-8")
    with pytest.raises(ValueError, match="cycle"):
        load_config(a)


def test_review_gate_rejects_wrong_slot_source_and_unquoted_history():
    policy = AccuracyPolicy(enabled=True)
    slots = [{"slot_id": "year", "question": "Year?", "evidence_type": "historical"}]
    evidence = [
        {
            "evidence_id": "e1",
            "kind": "source",
            "text": "Synthetic site was restored in a documented year.",
            "source_id": "web_test",
            "entity_id": "test",
            "version": "v1",
        }
    ]
    base = {
        "slot_id": "year",
        "text": "Synthetic historical claim",
        "kind": "historical",
        "verdict": "supported",
        "evidence_ids": ["e1"],
        "quotations": [{"evidence_id": "e1", "quote": evidence[0]["text"]}],
    }
    valid = check_claims(
        EvidenceReview(claims=[base]), evidence, slots, policy, identity_resolved=True
    )
    assert valid[0]["verdict"] == "supported"
    conflict = check_claims(
        EvidenceReview(claims=[base, {**base, "verdict": "contradicted"}]),
        evidence,
        slots,
        policy,
        identity_resolved=True,
    )
    assert len(conflict) == 1 and conflict[0]["verdict"] == "insufficient"
    assert "conflicting_duplicate" in conflict[0]["gate_errors"]
    for mutation, expected in [
        ({"slot_id": "invented"}, "unknown_slot"),
        ({"evidence_ids": ["fake"]}, "unregistered_evidence"),
        ({"evidence_ids": ["e1", "e1", "fake"]}, "unregistered_evidence"),
        ({"quotations": []}, "supporting_quote_missing"),
        ({"text": "https://fake.invalid"}, "model_generated_citation"),
    ]:
        review = EvidenceReview(claims=[{**base, **mutation}])
        result = check_claims(review, evidence, slots, policy, identity_resolved=True)[0]
        assert result["verdict"] == "insufficient" and expected in result["gate_errors"]
    assert (
        "identity_unresolved"
        in check_claims(
            EvidenceReview(claims=[base]), evidence, slots, policy, identity_resolved=False
        )[0]["gate_errors"]
    )
    # Mis-labelling a historical slot as visual cannot bypass the source requirement.
    visual = [
        {"evidence_id": "img", "kind": "visual", "text": "A roof is visible", "version": "v1"}
    ]
    claim = {**base, "kind": "visual", "evidence_ids": ["img"], "quotations": []}
    assert (
        "source_required"
        in check_claims(
            EvidenceReview(claims=[claim]), visual, slots, policy, identity_resolved=True
        )[0]["gate_errors"]
    )


def test_image_tools_preserve_root_coordinates_and_cache_ocr(photo):
    def behavior(role, kwargs):
        if getattr(kwargs.get("response_schema"), "__name__", "") == "OCROutput":
            return json.dumps(
                {"readable": True, "lines": [{"text": "Synthetic text", "box": [0, 0, 1, 1]}]}
            )

    manager = FakeLLM(behavior, config())
    tools = ToolExecutor(manager, photo)
    assert tools.quality()["calibrated"] is False
    region, data = tools.crop({"box": [0.25, 0.2, 0.75, 0.8]})
    tools.ocr(region, data)
    tools.ocr(region, data)
    assert len(manager.calls) == 1
    assert tools.calls[-1]["cached"]
    assert tools.evidence[0]["box"] == [0.25, 0.2, 0.75, 0.8]
    with Image.open(BytesIO(crop_root(photo, [0.25, 0.2, 0.75, 0.8]))) as cropped:
        assert cropped.size == (20, 18)
    with pytest.raises(ValueError):
        Region(box=[0.8, 0.2, 0.1, 1])
    with pytest.raises(ValueError):
        tools.execute("CodeExecutor", {}, lambda: None)


def test_retrieval_selects_question_passage_and_excludes_unreviewed_corpus(tmp_path):
    text = "Synthetic monument introduction.\n\nRestoration details for the synthetic gate."
    snippet, locator = relevant_passage(text, "restoration gate", 500)
    assert "Restoration" in snippet and locator.startswith("chars:")
    path = tmp_path / "corpus.jsonl"
    base = {
        "source_id": "web_seed",
        "title": "Synthetic gate",
        "url": "https://heritage.example/site",
        "type": "web",
        "snippet": text,
        "reviewer": "synthetic-test-reviewer",
        "reviewed_at": "2026-11-15",
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
    }
    path.write_text(
        "\n".join(
            json.dumps({**base, "annotation_status": status}) for status in ("draft", "reviewed")
        ),
        encoding="utf-8",
    )
    policy = config().accuracy.retrieval.model_copy(
        update={
            "wikipedia_enabled": False,
            "corpus_path": str(path),
            "allowed_domains": ["heritage.example"],
        }
    )
    result = HeritageSearchEngine(policy=policy).search_heritage("Synthetic", "restoration gate")
    assert len(result["sources"]) == 1
    assert result["sources"][0]["annotation_status"] == "reviewed"
    assert "Restoration" in result["sources"][0]["snippet"]


def test_profile_graph_emits_verifiable_claims_without_changing_legacy(photo):
    result = RunService(DemoManager(config()), search_engine_factory=DemoSearch).run(
        photo, "question"
    )
    assert result.status == "reviewed" and result.answer_status == "answered"
    assert result.result_schema_version == 2 and result.claims[0]["verdict"] == "supported"
    assert result.evidence and result.tool_calls and result.image_quality
    assert result.plan["identity_resolved"] is True
    reviewed = list(
        RunService(DemoManager(config()), search_engine_factory=DemoSearch).review_stream(
            photo, result
        )
    )[-1].result
    assert len(reviewed.calls) == 1 and reviewed.calls[0]["agent_role"] == "judge"
    assert reviewed.evidence == result.evidence


def test_clarification_reuses_visual_and_keeps_budget_and_parent(photo):
    manager = FakeLLM(ambiguous, config())
    service = RunService(manager, search_engine_factory=DemoSearch)
    parent = service.run(photo, "Question")
    saved = parent.model_dump()
    assert parent.answer_status == "needs_clarification"
    assert parent.clarification and not parent.final_response.startswith("- DEMO")
    child = list(service.continue_stream(photo, parent, {"answer": "DEMO", "rounds": 1}))[-1].result
    assert child.answer_status == "answered"
    assert child.parent_run_id == parent.run_id and child.run_kind == "clarification"
    assert "visual" in child.reused_nodes
    assert len(child.calls) == 4
    assert child.continuation_context["total_llm_calls"] == len(parent.calls)
    assert parent.model_dump() == saved


def test_changed_perception_config_invalidates_visual_reuse(photo):
    parent = RunService(FakeLLM(ambiguous, config()), search_engine_factory=DemoSearch).run(
        photo, "Question"
    )
    updated = config()
    updated.roles["visual"] = updated.roles["visual"].model_copy(
        update={"model": "changed-test-model"}
    )
    child = list(
        RunService(FakeLLM(ambiguous, updated), search_engine_factory=DemoSearch).continue_stream(
            photo, parent, {"answer": "DEMO", "rounds": 1}
        )
    )[-1].result
    assert "visual" not in child.reused_nodes and len(child.calls) == 5


def test_optional_ocr_failure_does_not_erase_visual_evidence(photo):
    def invalid_ocr(role, kwargs):
        if getattr(kwargs.get("response_schema"), "__name__", "") == "OCROutput":
            return "invalid JSON"

    result = RunService(FakeLLM(invalid_ocr, config()), search_engine_factory=DemoSearch).run(
        photo, "Question", focus_box=[0, 0, 1, 1]
    )
    assert result.answer_status == "answered"
    assert any(e["kind"] == "visual" for e in result.evidence)
    assert any(t["tool"] == "ocr_read" and t["status"] == "error" for t in result.tool_calls)


def test_visual_geometry_is_not_guessed_or_rescaled():
    findings, warnings = parse_visual_findings(
        {
            "observations": [
                {"text": "Synthetic roof", "box": [136, 308, 770, 776]},
                {"text": "Synthetic pillar", "box": [0.1, 0.2, 0.4, 0.8]},
            ]
        }
    )
    assert findings.observations[0].box is None
    assert findings.observations[1].box == [0.1, 0.2, 0.4, 0.8]
    assert warnings == [{"observation_index": 0, "code": "invalid_box_discarded"}]
    with pytest.raises(ValueError):
        parse_visual_findings({"observations": [{"box": [0, 0, 1, 1]}]})
    assert Region.model_json_schema()["properties"]["box"]["items"]["maximum"] == 1


def test_compact_provider_schema_keeps_backend_validation_and_coordinate_bounds():
    from core.evidence import VisualFindings
    from core.gateway import provider_json_schema

    full = provider_json_schema(EvidenceReview)
    compact = provider_json_schema(EvidenceReview, "compact")
    assert full["properties"]["claims"]["maxItems"] == 40
    assert "maxItems" not in compact["properties"]["claims"]
    assert "maxLength" not in compact["$defs"]["AssessedClaim"]["properties"]["text"]
    assert (
        provider_json_schema(VisualFindings, "compact")["$defs"]["Observation"]["properties"][
            "box"
        ]["anyOf"][0]["items"]["maximum"]
        == 1
    )
    with pytest.raises(ValueError):
        EvidenceReview.model_validate(
            {
                "claims": [
                    {
                        "slot_id": "test",
                        "text": "x" * 2001,
                        "kind": "visual",
                        "verdict": "insufficient",
                    }
                ]
            }
        )


def test_recovery_failure_preserves_supported_partial_answer(photo):
    class Search(DemoSearch):
        count = 0

        def search_heritage(self, *args, **kwargs):
            type(self).count += 1
            if self.count > 1:
                raise TimeoutError("synthetic retrieval failure")
            return super().search_heritage(*args, **kwargs)

    def partial(role, kwargs):
        name = getattr(kwargs.get("response_schema"), "__name__", "")
        if name == "ExecutionPlan":
            value = evidence_demo_response(kwargs["response_schema"], kwargs["prompt"])
            value["requested_slots"] = [
                {"slot_id": "visible", "question": "Visible?", "evidence_type": "visual"},
                {"slot_id": "history", "question": "History?", "evidence_type": "historical"},
            ]
            return json.dumps(value)
        if name == "EvidenceReview":
            payload = json.loads(kwargs["prompt"])
            visual = next(e for e in payload["evidence"] if e["kind"] == "visual")
            return json.dumps(
                {
                    "claims": [
                        {
                            "slot_id": "visible",
                            "text": "Synthetic visible feature",
                            "kind": "visual",
                            "verdict": "supported",
                            "evidence_ids": [visual["evidence_id"]],
                        }
                    ]
                }
            )

    result = RunService(FakeLLM(partial, config()), search_engine_factory=Search).run(
        photo, "Question"
    )
    assert result.answer_status == "partial" and result.status == "reviewed"
    assert "Synthetic visible feature" in result.final_response
    assert result.node_metadata["judge"]["recovery_error"]["error_type"] == "TimeoutError"
    assert Search.count == 2


def test_malformed_verifier_does_not_approve_draft(photo):
    manager = FakeLLM(lambda role, kwargs: "bad JSON" if role == "judge" else None, config())
    result = RunService(manager, search_engine_factory=DemoSearch).run(photo, "Question")
    assert result.answer_status == "verification_unavailable"
    assert result.status in {"failed", "unverified"} and not result.claims
    assert result.evidence and result.judge_report["error_code"] == "review_schema_invalid"


def test_evidence_api_crop_and_legacy_result_adapter(client, photo, monkeypatch):
    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    auth = identity(client)
    asset = upload(client, auth, photo)
    identifier = enqueue(client, auth, asset, focus_box=[0, 0, 0.5, 0.5])
    Worker(client.app.state.runtime).process_one()
    base = f"/api/v1/runs/{identifier}"
    data = client.get(base + "/evidence", headers=auth).json()
    assert data["answer_status"] == "answered" and data["result_schema_version"] == 2
    region = data["regions"][0]
    response = client.get(base + f"/regions/{region['region_id']}/image", headers=auth)
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert client.get(base + "/evidence", headers=identity(client)).status_code == 404
    assert client.get(base + "/regions/fake/image", headers=auth).status_code == 404


def test_api_clarification_is_atomic_owned_and_durable(settings, photo, monkeypatch):
    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        worker = Worker(client.app.state.runtime)
        assert worker.process_one()
        base = f"/api/v1/runs/{identifier}"
        assert client.get(base, headers=auth).json()["execution_status"] == "awaiting_input"
        parent = client.get(base + "/result", headers=auth).json()
        pending = client.get(base + "/clarification", headers=auth).json()["clarification"]
        assert "event: run.awaiting_input" in client.get(base + "/events", headers=auth).text
        body = {
            "clarification_id": pending["clarification_id"],
            "revision": pending["revision"],
            "answer": "DEMO",
        }
        assert (
            client.post(
                base + "/clarification",
                headers={**identity(client), "Idempotency-Key": "owner"},
                json=body,
            ).status_code
            == 404
        )
        assert (
            client.post(
                base + "/clarification",
                headers={**auth, "Idempotency-Key": "stale"},
                json={**body, "revision": 99},
            ).status_code
            == 409
        )
        headers = {**auth, "Idempotency-Key": "continuation"}
        child = client.post(base + "/clarification", headers=headers, json=body)
        assert child.status_code == 202, child.text
        child_id = child.json()["run_id"]
        assert (
            client.post(base + "/clarification", headers=headers, json=body).json()["run_id"]
            == child_id
        )
        assert (
            client.post(
                base + "/clarification", headers=headers, json={**body, "answer": "different"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                base + "/clarification", headers={**auth, "Idempotency-Key": "second"}, json=body
            ).status_code
            == 409
        )
        assert client.get(base + "/result", headers=auth).json() == parent
    # Queued continuation survives API/worker restart.
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as restarted:
        assert Worker(restarted.app.state.runtime).process_one()
        result = restarted.get(f"/api/v1/runs/{child_id}/result", headers=auth).json()
        assert result["answer_status"] == "answered"
        assert result["parent_run_id"] == identifier
        calls = restarted.get(f"/api/v1/runs/{child_id}/metrics", headers=auth).json()["calls"]
        assert len(calls) == 4 and all(c["agent_role"] != "visual" for c in calls)


@pytest.mark.parametrize(
    "condition,status", [("expired", 410), ("cancelled", 409), ("budget", 409), ("limit", 409)]
)
def test_clarification_cannot_bypass_lifecycle_or_budgets(
    settings, photo, monkeypatch, condition, status
):
    import time

    from api.models import Run

    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        runtime = client.app.state.runtime
        Worker(runtime).process_one()
        base = f"/api/v1/runs/{identifier}"
        pending = client.get(base + "/clarification", headers=auth).json()["clarification"]
        if condition == "cancelled":
            assert client.post(base + "/cancel", headers=auth).status_code == 200
        else:
            with runtime.db.session() as session:
                run = session.get(Run, identifier)
                if condition == "expired":
                    run.finished_at = time.time() - 90000
                elif condition == "budget":
                    run.result = {**run.result, "continuation_context": {"total_llm_calls": 24}}
                else:
                    run.result = {
                        **run.result,
                        "clarification": {**run.result["clarification"], "rounds": 2},
                    }
        response = client.post(
            base + "/clarification",
            headers={**auth, "Idempotency-Key": condition},
            json={
                "clarification_id": pending["clarification_id"],
                "revision": pending["revision"],
                "answer": "DEMO",
            },
        )
        assert response.status_code == status, response.text


def test_concurrent_clarifications_consume_one_revision(settings, photo, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        Worker(client.app.state.runtime).process_one()
        base = f"/api/v1/runs/{identifier}"
        pending = client.get(base + "/clarification", headers=auth).json()["clarification"]

        def send(key):
            return client.post(
                base + "/clarification",
                headers={**auth, "Idempotency-Key": key},
                json={
                    "clarification_id": pending["clarification_id"],
                    "revision": pending["revision"],
                    "answer": "DEMO",
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, ["first", "second"]))
        assert sorted(r.status_code for r in responses) == [202, 409]
        assert client.delete("/api/v1/sessions/me", headers=auth).status_code == 204


def test_remote_adapter_preserves_evidence_and_continues_pending_run(settings, photo, monkeypatch):
    import httpx

    from ui.api_client import RemoteManager

    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as client:

        def proxy(request):
            response = client.request(
                request.method,
                request.url.raw_path.decode(),
                headers=dict(request.headers),
                content=request.read(),
            )
            if request.method == "POST" and response.status_code == 202:
                Worker(client.app.state.runtime).process_one()
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=response.content,
                request=request,
            )

        manager = RemoteManager("http://testserver", transport=httpx.MockTransport(proxy))
        parent = list(manager.remote_stream(photo, "Question", "tourist"))[-1].result
        assert parent.answer_status == "needs_clarification" and parent.evidence
        child = list(manager.remote_continue_stream(photo, parent.model_dump(), "DEMO"))[-1].result
        assert child.answer_status == "answered" and child.parent_run_id == parent.run_id
        assert child.claims and child.evidence and len(child.calls) == 4


def test_sibling_reviews_share_reserved_conversation_budget(client, photo, monkeypatch):
    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    runtime = client.app.state.runtime
    Worker(runtime).process_one()
    base = f"/api/v1/runs/{identifier}"
    first = client.post(base + "/review", headers={**auth, "Idempotency-Key": "review-1"})
    second = client.post(base + "/review", headers={**auth, "Idempotency-Key": "review-2"})
    assert first.status_code == second.status_code == 202
    root = runtime.store.get_run(
        identifier, client.get("/api/v1/sessions/me", headers=auth).json()["session_id"]
    )
    owner = root.owner_id
    one = runtime.store.get_run(first.json()["run_id"], owner)
    two = runtime.store.get_run(second.json()["run_id"], owner)
    assert (
        one.input_context["conversation_root_id"]
        == two.input_context["conversation_root_id"]
        == identifier
    )
    assert (
        len(root.result["calls"])
        + one.config_snapshot["budget"]["max_llm_calls"]
        + two.config_snapshot["budget"]["max_llm_calls"]
        == 24
    )
    blocked = client.post(base + "/review", headers={**auth, "Idempotency-Key": "review-3"})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "conversation_budget"
    # A finished review releases unused reservation, so the next review can use remaining calls.
    Worker(runtime).process_one()
    assert (
        client.post(base + "/review", headers={**auth, "Idempotency-Key": "review-3"}).status_code
        == 202
    )


def test_version_five_migration_preserves_legacy_records_on_selected_database(settings):
    from tests.test_operational_logging import test_migration_preserves_old_records

    test_migration_preserves_old_records(settings)
