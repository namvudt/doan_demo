"""Human-reviewed evaluation, separate from model self-verdicts and software tests."""

import hashlib
import json
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExpectedSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: str
    question: str
    kind: Literal["visual", "historical", "identity", "mixed"]
    answerable: bool | None = None
    accepted_answers: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    image_path: str
    image_family: str
    entity_group: str
    degradation: str = "original"
    question: str
    split: Literal["draft", "dev", "test"] = "draft"
    annotation_status: Literal["draft", "reviewed"] = "draft"
    reviewer: str | None = None
    reviewed_at: str | None = None
    image_rights: str = "unverified"
    image_source: str | None = None
    sources: list[dict] = Field(default_factory=list)
    slots: list[ExpectedSlot]

    @model_validator(mode="after")
    def reviewed_contract(self):
        if not self.slots or len({s.slot_id for s in self.slots}) != len(self.slots):
            raise ValueError("Slots must be non-empty and unique")
        if self.annotation_status == "reviewed":
            if (
                not self.reviewer
                or not self.reviewed_at
                or not self.image_source
                or self.image_rights == "unverified"
            ):
                raise ValueError("Reviewed cases require reviewer, date and image rights")
            registered = {
                s.get("source_id") for s in self.sources if s.get("content_hash") and s.get("url")
            }
            for slot in self.slots:
                if slot.answerable is None or (slot.answerable and not slot.accepted_answers):
                    raise ValueError("Reviewed slots require answerability and accepted facts")
                if slot.answerable and slot.kind in {"historical", "mixed"}:
                    if not slot.source_ids or not set(slot.source_ids) <= registered:
                        raise ValueError("Historical gold requires versioned sources")
        return self


def validate_manifest(items, *, allow_draft=False):
    cases = [EvaluationCase.model_validate(item) for item in items]
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Manifest must have unique non-empty cases")
    if not allow_draft and any(
        c.annotation_status != "reviewed" or c.split == "draft" for c in cases
    ):
        raise ValueError("Quality evaluation requires reviewed dev/test cases")
    groups = defaultdict(set)
    for case in cases:
        if case.split != "draft":
            for key in ("image_family", "entity_group"):
                groups[(key, getattr(case, key))].add(case.split)
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("Related image families/entities must not cross dev/test splits")
    return cases


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def score(cases, predictions, judgments):
    """Require human verdicts for every displayed claim and slot; model verdicts are not truth."""
    cases = validate_manifest(cases)
    predicted = {p["case_id"]: p for p in predictions}
    judged = {j["case_id"]: j for j in judgments}
    wanted = {c.case_id for c in cases}
    if (
        set(predicted) != wanted
        or set(judged) != wanted
        or len(predictions) != len(wanted)
        or len(judgments) != len(wanted)
    ):
        raise ValueError("Every case requires exactly one prediction and human judgment")
    correct_claims = claims = answered = correct_slots = answerable = answered_answerable = (
        false_refusals
    ) = 0
    technical_failures = evaluable_answerable = 0
    judged_recognitions = correct_recognitions = 0
    durations = []
    for case in cases:
        prediction, judgment = predicted[case.case_id], judged[case.case_id]
        if prediction.get("model_mode") != "live":
            raise ValueError("Demo outputs cannot be used for quality scores")
        if prediction.get("case_hash") != digest(case.model_dump(mode="json")):
            raise ValueError("Case changed after prediction")
        if (
            not judgment.get("reviewer")
            or not judgment.get("reviewed_at")
            or judgment.get("prediction_hash") != digest(prediction)
        ):
            raise ValueError("Human judgment missing or stale")
        result = prediction["result"]
        recognition = result.get("recognition") or {}
        if recognition.get("status") in {"probable", "recognized"}:
            recognition_correct = judgment.get("recognition_correct")
            if type(recognition_correct) is not bool:
                raise ValueError("Displayed recognition requires a human correctness label")
            judged_recognitions += 1
            correct_recognitions += recognition_correct
        failed = result.get("status") in {"failed", "unverified"}
        expected_claims = {
            c["claim_id"] for c in result.get("claims", []) if c["verdict"] == "supported"
        }
        verdicts = judgment.get("claims", {})
        if set(verdicts) != expected_claims or any(type(v) is not bool for v in verdicts.values()):
            raise ValueError("Every displayed supported claim requires a human correctness label")
        slots = judgment.get("slots", {})
        if set(slots) != {s.slot_id for s in case.slots}:
            raise ValueError("Every expected slot requires a human verdict")
        for slot in case.slots:
            verdict = slots[slot.slot_id]
            if verdict not in {"correct", "incorrect", "abstained"}:
                raise ValueError("Invalid slot verdict")
            did_answer = verdict != "abstained"
            answered += did_answer
            correct_slots += verdict == "correct"
            answerable += slot.answerable
            answered_answerable += bool(slot.answerable and did_answer)
            evaluable_answerable += bool(slot.answerable and not failed)
            false_refusals += bool(slot.answerable and not did_answer and not failed)
        claims += len(verdicts)
        correct_claims += sum(verdicts.values())
        technical_failures += failed
        durations.append(float(result.get("duration", 0)))

    def ratio(a, b):
        return a / b if b else None

    durations.sort()
    return {
        "evaluation_status": "human_reviewed",
        "cases": len(cases),
        "claim_precision": ratio(correct_claims, claims),
        "judged_claims": claims,
        "recognition_precision": ratio(correct_recognitions, judged_recognitions),
        "judged_recognitions": judged_recognitions,
        "answered_slot_accuracy": ratio(correct_slots, answered),
        "answered_slots": answered,
        "answerable_slot_coverage": ratio(answered_answerable, answerable),
        "false_refusal_rate": ratio(false_refusals, evaluable_answerable),
        "answerable_slots": answerable,
        "answerable_slots_without_technical_failure": evaluable_answerable,
        "technical_failures": technical_failures,
        "latency_p50_seconds": durations[(len(durations) - 1) // 2],
        "latency_p95_seconds": durations[min(len(durations) - 1, int(len(durations) * 0.95))],
        "note": "Đúng/sai do người duyệt; không lấy verdict model làm ground truth. Không suy ra chi phí khi thiếu usage.",
    }
