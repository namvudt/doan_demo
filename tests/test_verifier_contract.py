import pytest
from pydantic import ValidationError

from core.coverage import slot_results
from core.evidence import EvidenceReview, validate_review_contract

SLOTS = [{"slot_id": "color", "question": "What color?", "evidence_type": "visual"}]


def test_wire_contract_requires_claims_and_assessments():
    for response in ({}, {"claims": []}, {"slot_assessments": []}):
        with pytest.raises(ValidationError):
            EvidenceReview.model_validate(response)


def test_complete_without_claim_is_a_contract_error():
    review = EvidenceReview(
        claims=[], slot_assessments=[{"slot_id": "color", "status": "complete"}]
    )
    assert validate_review_contract(review, SLOTS) == ["complete_without_supported_claim:color"]
    result = slot_results(SLOTS, [], [], review.slot_assessments)[0]
    assert result["status"] == "unanswered"
    assert "invalid_verifier_response" in result["reason_codes"]


def test_identity_complete_can_use_separate_recognition():
    slots = [{"slot_id": "name", "question": "Which building?", "evidence_type": "identity"}]
    review = EvidenceReview(
        claims=[],
        recognition={"status": "probable", "entity_id": "building"},
        slot_assessments=[{"slot_id": "name", "status": "complete"}],
    )
    assert validate_review_contract(review, slots) == []


def test_unknown_duplicate_and_missing_slots_are_not_silently_accepted():
    review = EvidenceReview(
        claims=[{"slot_id": "fake", "text": "Blue", "kind": "visual", "verdict": "supported"}],
        slot_assessments=[
            {"slot_id": "fake", "status": "unanswered"},
            {"slot_id": "fake", "status": "partial"},
        ],
    )
    assert set(validate_review_contract(review, SLOTS)) == {
        "unknown_claim_slot:fake",
        "unknown_assessment_slot:fake",
        "duplicate_assessment_slot:fake",
        "missing_assessment_slot:color",
    }


def test_complete_with_missing_information_is_not_complete():
    review = EvidenceReview(
        claims=[{"slot_id": "color", "text": "Blue", "kind": "visual", "verdict": "supported"}],
        slot_assessments=[
            {"slot_id": "color", "status": "complete", "missing_information": ["Side wall hidden"]}
        ],
    )
    assert validate_review_contract(review, SLOTS) == ["complete_with_missing_information:color"]


@pytest.mark.parametrize(
    "has_source,reason", [(False, "no_retrieved_sources"), (True, "no_supporting_source")]
)
def test_missing_retrieval_differs_from_no_supporting_source(has_source, reason):
    slots = [{"slot_id": "history", "question": "When built?", "evidence_type": "historical"}]
    evidence = [{"evidence_id": "source", "kind": "source"}] if has_source else []
    review = EvidenceReview(
        claims=[], slot_assessments=[{"slot_id": "history", "status": "unanswered"}]
    )
    result = slot_results(slots, [], evidence, review.slot_assessments)[0]
    assert reason in result["reason_codes"]
    assert "missing_source" in result["reason_codes"]  # Retains existing client compatibility.


def test_duplicate_assessment_never_reports_a_fully_answered_slot():
    review = EvidenceReview(
        claims=[], slot_assessments=[{"slot_id": "color", "status": "complete"}] * 2
    )
    claims = [
        {
            "slot_id": "color",
            "verdict": "supported",
            "text": "Blue",
            "claim_id": "c",
            "evidence_ids": ["v"],
        }
    ]
    result = slot_results(SLOTS, claims, [], review.slot_assessments)[0]
    assert result["status"] == "partial"
    assert "invalid_verifier_response" in result["reason_codes"]
