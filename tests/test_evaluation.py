from copy import deepcopy

import pytest

from core.evaluation import digest, score, validate_manifest
from scripts.evaluate import ROOT, prepare, read


def case():
    return {
        "case_id": "synthetic",
        "image_path": "not-a-real-image.png",
        "image_family": "synthetic-family",
        "entity_group": "synthetic-entity",
        "question": "Visible feature?",
        "split": "dev",
        "annotation_status": "reviewed",
        "reviewer": "synthetic-test-reviewer",
        "reviewed_at": "2026-11-15",
        "image_rights": "synthetic generated test fixture",
        "image_source": "generated synthetic fixture",
        "slots": [
            {
                "slot_id": "visible",
                "question": "Feature?",
                "kind": "visual",
                "answerable": True,
                "accepted_answers": ["synthetic fixture feature"],
            },
            {
                "slot_id": "other",
                "question": "Other feature?",
                "kind": "visual",
                "answerable": True,
                "accepted_answers": ["another synthetic feature"],
            },
        ],
    }


def test_pilot_is_draft_and_references_existing_images():
    cases = validate_manifest(
        prepare(read(ROOT / "config/evaluation/hanoi-pilot.json")), allow_draft=True
    )
    assert len(cases) == 32 and all((ROOT / c.image_path).is_file() for c in cases)
    assert all(c.annotation_status == "draft" and c.image_rights == "unverified" for c in cases)
    with pytest.raises(ValueError, match="requires reviewed"):
        validate_manifest([c.model_dump() for c in cases])


def test_split_leakage_and_unversioned_historical_gold_are_rejected():
    first = case()
    second = {**deepcopy(first), "case_id": "other", "split": "test"}
    with pytest.raises(ValueError, match="must not cross"):
        validate_manifest([first, second])
    first["slots"][0]["kind"] = "historical"
    with pytest.raises(ValueError, match="versioned sources"):
        validate_manifest([first])


def test_scores_require_human_review_and_measure_refusal_separately():
    raw = case()
    validated = validate_manifest([raw])[0].model_dump(mode="json")
    prediction = {
        "case_id": "synthetic",
        "case_hash": digest(validated),
        "model_mode": "live",
        "result": {
            "status": "reviewed",
            "duration": 1.2,
            "claims": [{"claim_id": "c1", "verdict": "supported"}],
        },
    }
    human = {
        "case_id": "synthetic",
        "reviewer": "synthetic-human",
        "reviewed_at": "2026-11-15",
        "prediction_hash": digest(prediction),
        "claims": {"c1": False},
        "slots": {"visible": "incorrect", "other": "abstained"},
    }
    result = score([raw], [prediction], [human])
    assert result["claim_precision"] == 0
    assert result["answered_slot_accuracy"] == 0
    assert result["answerable_slot_coverage"] == result["false_refusal_rate"] == 0.5
    with pytest.raises(ValueError, match="Demo outputs"):
        score([raw], [{**prediction, "model_mode": "demo"}], [human])
    with pytest.raises(ValueError, match="missing or stale"):
        score([raw], [prediction], [{**human, "prediction_hash": "old"}])
    with pytest.raises(ValueError, match="correctness label"):
        score([raw], [prediction], [{**human, "claims": {}}])
    prediction["result"]["recognition"] = {"status": "probable"}
    human["prediction_hash"] = digest(prediction)
    with pytest.raises(ValueError, match="recognition requires"):
        score([raw], [prediction], [human])
    result = score([raw], [prediction], [{**human, "recognition_correct": False}])
    assert result["recognition_precision"] == 0 and result["judged_recognitions"] == 1
