"""Synthetic recognition contracts, not a benchmark of heritage identification accuracy."""

import json

import pytest

from core.config import RecognitionPolicy, load_config
from core.entities import EntityCatalog
from core.evidence import RecognitionAssessment, VisualFindings
from core.recognition import candidate_support, check_recognition
from tests.conftest import FakeLLM
from workflow.service import RunService

NAME = "Chùa Thiên Trù"
ENTITY = "hanoi:chua-thien-tru"


def recognition_response(
    *,
    basis="distinctive_configuration",
    rivals=False,
    history=False,
    omit_review=False,
    unreadable=False,
    contradiction=False,
):
    def respond(role, kwargs):
        schema = getattr(kwargs.get("response_schema"), "__name__", "")
        if schema == "ExecutionPlan":
            return json.dumps(
                {
                    "selected_agents": ["visual_agent"],
                    "candidates": [{"name": NAME}],
                    # Deliberately stronger than the original tentative query.
                    "requested_slots": [
                        {
                            "slot_id": "identity",
                            "question": "Đây chính xác là công trình nào?",
                            "evidence_type": "identity",
                        },
                        *(
                            [
                                {
                                    "slot_id": "history",
                                    "question": "Năm khởi dựng?",
                                    "evidence_type": "historical",
                                }
                            ]
                            if history
                            else []
                        ),
                    ],
                }
            )
        if schema == "VisualFindings":
            # An external label must not leak into independent perception.
            assert "Gợi ý địa điểm" not in kwargs["prompt"]
            return json.dumps(
                {
                    "observations": [
                        {"text": "SYNTHETIC: bố cục mặt tiền nhìn thấy.", "box": [0, 0, 0.5, 1]},
                        {"text": "SYNTHETIC: tổ hợp các tầng mái và sân nhìn thấy."},
                    ],
                    "candidates": [NAME, *(["Chùa Một Cột"] if rivals else [])],
                    "candidate_support": [
                        {"name": NAME, "basis": basis, "observation_indices": [0, 1]}
                    ],
                    "readability": "unreadable" if unreadable else "adequate",
                }
            )
        if schema == "EvidenceReview":
            data = json.loads(kwargs["prompt"])
            assert data["query"] == data["original_question"]
            visual = [e["evidence_id"] for e in data["evidence"] if e["kind"] == "visual"]
            result = {
                "claims": [
                    {
                        "slot_id": "identity",
                        "kind": "identity",
                        "text": "Khẳng định tuyệt đối tên di tích",
                        "verdict": "contradicted" if contradiction else "insufficient",
                        "evidence_ids": visual,
                        "explanation": "Không xác nhận tuyệt đối bằng biển tên.",
                    }
                ]
            }
            if not omit_review:
                result["recognition"] = {
                    "status": "probable",
                    "entity_id": ENTITY,
                    "evidence_ids": visual,
                    "explanation": "SYNTHETIC: tổ hợp quan sát hỗ trợ nhận diện có điều kiện.",
                }
            return json.dumps(result)

    return respond


class NoSources:
    def search_heritage(self, **kwargs):
        return {"status": "empty", "sources": [], "context_text": "", "navigation_links": []}


def service(**kwargs):
    return RunService(
        FakeLLM(recognition_response(**kwargs), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=NoSources,
    )


def test_tentative_identity_is_answered_without_ocr_or_absolute_claim(photo):
    result = service().run(photo, "Đây có thể là công trình nào?")
    assert result.recognition.status == "probable"
    assert result.recognition.name == NAME
    assert len(result.recognition.evidence_ids) == 2
    assert result.answer_status == "answered" and result.clarification is None
    assert "có thể là" in result.final_response
    assert "Chưa đủ căn cứ" not in result.final_response
    assert "Khẳng định tuyệt đối" not in result.final_response
    assert result.claims[0]["verdict"] == "insufficient"  # Original verdict remains auditable.
    assert not any(e["kind"] == "ocr" for e in result.evidence)
    judge = next(e for e in result.events if e.node == "judge" and e.status == "completed")
    assert judge.payload["recognition"]["status"] == "probable"


def test_explicit_certainty_request_keeps_the_recognition_limit(photo):
    result = service().run(photo, "Hãy xác nhận chắc chắn danh tính công trình.")
    assert result.recognition.status == "probable"
    assert result.answer_status == "partial"
    assert "Chưa đủ căn cứ" in result.final_response and result.clarification is None


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"basis": "generic_appearance"}, "unrecognized"),
        ({"rivals": True}, "ambiguous"),
        ({"contradiction": True}, "unrecognized"),
    ],
)
def test_generic_rival_or_contradicted_identity_is_not_promoted(photo, kwargs, expected):
    result = service(**kwargs).run(photo, "Đây có thể là công trình nào?")
    assert result.recognition.status == expected
    assert result.answer_status == "needs_clarification"
    assert "có thể là Chùa Thiên Trù" not in result.final_response


def test_missing_protocol_is_not_a_request_for_user_confirmation(photo):
    result = service(omit_review=True).run(photo, "Nhận diện công trình")
    assert result.recognition.gate_errors == ["recognition_assessment_missing"]
    assert result.answer_status == "insufficient_evidence" and result.clarification is None


def test_unreadable_image_cannot_be_promoted_by_a_model_proposal(photo):
    result = service(unreadable=True).run(photo, "Nhận diện")
    assert result.recognition.status == "unrecognized"
    assert result.recognition.gate_errors == ["recognition_image_unreadable"]
    assert result.clarification["reason"] == "image_unreadable"


def test_missing_history_does_not_repeat_identity_confirmation(photo):
    result = service(history=True).run(photo, "Nhận diện và năm khởi dựng?")
    assert result.recognition.status == "probable"
    assert result.answer_status == "partial" and result.clarification is None
    assert "Năm khởi dựng?" in result.final_response
    assert all(c["kind"] != "historical" for c in result.claims)


def test_hint_is_unverified_bound_to_result_and_changes_fingerprint(photo):
    runner = service(basis="generic_appearance")
    blind = runner.run(photo, "Nhận diện")
    hinted = runner.run(
        photo, "Nhận diện", location_hint={"name": "Chùa Hương", "provenance": "sample_label"}
    )
    assert hinted.recognition.status == "unrecognized"  # The label cannot create image support.
    assert hinted.location_hint.provenance == "sample_label"
    assert hinted.fingerprint != blind.fingerprint
    assert hinted.answer_status == "insufficient_evidence" and not hinted.clarification


@pytest.mark.parametrize(
    "mutation,error",
    [
        ({"evidence_ids": ["fake", "image_b"]}, "recognition_image_evidence_required"),
        ({"evidence_ids": ["image_a", "source"]}, "recognition_image_evidence_required"),
        ({"evidence_ids": ["image_a", "image_a"]}, "recognition_observations_insufficient"),
        ({"entity_id": "wrong"}, "recognition_candidate_unresolved"),
    ],
)
def test_recognition_gate_rejects_unregistered_source_duplicate_and_wrong_entity(mutation, error):
    evidence = [
        {"evidence_id": "image_a", "kind": "visual"},
        {"evidence_id": "image_b", "kind": "visual"},
        {"evidence_id": "source", "kind": "source"},
    ]
    support = [
        {
            "entity_id": ENTITY,
            "basis": "distinctive_configuration",
            "evidence_ids": ["image_a", "image_b"],
        }
    ]
    assessment = RecognitionAssessment.model_validate(
        {
            "status": "recognized",
            "entity_id": ENTITY,
            "evidence_ids": ["image_a", "image_b"],
            **mutation,
        }
    )
    result = check_recognition(
        assessment,
        [{"entity_id": ENTITY, "name": NAME}],
        support,
        evidence,
        RecognitionPolicy(),
        identity_resolved=True,
    )
    assert result["status"] == "unrecognized" and error in result["gate_errors"]


def test_recognition_cap_and_empty_or_out_of_range_support():
    findings = VisualFindings.model_validate(
        {
            "candidate_support": [
                {"name": " ", "observation_indices": [0], "basis": "readable_name"},
                {"name": NAME, "observation_indices": [19], "basis": "distinctive_configuration"},
            ]
        }
    )
    rows = candidate_support(findings, [], EntityCatalog())
    assert len(rows) == 1 and not rows[0]["evidence_ids"]
    rows[0]["evidence_ids"] = ["a", "b"]
    result = check_recognition(
        RecognitionAssessment(status="recognized", entity_id=ENTITY, evidence_ids=["a", "b"]),
        [{"entity_id": ENTITY, "name": NAME}],
        rows,
        [{"evidence_id": key, "kind": "visual"} for key in ("a", "b")],
        RecognitionPolicy(),
        identity_resolved=True,
    )
    assert result["status"] == "probable" and result["assessment"]["status"] == "recognized"


def test_ui_guided_mode_is_explicit_and_invalidates_blind_result(monkeypatch):
    from tests.test_ui import prepared_app

    app = prepared_app(monkeypatch, service().llm)
    assert not app.checkbox(key="guided_sample").value
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state.result["recognition"]["status"] == "probable"
    assert app.session_state.result["location_hint"] is None
    app.checkbox(key="guided_sample").check().run()
    assert "result" not in app.session_state
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state.result["location_hint"] == {
        "name": "Chùa Một Cột",
        "provenance": "sample_label",
    }
    assert any("Nhận diện có cơ sở" in m.value for m in app.markdown)


def test_old_results_remain_readable(photo):
    from core.schemas import RunResult

    result = service().run(photo, "Nhận diện").model_dump()
    result.pop("recognition")
    result.pop("location_hint")
    previous = RunResult.model_validate(result)
    assert previous.recognition is None and previous.location_hint is None


def test_han_filter_remaps_candidate_indices_before_registering_ids(photo):
    base = recognition_response()

    def respond(role, kwargs):
        value = base(role, kwargs)
        if getattr(kwargs.get("response_schema"), "__name__", "") == "VisualFindings":
            value = json.loads(value)
            value["observations"].insert(0, {"text": "香天寶剎"})
            value["candidate_support"][0]["observation_indices"] = [1, 2]
            return json.dumps(value)
        return value

    result = RunService(FakeLLM(respond, load_config("config/hanoi-evidence.yaml"))).run(
        photo, "Nhận diện"
    )
    assert result.recognition.status == "probable"
    assert len(result.recognition.evidence_ids) == 2
    assert all("香" not in e["text"] for e in result.evidence)
    assert result.expert_results["visual"]["meta"]["omitted_observations"]


def test_review_keeps_hint_and_recognition_without_rerunning_perception(photo):
    runner = service()
    parent = runner.run(photo, "Nhận diện", location_hint={"name": "Chùa Hương"})
    reviewed = list(runner.review_stream(photo, parent))[-1].result
    assert reviewed.recognition == parent.recognition
    assert reviewed.location_hint == parent.location_hint
    assert len(reviewed.calls) == 1


def test_continuation_hint_is_bound_to_original_image(photo):
    from PIL import Image

    from core.images import image_bytes

    runner = service(unreadable=True)
    parent = runner.run(
        photo, "Nhận diện", location_hint={"name": "Chùa Hương", "provenance": "sample_label"}
    )
    assert parent.clarification
    same = list(runner.continue_stream(photo, parent, {"answer": "", "rounds": 1}))[-1].result
    assert same.location_hint == parent.location_hint and "visual" in same.reused_nodes
    other_image = image_bytes(Image.new("RGB", (50, 40), "blue"))
    other = list(runner.continue_stream(other_image, parent, {"answer": "", "rounds": 1}))[
        -1
    ].result
    assert other.location_hint is None and "visual" not in other.reused_nodes


def test_recognition_explanations_do_not_bypass_material_date_or_han_policy(photo):
    base = recognition_response()

    def respond(role, kwargs):
        value = base(role, kwargs)
        schema = getattr(kwargs.get("response_schema"), "__name__", "")
        if schema == "VisualFindings":
            value = json.loads(value)
            value["candidate_support"][0]["explanation"] = "Bảng ghi 香天寶剎 và gỗ lim."
            return json.dumps(value)
        if schema == "EvidenceReview":
            value = json.loads(value)
            value["recognition"]["explanation"] = "Khởi dựng năm 1467, núi đá vôi và gỗ lim."
            return json.dumps(value)
        return value

    result = RunService(FakeLLM(respond, load_config("config/hanoi-evidence.yaml"))).run(
        photo, "Nhận diện"
    )
    payload = json.dumps(result.recognition.model_dump(), ensure_ascii=False)
    assert result.recognition.status == "probable"
    assert all(term not in payload for term in ("香", "gỗ lim", "1467", "đá vôi"))


@pytest.mark.parametrize(
    "coordinator_names,expected",
    [
        (["Chùa Hương"], "probable"),
        ([NAME, "Chùa Một Cột"], "probable"),
        (["Chùa Một Cột"], "ambiguous"),
    ],
)
def test_independent_visual_selection_respects_site_component_and_rejects_unrelated_agreement(
    photo, coordinator_names, expected
):
    base = recognition_response()

    def respond(role, kwargs):
        value = base(role, kwargs)
        if getattr(kwargs.get("response_schema"), "__name__", "") == "ExecutionPlan":
            value = json.loads(value)
            value["candidates"] = [{"name": name} for name in coordinator_names]
            return json.dumps(value)
        return value

    result = RunService(FakeLLM(respond, load_config("config/hanoi-evidence.yaml"))).run(
        photo, "Nhận diện"
    )
    assert result.recognition.status == expected
    if expected == "probable":
        assert result.recognition.name == NAME and result.answer_status == "answered"
    else:
        assert result.clarification
