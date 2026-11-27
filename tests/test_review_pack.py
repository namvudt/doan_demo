import json
from copy import deepcopy

import pytest

from core.evaluation import digest, score, validate_manifest
from scripts.export_review_pack import export_pack, finalize_pack, image_hash


def test_export_is_blind_draft_and_preserves_real_image_bytes(tmp_path):
    pack = tmp_path / "review"
    result = export_pack(pack)
    assert result == {"cases": 32, "images": 4, "gold_status": "awaiting_human_review"}
    cases = json.loads((pack / "blind/manifest.json").read_text(encoding="utf-8"))
    assert all(
        item["case_id"].startswith("case-") and "image-" in item["image_path"] for item in cases
    )
    assert all(item["annotation_status"] == "draft" and not item["reviewer"] for item in cases)
    assert all(not slot["accepted_answers"] for item in cases for slot in item["slots"])
    provenance = json.loads((pack / "operator/provenance.json").read_text(encoding="utf-8"))
    assert all(image_hash(case) == proof["image_sha256"] for case, proof in zip(cases, provenance))
    with pytest.raises(ValueError, match="requires reviewed"):
        validate_manifest(cases)
    with pytest.raises(ValueError, match="must be empty"):
        export_pack(pack)


def reviewed_cases(originals):
    cases = deepcopy(originals)
    for case in cases:
        case.update(
            annotation_status="reviewed",
            reviewer="synthetic-test-reviewer",
            reviewed_at="2026-11-16",
            image_rights="synthetic-test-only annotation",
            image_source="synthetic test review fixture",
            split="dev" if case["image_family"] in {"image-01", "image-02"} else "test",
        )
        case["sources"] = [
            {
                "source_id": "synthetic-source",
                "url": "https://example.test/source",
                "content_hash": "synthetic-hash",
            }
        ]
        for slot in case["slots"]:
            slot.update(
                answerable=True,
                accepted_answers=["synthetic accepted fact"],
                source_ids=["synthetic-source"],
            )
    return cases


def test_human_review_rebinding_and_scoring_roundtrip(tmp_path):
    pack = tmp_path / "review"
    export_pack(pack)
    original = json.loads((pack / "operator/original-cases.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="requires reviewed"):
        finalize_pack(pack, original)
    reviewed = reviewed_cases(original)
    prediction = {
        "case_id": original[0]["case_id"],
        "case_hash": digest(original[0]),
        "image_hash": image_hash(original[0]),
        "model_mode": "live",
        "result": {
            "status": "reviewed",
            "duration": 1,
            "claims": [{"claim_id": "synthetic-claim", "verdict": "supported"}],
        },
    }
    result = finalize_pack(pack, reviewed, predictions=[prediction])
    assert result["predictions_rebound"] == 1
    rebound = json.loads((pack / "reviewed/predictions.json").read_text(encoding="utf-8"))
    human = json.loads((pack / "reviewed/judgments-template.json").read_text(encoding="utf-8"))
    assert rebound[0]["original_case_hash"] == prediction["case_hash"]
    assert human[0]["reviewer"] == "" and human[0]["claims"] == {"synthetic-claim": None}
    human[0].update(
        reviewer="synthetic-human",
        reviewed_at="2026-11-16",
        claims={"synthetic-claim": True},
        slots={"identify": "correct"},
    )
    metrics = score([reviewed[0]], rebound, human)
    assert metrics["claim_precision"] == 1 and metrics["answered_slot_accuracy"] == 1


def test_changed_inputs_and_demo_predictions_cannot_be_relabelled_gold(tmp_path):
    pack = tmp_path / "review"
    export_pack(pack)
    originals = json.loads((pack / "operator/original-cases.json").read_text(encoding="utf-8"))
    reviewed = reviewed_cases(originals)
    reviewed[0]["question"] += " changed input"
    with pytest.raises(ValueError, match="Model input changed"):
        finalize_pack(pack, reviewed)
    reviewed = reviewed_cases(originals)
    demo = {
        "case_id": originals[0]["case_id"],
        "case_hash": digest(originals[0]),
        "image_hash": image_hash(originals[0]),
        "model_mode": "demo",
        "result": {},
    }
    with pytest.raises(ValueError, match="Demo predictions"):
        finalize_pack(pack, reviewed, predictions=[demo])
