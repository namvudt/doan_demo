"""Offline integration checks for the failures found in the six-case pilot."""

import json

from core.config import load_config
from tests.conftest import FakeLLM
from workflow.service import RunService


class SubjectSearch:
    def __init__(self):
        self.hints = []

    def search_heritage(self, monument_hint, query):
        self.hints.append(monument_hint)
        text = f"{monument_hint} thuộc quốc gia Ví Dụ."
        return {
            "status": "success",
            "error": None,
            "navigation_links": [],
            "context_text": text,
            "sources": [
                {
                    "source_id": "synthetic-country",
                    "title": monument_hint,
                    "snippet": text,
                    "url": "https://example.org/synthetic",
                    "type": "web",
                }
            ],
        }


def responder(*, broken="once", rivals=False):
    def respond(role, kwargs):
        schema = getattr(kwargs.get("response_schema"), "__name__", "")
        if schema == "ExecutionPlan":
            return json.dumps(
                {
                    "selected_agents": ["visual_agent", "knowledge_agent"],
                    "identified_monument": "Site A",
                    "candidates": [{"name": "Site A"}, {"name": "Site B"}]
                    if rivals
                    else [{"name": "Site A"}],
                    "requested_slots": [
                        {
                            "slot_id": "country",
                            "question": "Mẫu thuộc quốc gia nào?",
                            "evidence_type": "historical",
                        }
                    ],
                }
            )
        if schema == "VisualFindings":
            return json.dumps(
                {
                    "observations": [
                        {"text": "SYNTHETIC: tháp phía trái", "box": [0.1, 0.1, 0.3, 0.8]},
                        {"text": "SYNTHETIC: cổng phía phải", "box": [0.6, 0.2, 0.9, 0.8]},
                    ],
                    "candidates": ["Site B"],
                    "candidate_support": [
                        {
                            "name": "Site B",
                            "basis": "distinctive_configuration",
                            "observation_indices": [0, 1],
                        }
                    ],
                    "readability": "adequate",
                }
            )
        if schema == "OCROutput":
            return json.dumps({"readable": False, "lines": []})
        if schema == "EvidenceReview":
            data = json.loads(kwargs["prompt"])
            assessments = [{"slot_id": "country", "status": "complete", "missing_information": []}]
            if broken == "always" or (broken == "once" and "contract_repair" not in data):
                return json.dumps({"slot_assessments": assessments})
            source = next(e for e in data["evidence"] if e["kind"] == "source")
            return json.dumps(
                {
                    "claims": [
                        {
                            "slot_id": "country",
                            "kind": "historical",
                            "verdict": "supported",
                            "text": f"{(data.get('question_subject') or data['candidates'][0])['name']} thuộc quốc gia Ví Dụ.",
                            "evidence_ids": [source["evidence_id"]],
                            "quotations": [
                                {"evidence_id": source["evidence_id"], "quote": source["text"]}
                            ],
                        }
                    ],
                    "slot_assessments": assessments,
                }
            )
        return "SYNTHETIC: report"

    return respond


def test_missing_claims_gets_one_bounded_repair_and_keeps_diagnostics(photo):
    search = SubjectSearch()
    result = RunService(
        FakeLLM(responder(), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=lambda: search,
    ).run(photo, "Mẫu thuộc quốc gia nào?")
    assert result.answer_status == "answered" and result.clarification is None
    assert search.hints == ["Mẫu"]
    assert not result.plan["identity_resolved"]  # A named subject does not identify the photograph.
    attempts = result.node_metadata["judge"]["review_diagnostics"]["attempts"]
    assert attempts[0]["contract_errors"] == ["review_schema_invalid"]
    assert attempts[1]["contract_errors"] == []
    assert len([c for c in result.calls if c["agent_role"] == "judge"]) == 2


def test_repeated_invalid_verifier_is_technical_failure_not_missing_source(photo):
    result = RunService(
        FakeLLM(responder(broken="always"), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=SubjectSearch,
    ).run(photo, "Mẫu thuộc quốc gia nào?")
    assert result.answer_status == "verification_unavailable"
    assert result.judge_report["error_code"] == "invalid_verifier_response"
    assert len(result.node_metadata["judge"]["review_diagnostics"]["attempts"]) == 2
    assert len([c for c in result.calls if c["agent_role"] == "judge"]) == 2


def test_contract_repair_can_be_disabled_dynamically(photo):
    config = load_config("config/hanoi-evidence.yaml")
    config = config.model_copy(
        update={"accuracy": config.accuracy.model_copy(update={"verifier_contract_retries": 0})}
    )
    result = RunService(
        FakeLLM(responder(broken="always"), config), search_engine_factory=SubjectSearch
    ).run(photo, "Mẫu thuộc quốc gia nào?")
    assert result.answer_status == "verification_unavailable"
    assert len([c for c in result.calls if c["agent_role"] == "judge"]) == 1


def test_retrieval_waits_for_visual_and_uses_resolved_candidate(photo):
    search = SubjectSearch()
    result = RunService(
        FakeLLM(responder(broken="never", rivals=True), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=lambda: search,
    ).run(photo, "Nơi này thuộc quốc gia nào?")
    assert search.hints == ["Site B"]
    visual_end = next(
        i for i, e in enumerate(result.events) if e.node == "visual" and e.status == "completed"
    )
    knowledge_start = next(
        i for i, e in enumerate(result.events) if e.node == "knowledge" and e.status == "running"
    )
    assert visual_end < knowledge_start
    assert result.plan["identity_resolved"]


def test_review_only_keeps_question_subject_separate_from_image_identity(photo):
    runner = RunService(
        FakeLLM(responder(broken="never"), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=SubjectSearch,
    )
    parent = runner.run(photo, "Mẫu thuộc quốc gia nào?")
    assert parent.answer_status == "answered"
    reviewed = list(runner.review_stream(photo, parent))[-1].result
    assert reviewed.answer_status == "answered"
    assert reviewed.plan["question_subject"]["name"] == "Mẫu"
    assert reviewed.claims[0]["gate_errors"] == []


def test_country_claim_cannot_use_a_persons_nationality_as_geographic_proof(photo):
    class WrongRelationSearch(SubjectSearch):
        def search_heritage(self, monument_hint, query):
            found = super().search_heritage(monument_hint, query)
            text = f"Nhà tù {monument_hint} từng giam giữ những người cách mạng của Ví Dụ."
            found["sources"][0]["snippet"] = found["context_text"] = text
            return found

    result = RunService(
        FakeLLM(responder(broken="never"), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=WrongRelationSearch,
    ).run(photo, "Mẫu thuộc quốc gia nào?")
    assert result.answer_status == "insufficient_evidence"
    assert "relation_quote_mismatch" in result.claims[0]["gate_errors"]
    assert "relation_quote_mismatch" in result.slot_results[0].reason_codes
    assert result.clarification is None


def test_nearest_condition_cannot_be_replaced_by_generic_surrounding_terrain(photo):
    result = RunService(
        FakeLLM(responder(broken="never", rivals=True), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=SubjectSearch,
    ).run(photo, "Nơi gần địa danh trong ảnh nhất thuộc dạng địa hình nào?")
    assert result.answer_status == "needs_clarification"
    assert result.clarification["reason"] == "missing_evidence"
    assert result.clarification["options"] == []
    assert all(s.status != "answered" for s in result.slot_results)
    assert any("nearest_scope_required" in s.reason_codes for s in result.slot_results)


def test_nearest_clarification_uses_supplied_scope_without_repeating_question(photo):
    runner = RunService(
        FakeLLM(responder(broken="never", rivals=True), load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=SubjectSearch,
    )
    parent = runner.run(photo, "Nơi gần địa danh trong ảnh nhất thuộc dạng địa hình nào?")
    assert parent.clarification["reason"] == "missing_evidence"
    child = list(
        runner.continue_stream(
            photo, parent, {"answer": "Trong số Địa điểm A và Địa điểm B", "rounds": 1}
        )
    )[-1].result
    assert child.query == parent.query
    assert child.clarification is None
    assert child.answer_status != "answered"  # Scope is a condition, not evidence of proximity.
    assert any("Trong số" in s["question"] for s in child.requested_slots)
    reviewed = list(runner.review_stream(photo, child))[-1].result
    assert reviewed.clarification is None
    assert any("Trong số" in s["question"] for s in reviewed.requested_slots)
