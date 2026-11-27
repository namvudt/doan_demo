import copy

import pytest

from core.config import load_config
from core.evidence import (
    EvidenceReview,
    NamedBox,
    VisualFindings,
    annotate_count_grounding,
    check_claims,
    parse_visual_findings,
)

SLOTS = [{"slot_id": "count", "question": "How many flagpoles?", "evidence_type": "visual"}]


def findings():
    boxes = [[0.1, 0.1, 0.13, 0.4], [0.7, 0.1, 0.73, 0.4]]
    return {
        "observations": [
            {"text": "A vertical flagpole on the left", "box": boxes[0]},
            {"text": "A vertical flagpole on the right", "box": boxes[1]},
        ],
        "count_findings": [
            {
                "slot_id": "count",
                "object_class": "flagpole",
                "count": 2,
                "instances": [
                    {
                        "observation_index": i,
                        "object_class": "flagpole",
                        "classification": "confirmed",
                        "box": dict(zip(("x_min", "y_min", "x_max", "y_max"), box)),
                    }
                    for i, box in enumerate(boxes)
                ],
            }
        ],
    }


def check(raw, text="There are 2 flagpoles.", refs=None, prefix=()):
    parsed, warnings = parse_visual_findings(raw)
    evidence = [
        *prefix,
        *[
            {
                "evidence_id": f"visual_{i}",
                "kind": "visual",
                "text": obs.text,
                "box": obs.box,
                "version": "image",
            }
            for i, obs in enumerate(parsed.observations)
        ],
    ]
    annotated, more_warnings = annotate_count_grounding(parsed, evidence, SLOTS)
    review = EvidenceReview(
        claims=[
            {
                "slot_id": "count",
                "text": text,
                "kind": "visual",
                "verdict": "supported",
                "evidence_ids": refs if refs is not None else ["visual_0", "visual_1"],
            }
        ],
        slot_assessments=[{"slot_id": "count", "status": "complete"}],
    )
    checked = check_claims(
        review,
        annotated,
        SLOTS,
        load_config().accuracy,
        identity_resolved=False,
        require_count_grounding=True,
    )
    return checked[0], [*warnings, *more_warnings], annotated


def test_distinct_confirmed_instances_support_count_without_identity_confirmation():
    claim, warnings, _ = check(findings())
    assert claim["verdict"] == "supported"
    assert not claim["gate_errors"] and not warnings


def test_named_box_rejects_inverted_coordinates():
    with pytest.raises(ValueError):
        NamedBox(x_min=0.9, y_min=0.1, x_max=0.5, y_max=0.4)


def test_count_schema_requires_instance_inventory_and_named_coordinate_fields():
    definitions = VisualFindings.model_json_schema()["$defs"]
    assert set(definitions["CountFinding"]["required"]) == {
        "slot_id",
        "object_class",
        "count",
        "instances",
    }
    assert set(definitions["CountInstance"]["required"]) == {
        "observation_index",
        "object_class",
        "classification",
    }
    assert set(definitions["NamedBox"]["required"]) == {"x_min", "y_min", "x_max", "y_max"}


def test_swapped_legacy_boxes_are_flagged_and_never_automatically_transposed():
    raw = findings()
    swapped = [0.1, 0.8, 0.4, 0.83]
    raw["observations"][1]["box"] = swapped
    raw["count_findings"][0]["instances"][1]["box"] = swapped
    claim, warnings, evidence = check(raw)
    assert claim["verdict"] == "insufficient"
    assert "suspected_axis_swap" in claim["gate_errors"]
    assert any(item["code"] == "suspected_axis_swap" for item in warnings)
    assert evidence[1]["box"] == swapped


def test_legacy_instance_tuple_is_interpreted_as_xyxy_only():
    raw = findings()
    raw["count_findings"][0]["instances"][0]["box"] = tuple(raw["observations"][0]["box"])
    claim, _, _ = check(raw)
    assert claim["verdict"] == "supported"


def test_invalid_raw_box_is_visible_and_cannot_support_count():
    raw = findings()
    raw["observations"][0]["box"] = [10, 20, 30, 40]
    claim, warnings, _ = check(raw)
    assert claim["verdict"] == "insufficient"
    assert any(item["code"] == "invalid_box_discarded" for item in warnings)


def test_invalid_named_instance_box_is_discarded_without_poisoning_observation():
    raw = findings()
    raw["count_findings"][0]["instances"][0]["box"]["x_max"] = 1.5
    claim, warnings, evidence = check(raw)
    assert claim["verdict"] == "insufficient"
    assert evidence[0]["box"] == raw["observations"][0]["box"]
    assert any(item["code"] == "invalid_count_box_discarded" for item in warnings)


def test_rods_of_unknown_class_do_not_become_confirmed_flagpoles():
    raw = findings()
    raw["count_findings"][0]["instances"][1]["classification"] = "uncertain"
    claim, _, _ = check(raw)
    assert claim["verdict"] == "insufficient"
    assert "object_class_uncertain" in claim["gate_errors"]


def test_wrong_object_class_does_not_support_the_requested_count():
    raw = findings()
    for item in raw["count_findings"][0]["instances"]:
        item["object_class"] = "lightning rod"
    claim, _, _ = check(raw)
    assert "count_object_class_mismatch" in claim["gate_errors"]


def test_generic_class_substring_is_not_the_requested_object_class():
    raw = findings()
    raw["count_findings"][0]["object_class"] = "pole"
    for instance in raw["count_findings"][0]["instances"]:
        instance["object_class"] = "pole"
    claim, _, _ = check(raw)
    assert "count_object_class_mismatch" in claim["gate_errors"]


def test_duplicate_observation_cannot_be_counted_twice():
    raw = findings()
    raw["count_findings"][0]["instances"][1] = copy.deepcopy(
        raw["count_findings"][0]["instances"][0]
    )
    claim, _, _ = check(raw)
    assert claim["verdict"] == "insufficient"
    assert "duplicate_count_instance" in claim["gate_errors"]


def test_declared_total_requires_all_registered_instances_in_claim():
    claim, _, _ = check(findings(), refs=["visual_0"])
    assert claim["verdict"] == "insufficient"
    assert "count_instance_total_mismatch" in claim["gate_errors"]


def test_answer_cannot_change_the_declared_count():
    claim, _, _ = check(findings(), text="There is 1 flagpole.")
    assert claim["verdict"] == "insufficient"
    assert "count_value_unverifiable" in claim["gate_errors"]


def test_legacy_visual_evidence_without_instance_inventory_is_not_enough():
    raw = findings()
    raw.pop("count_findings")
    claim, _, _ = check(raw)
    assert claim["verdict"] == "insufficient"
    assert "count_grounding_missing" in claim["gate_errors"]


def test_zero_count_requires_more_than_an_empty_instance_list():
    raw = findings()
    raw["count_findings"][0].update(count=0, instances=[])
    claim, _, _ = check(raw, text="There are zero flagpoles.")
    assert claim["verdict"] == "insufficient"
    assert "count_grounding_missing" in claim["gate_errors"]


def test_duplicate_count_findings_cannot_silently_override_a_total():
    raw = findings()
    raw["count_findings"].append(copy.deepcopy(raw["count_findings"][0]))
    claim, _, _ = check(raw)
    assert claim["verdict"] == "insufficient"
    assert "duplicate_count_finding" in claim["gate_errors"]


def test_source_and_ocr_rows_cannot_shift_observation_indices():
    prefix = [{"evidence_id": "ocr", "kind": "ocr", "text": "A sign", "version": "image"}]
    claim, _, evidence = check(findings(), prefix=prefix)
    assert claim["verdict"] == "supported"
    assert evidence[0]["count_grounding"] == []
    assert evidence[1]["count_grounding"][0]["instance_index"] == 0


def test_missing_observation_invalidates_the_remaining_count_records():
    raw = findings()
    raw["count_findings"][0]["instances"][1]["observation_index"] = 19
    claim, warnings, _ = check(raw)
    assert claim["verdict"] == "insufficient"
    assert "count_observation_missing" in claim["gate_errors"]
    assert any(item["code"] == "count_observation_missing" for item in warnings)


def test_additional_per_instance_numbers_do_not_change_the_answer_count():
    claim, _, _ = check(findings(), text="There are two flagpoles, one on each side.")
    assert claim["verdict"] == "supported"


def test_vietnamese_count_and_geometry_rules_use_accents_correctly():
    from core.evidence import geometry_issues, is_count_question

    assert is_count_question("Trong hình có bao nhiêu cột?")
    assert geometry_issues("Một cột thẳng đứng bên phải", [0.1, 0.8, 0.3, 0.81]) == [
        "suspected_axis_swap"
    ]
    raw = findings()
    raw["count_findings"][0]["object_class"] = "flagpole"
    claim, _, _ = check(raw, text="Có hai flagpoles, một ở mỗi phía.")
    assert claim["verdict"] == "supported"


def test_spelled_number_fallback_requires_an_actual_count():
    claim, _, _ = check(findings(), text="Các flagpoles nằm trên mái.")
    assert claim["verdict"] == "insufficient"
    assert "count_value_unverifiable" in claim["gate_errors"]


@pytest.mark.parametrize("count,words", [(12, "mười hai"), (20, "hai mươi")])
def test_vietnamese_multiword_numbers_match_the_registered_total(count, words):
    raw = findings()
    raw["observations"] = []
    raw["count_findings"][0].update(count=count, instances=[])
    for index in range(count):
        x = 0.02 + index * 0.047
        box = [x, 0.1, x + 0.02, 0.4]
        raw["observations"].append({"text": "A vertical flagpole", "box": box})
        raw["count_findings"][0]["instances"].append(
            {
                "observation_index": index,
                "object_class": "flagpole",
                "classification": "confirmed",
                "box": dict(zip(("x_min", "y_min", "x_max", "y_max"), box)),
            }
        )
    claim, _, _ = check(
        raw, text=f"Có {words} flagpoles.", refs=[f"visual_{i}" for i in range(count)]
    )
    assert claim["verdict"] == "supported"


def test_null_box_on_non_count_observation_is_not_a_count_error():
    parsed, _ = parse_visual_findings(
        {"observations": [{"text": "A yellow building", "box": None}]}
    )
    evidence = [
        {"evidence_id": "v", "kind": "visual", "text": "A yellow building", "version": "image"}
    ]
    annotated, warnings = annotate_count_grounding(parsed, evidence, [])
    assert not annotated[0].get("grounding_errors")
    assert not warnings


def test_non_count_claim_with_contradictory_grounding_is_not_supported():
    parsed, _ = parse_visual_findings(
        {"observations": [{"text": "A vertical pole on the right", "box": [0.1, 0.8, 0.3, 0.81]}]}
    )
    evidence = [
        {
            "evidence_id": "v",
            "kind": "visual",
            "text": parsed.observations[0].text,
            "box": parsed.observations[0].box,
            "version": "image",
        }
    ]
    annotated, _ = annotate_count_grounding(parsed, evidence, [])
    slots = [{"slot_id": "position", "question": "Where is the pole?", "evidence_type": "visual"}]
    review = EvidenceReview(
        claims=[
            {
                "slot_id": "position",
                "text": "It is on the right",
                "kind": "visual",
                "verdict": "supported",
                "evidence_ids": ["v"],
            }
        ],
        slot_assessments=[{"slot_id": "position", "status": "complete"}],
    )
    claim = check_claims(review, annotated, slots, load_config().accuracy, identity_resolved=False)[
        0
    ]
    assert claim["verdict"] == "insufficient"
    assert "suspected_axis_swap" in claim["gate_errors"]
