"""Behavioral regressions for per-question coverage; historical strings here are synthetic."""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.worker import Worker
from core.config import load_config
from core.questions import response_is_unknown
from tests.conftest import FakeLLM
from tests.test_accuracy_profile import ambiguous
from tests.test_api import identity, upload
from tests.test_api import settings as settings
from tests.test_recognition import NAME, NoSources, recognition_response, service
from workflow.service import RunService


@pytest.mark.parametrize(
    "query",
    [
        "Tôi không cần xác nhận chắc chắn, chỉ muốn biết có thể là nơi nào.",
        "Khong can xac nhan chac chan, day co the la dau?",
        "No need to identify with certainty. What might it be?",
        "Tôi không yêu cầu khẳng định chắc chắn.",
    ],
)
def test_negated_certainty_does_not_force_absolute_verification(photo, query):
    result = service().run(photo, query)
    assert result.answer_status == "answered" and result.clarification is None
    assert result.slot_results[0].status == "answered"
    assert result.slot_results[0].evidence_ids == result.recognition.evidence_ids


def test_separate_positive_certainty_clause_is_still_enforced(photo):
    result = service().run(photo, "Không cần mô tả. Hãy xác nhận chắc chắn danh tính.")
    assert result.answer_status == "partial"
    assert result.slot_results[0].reason_codes == ["identity_unconfirmed"]


def test_visual_identity_question_does_not_call_unneeded_knowledge_agent(photo):
    base = recognition_response()

    def respond(role, kwargs):
        value = base(role, kwargs)
        if getattr(kwargs.get("response_schema"), "__name__", "") == "ExecutionPlan":
            value = json.loads(value)
            value["selected_agents"].append("knowledge_agent")
            return json.dumps(value)
        return value

    result = RunService(FakeLLM(respond, load_config("config/hanoi-evidence.yaml"))).run(
        photo, "Nhận diện từ ảnh, không cần lịch sử"
    )
    assert result.answer_status == "answered"
    assert result.plan["selected_agents"] == ["visual_agent"]
    assert all(call["agent_role"] != "knowledge" for call in result.calls)
    assert all(call["tool"] != "retrieve_heritage" for call in result.tool_calls)


class HistorySearch:
    def search_heritage(self, **kwargs):
        text = f"SYNTHETIC: {NAME} được khởi dựng năm 1500 trong dữ liệu kiểm thử giả."
        return {
            "status": "success",
            "error": None,
            "context_text": text,
            "navigation_links": [],
            "sources": [
                {
                    "source_id": "synthetic_history",
                    "title": NAME + " - synthetic test fixture",
                    "snippet": text,
                    "url": "https://example.org/synthetic-history",
                    "type": "web",
                }
            ],
        }


def history_response(*, complete=True, conflict=False):
    base = recognition_response()

    def respond(role, kwargs):
        schema = getattr(kwargs.get("response_schema"), "__name__", "")
        if schema == "ExecutionPlan":
            return json.dumps(
                {
                    "selected_agents": ["visual_agent", "knowledge_agent"],
                    "candidates": [{"name": NAME}],
                    "requested_slots": [
                        {
                            "slot_id": "history",
                            "question": "Khởi dựng và trùng tu khi nào?",
                            "evidence_type": "historical",
                        }
                    ],
                }
            )
        if schema == "EvidenceReview":
            data = json.loads(kwargs["prompt"])
            source = next(e for e in data["evidence"] if e["kind"] == "source")
            slot = next(s for s in data["requested_slots"] if s.get("aspect") == "construction")
            return json.dumps(
                {
                    "claims": [
                        {
                            "slot_id": slot["slot_id"],
                            "kind": "historical",
                            "text": source["text"],
                            "verdict": "supported",
                            "evidence_ids": [source["evidence_id"]],
                            "quotations": [
                                {"evidence_id": source["evidence_id"], "quote": source["text"]}
                            ],
                        }
                    ],
                    "slot_assessments": [
                        {
                            "slot_id": slot["slot_id"],
                            "status": "conflicted"
                            if conflict
                            else "complete"
                            if complete
                            else "partial",
                            "missing_information": [] if complete else ["Chưa trả lời hết ý hỏi"],
                        }
                    ]
                    + [
                        {
                            "slot_id": s["slot_id"],
                            "status": "unanswered",
                            "missing_information": ["Nguồn kiểm thử chưa có dữ kiện này."],
                        }
                        for s in data["requested_slots"]
                        if s["slot_id"] != slot["slot_id"]
                    ],
                }
            )
        return base(role, kwargs)

    return respond


def test_compound_history_is_split_and_one_fact_cannot_complete_two_events(photo):
    result = RunService(
        FakeLLM(history_response(), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=HistorySearch,
    ).run(photo, "Cho biết khởi dựng và trùng tu khi nào?")
    slots = {s["aspect"]: s["slot_id"] for s in result.requested_slots}
    assert set(slots) == {"construction", "restoration"}
    results = {s.slot_id: s for s in result.slot_results}
    assert results[slots["construction"]].status == "answered"
    assert results[slots["restoration"]].status == "unanswered"
    assert "missing_source" in results[slots["restoration"]].reason_codes
    assert result.answer_status == "partial" and result.clarification is None
    assert result.slot_results[0].claim_ids == [result.claims[0]["claim_id"]]
    event = next(e for e in result.events if e.node == "judge" and e.status == "completed")
    assert event.payload["slot_results"] == [s.model_dump() for s in result.slot_results]


def test_original_or_is_not_turned_into_and():
    from core.questions import atomic_slots

    cfg = load_config("config/hanoi-evidence.yaml")
    slots = [
        {
            "slot_id": "history",
            "question": "Khởi dựng và trùng tu khi nào?",
            "evidence_type": "historical",
        }
    ]
    assert atomic_slots(slots, "Đối chiếu khởi dựng hoặc trùng tu", cfg.accuracy.questions) == slots


@pytest.mark.parametrize(
    "conflict,expected,reason",
    [
        (False, "partial", "incomplete_answer"),
        (True, "conflicted", "source_conflict"),
    ],
)
def test_semantic_coverage_or_conflict_is_not_overridden_by_one_supported_claim(
    photo, conflict, expected, reason
):
    result = RunService(
        FakeLLM(
            history_response(complete=False, conflict=conflict),
            load_config("config/hanoi-evidence.yaml"),
        ),
        search_engine_factory=HistorySearch,
    ).run(photo, "Khởi dựng và trùng tu khi nào?")
    assert result.slot_results[0].status == expected
    assert reason in result.slot_results[0].reason_codes
    assert result.answer_status == "partial"
    if conflict:
        assert "Nguồn còn bất đồng" in result.final_response


def test_mixed_han_request_preserves_answerable_visual_part(photo):
    base = recognition_response()

    def respond(role, kwargs):
        schema = getattr(kwargs.get("response_schema"), "__name__", "")
        if schema == "ExecutionPlan":
            return json.dumps(
                {
                    "selected_agents": ["visual_agent"],
                    "candidates": [{"name": NAME}],
                    "requested_slots": [
                        {
                            "slot_id": "visible",
                            "question": "Mô tả kiến trúc",
                            "evidence_type": "visual",
                        }
                    ],
                }
            )
        if schema == "EvidenceReview":
            data = json.loads(kwargs["prompt"])
            visual = next(e for e in data["evidence"] if e["kind"] == "visual")
            return json.dumps(
                {
                    "claims": [
                        {
                            "slot_id": "visible",
                            "kind": "visual",
                            "text": "Có mặt tiền nhìn thấy.",
                            "verdict": "supported",
                            "evidence_ids": [visual["evidence_id"]],
                        }
                    ],
                    "slot_assessments": [
                        {
                            "slot_id": s["slot_id"],
                            "status": "complete" if s["slot_id"] == "visible" else "unanswered",
                            "missing_information": [],
                        }
                        for s in data["requested_slots"]
                    ],
                }
            )
        return base(role, kwargs)

    result = RunService(
        FakeLLM(respond, load_config("config/hanoi-evidence.yaml")), search_engine_factory=NoSources
    ).run(photo, "Mô tả kiến trúc và đọc chữ Hán trên hoành phi")
    assert result.status == "reviewed" and result.answer_status == "partial"
    assert [s.status for s in result.slot_results] == ["answered", "unsupported"]
    assert result.slot_results[1].reason_codes == ["unsupported_request"]
    assert "Có mặt tiền" in result.final_response
    assert "có thể là" not in result.final_response  # No unsolicited identity answer.


def test_pure_han_request_remains_out_of_scope_without_model_calls(photo):
    result = service().run(photo, "Đọc chữ Hán trên hoành phi")
    assert result.answer_status == "out_of_scope" and not result.calls
    assert result.slot_results[0].status == "unsupported"


@pytest.mark.parametrize(
    "context", [{"answer": "Tôi không biết"}, {"answer": "", "response_type": "unknown"}]
)
def test_unknown_clarification_does_not_confirm_identity_or_repeat_question(photo, context):
    runner = RunService(
        FakeLLM(ambiguous, load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=HistorySearch,
    )
    parent = runner.run(photo, "Nhận diện và lịch sử?")
    assert parent.clarification
    child = list(runner.continue_stream(photo, parent, {**context, "rounds": 1}))[-1].result
    assert not child.plan["identity_resolved"] and child.clarification is None
    assert child.answer_status != "answered"
    assert parent.clarification  # Parent is immutable.


def test_unknown_detection_is_exact_and_configurable():
    policy = load_config("config/hanoi-evidence.yaml").accuracy.questions
    assert not response_is_unknown({"answer": "Không biết tên nhưng ảnh chụp ở Mỹ Đức"}, policy)
    changed = policy.model_copy(update={"unknown_answers": ["chưa có thông tin"]})
    assert response_is_unknown({"answer": "Chưa có thông tin"}, changed)


def test_unknown_api_terminal_event_and_result_have_the_same_slot_contract(
    settings, photo, monkeypatch
):
    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as client:
        auth = identity(client)
        created = client.post(
            "/api/v1/runs",
            headers=auth,
            json={"asset_id": upload(client, auth, photo), "question": "Identify"},
        )
        base = "/api/v1/runs/" + created.json()["run_id"]
        assert Worker(client.app.state.runtime).process_one()
        parent = client.get(base + "/result", headers=auth).json()
        pending = parent["clarification"]
        body = {
            "clarification_id": pending["clarification_id"],
            "revision": pending["revision"],
            "response_type": "unknown",
        }
        headers = {**auth, "Idempotency-Key": "unknown-response"}
        assert (
            client.post(
                base + "/clarification",
                headers=headers,
                json={**body, "selected_candidate": "DEMO"},
            ).status_code
            == 422
        )
        response = client.post(base + "/clarification", headers=headers, json=body)
        assert response.status_code == 202, response.text
        child_base = "/api/v1/runs/" + response.json()["run_id"]
        assert Worker(client.app.state.runtime).process_one()
        result = client.get(child_base + "/result", headers=auth).json()
        evidence = client.get(child_base + "/evidence", headers=auth).json()
        events = client.get(child_base + "/events/history", headers=auth).json()["items"]
        terminal = next(e["data"] for e in events if e["event"] == "run.succeeded")
        assert terminal["slot_results"] == result["slot_results"] == evidence["slot_results"]
        assert terminal["answer_status"] == result["answer_status"]
        assert result["clarification"] is None and result["slot_results"]
        assert client.get(base + "/result", headers=auth).json() == parent


def test_verifier_failure_exposes_technical_reason_per_slot(photo):
    def fail(role, kwargs):
        if role == "judge":
            return "not JSON"
        return recognition_response()(role, kwargs)

    result = RunService(FakeLLM(fail, load_config("config/hanoi-evidence.yaml"))).run(
        photo, "Nhận diện"
    )
    assert result.answer_status == "verification_unavailable"
    assert result.slot_results[0].reason_codes == ["verification_unavailable"]


def test_coordinator_failure_preserves_original_question_with_technical_reason(photo):
    class RateLimited(RuntimeError):
        code = 429

    def respond(role, kwargs):
        if role == "coordinator":
            raise RateLimited("synthetic rate limit")

    result = RunService(FakeLLM(respond, load_config("config/hanoi-evidence.yaml"))).run(
        photo, "Nhận diện và mô tả?"
    )
    assert result.status == "failed" and result.answer_status == "verification_unavailable"
    assert len(result.slot_results) == 1
    assert result.slot_results[0].question == result.query
    assert result.slot_results[0].reason_codes == ["verification_unavailable"]


def test_missing_information_cannot_be_declared_complete_by_same_assessment(photo):
    base = history_response(complete=False)

    def respond(role, kwargs):
        value = base(role, kwargs)
        if getattr(kwargs.get("response_schema"), "__name__", "") == "EvidenceReview":
            value = json.loads(value)
            if "contract_repair" not in json.loads(kwargs["prompt"]):
                value["slot_assessments"][0]["status"] = "complete"
            return json.dumps(value)
        return value

    result = RunService(
        FakeLLM(respond, load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=HistorySearch,
    ).run(photo, "Khởi dựng và trùng tu khi nào?")
    assert result.slot_results[0].status == "partial" and result.answer_status == "partial"
    assert result.node_metadata["judge"]["review_diagnostics"]["attempts"][0]["contract_errors"]


def test_streamlit_unknown_checkbox_keeps_parent_and_shows_slot_results(monkeypatch):
    from api.demo import DemoSearch
    from tests.test_ui import prepared_app

    monkeypatch.setattr(
        "core.search.HeritageSearchEngine.search_heritage", DemoSearch().search_heritage
    )
    app = prepared_app(monkeypatch, FakeLLM(ambiguous, load_config("config/hanoi-evidence.yaml")))
    app.button(key="start").click().run()
    parent = app.session_state.result
    assert parent["clarification"]
    app.checkbox(key="unknown_" + parent["run_id"]).check()
    next(
        button for button in app.button if button.label == "Tiếp tục với thông tin bổ sung"
    ).click().run()
    assert not app.exception
    child = app.session_state.result
    assert child["parent_run_id"] == parent["run_id"] and child["clarification"] is None
    assert child["slot_results"] and child["answer_status"] != "answered"
    assert child["continuation_context"]["response_type"] == "unknown"
