"""Versioned public evidence contracts. Models propose; application code assigns IDs."""

import hashlib
import json
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Coordinate = Annotated[float, Field(ge=0, le=1)]
BOX_DESCRIPTION = "Root-image [x1,y1,x2,y2] in 0..1, x1<x2, y1<y2. Never pixels or 0..1000."


def stable_id(prefix, value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return prefix + "_" + hashlib.sha256(encoded).hexdigest()[:20]


def normalized_text(text):
    value = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return " ".join(re.findall(r"\w+", "".join(c for c in value if not unicodedata.combining(c))))


def bounded_report(text, max_chars):
    """Limit intermediate prose only; original evidence/source snapshots are never truncated here."""
    if len(text) <= max_chars:
        return text, False
    marker = "\n[Báo cáo trung gian đã rút gọn; xem evidence và nguồn gốc.]"
    budget = max(1, max_chars - len(marker))
    head = text[:budget]
    boundary = max(head.rfind("\n"), head.rfind(". "))
    if boundary >= budget // 2:
        head = head[: boundary + 1]
    return head.rstrip() + marker, True


class RequestedSlot(Contract):
    slot_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1000)
    evidence_type: Literal["visual", "historical", "identity", "mixed"] = "mixed"
    aspect: Literal["construction", "restoration", "reconstruction"] | None = None


class Candidate(Contract):
    name: str = Field(min_length=1, max_length=200)
    entity_id: str | None = None
    reason: str = Field(default="", max_length=1000)


class Region(Contract):
    box: list[Coordinate] = Field(min_length=4, max_length=4, description=BOX_DESCRIPTION)
    purpose: str = Field(default="Đọc chữ liên quan đến câu hỏi", max_length=300)

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.box
        if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
            raise ValueError("Box must use normalized root-image x1,y1,x2,y2 coordinates")
        return self


class Observation(Contract):
    text: str = Field(min_length=1, max_length=1500)
    box: list[Coordinate] | None = Field(
        default=None, min_length=4, max_length=4, description=BOX_DESCRIPTION
    )

    @model_validator(mode="after")
    def valid_box(self):
        if self.box:
            Region(box=self.box)
        return self


class NamedBox(Contract):
    """Unambiguous image coordinates for newly produced object instances."""

    x_min: Coordinate
    y_min: Coordinate
    x_max: Coordinate
    y_max: Coordinate

    @model_validator(mode="after")
    def valid_box(self):
        Region(box=self.as_list())
        return self

    def as_list(self):
        return [self.x_min, self.y_min, self.x_max, self.y_max]


class CountInstance(Contract):
    observation_index: Annotated[int, Field(ge=0, le=19)]
    object_class: str = Field(min_length=1, max_length=200)
    classification: Literal["confirmed", "uncertain", "excluded"]
    box: NamedBox | None = None


class CountFinding(Contract):
    slot_id: str = Field(min_length=1, max_length=80)
    object_class: str = Field(min_length=1, max_length=200)
    count: Annotated[int, Field(ge=0, le=100)]
    instances: list[CountInstance] = Field(max_length=100)


class LocationHint(Contract):
    name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    provenance: Literal["user", "sample_label"] = "user"


class CandidateSupport(Contract):
    name: str = Field(min_length=1, max_length=200)
    observation_indices: list[Annotated[int, Field(ge=0, le=19)]] = Field(
        default_factory=list,
        max_length=20,
        description="Zero-based indices into observations; only features supporting this candidate.",
    )
    basis: Literal["distinctive_configuration", "readable_name", "generic_appearance", "none"]
    explanation: str = Field(default="", max_length=500)


class VisualFindings(Contract):
    observations: list[Observation] = Field(default_factory=list, max_length=20)
    candidates: list[str] = Field(default_factory=list, max_length=3)
    candidate_support: list[CandidateSupport] = Field(default_factory=list, max_length=3)
    count_findings: list[CountFinding] = Field(default_factory=list, max_length=20)
    readability: Literal["adequate", "limited", "unreadable"] = "limited"
    scene_visibility: Literal["adequate", "limited", "unreadable"] | None = Field(
        default=None,
        description="Visibility of scene/architecture only; independent of readable text and historical knowledge.",
    )
    text_readability: Literal["adequate", "limited", "unreadable", "not_applicable"] | None = Field(
        default=None,
        description="Legibility of text only; unreadable text does not imply an unreadable scene.",
    )


def parse_visual_findings(raw):
    """Invalid geometry is discarded, never guessed/rescaled into a different coordinate system."""
    cleaned, warnings = dict(raw), []
    observations = raw.get("observations", [])
    if isinstance(observations, list):
        cleaned["observations"] = []
        for index, observation in enumerate(observations):
            item = dict(observation) if isinstance(observation, dict) else observation
            if isinstance(item, dict) and item.get("box") is not None:
                try:
                    Region(box=item["box"])
                except (ValueError, TypeError):
                    item["box"] = None
                    warnings.append({"observation_index": index, "code": "invalid_box_discarded"})
                else:
                    for code in geometry_issues(item.get("text", ""), item["box"]):
                        warnings.append({"observation_index": index, "code": code})
            cleaned["observations"].append(item)
    if isinstance(raw.get("count_findings"), list):
        cleaned["count_findings"] = []
        for finding_index, finding in enumerate(raw["count_findings"]):
            current = dict(finding) if isinstance(finding, dict) else finding
            if isinstance(current, dict) and isinstance(current.get("instances"), list):
                current["instances"] = []
                for instance_index, instance in enumerate(finding["instances"]):
                    instance = dict(instance) if isinstance(instance, dict) else instance
                    if isinstance(instance, dict) and instance.get("box") is not None:
                        box = instance["box"]
                        try:
                            if isinstance(box, (list, tuple)):
                                Region(box=list(box))
                                box = dict(zip(("x_min", "y_min", "x_max", "y_max"), box))
                            instance["box"] = NamedBox.model_validate(box).model_dump()
                        except (ValueError, TypeError):
                            instance["box"] = None
                            warnings.append(
                                {
                                    "count_finding_index": finding_index,
                                    "instance_index": instance_index,
                                    "code": "invalid_count_box_discarded",
                                }
                            )
                    current["instances"].append(instance)
            cleaned["count_findings"].append(current)
    return VisualFindings.model_validate(cleaned), warnings


def geometry_issues(text, box):
    """Flag strong text/geometry contradictions; never guess or transpose coordinates."""
    if not box:
        return []
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    words = normalized_text(text)
    issues = []
    if re.search(r"\b(?:thang dung|vertical|upright)\b", words) and width > 4 * height:
        issues.append("suspected_axis_swap")
    if re.search(r"\b(?:ben phai|phia phai|right)\b", words) and (x1 + x2) / 2 < 0.3:
        if (y1 + y2) / 2 > 0.7:
            issues.append("suspected_axis_swap")
    if re.search(r"\b(?:ben trai|phia trai|left)\b", words) and (x1 + x2) / 2 > 0.7:
        if (y1 + y2) / 2 < 0.3:
            issues.append("suspected_axis_swap")
    return list(dict.fromkeys(issues))


class OCRLine(Observation):
    pass


class OCROutput(Contract):
    lines: list[OCRLine] = Field(default_factory=list, max_length=30)
    readable: bool = False


class Evidence(Contract):
    evidence_id: str
    kind: Literal["visual", "ocr", "source"]
    text: str
    source_id: str | None = None
    region_id: str | None = None
    box: tuple[float, float, float, float] | None = None
    version: str
    entity_id: str | None = None
    grounding_errors: list[str] = Field(default_factory=list)
    count_grounding: list[dict] = Field(default_factory=list)


class Quotation(Contract):
    evidence_id: str
    quote: str = Field(min_length=1, max_length=1500)


class AssessedClaim(Contract):
    slot_id: str
    text: str = Field(min_length=1, max_length=2000)
    kind: Literal["visual", "historical", "interpretation", "identity"]
    verdict: Literal["supported", "contradicted", "insufficient", "not_assessable"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    quotations: list[Quotation] = Field(default_factory=list, max_length=10)
    explanation: str = Field(default="", max_length=1000)
    risk_tags: list[Literal["han_nom_reading", "specific_material", "historical_date"]] = Field(
        default_factory=list, max_length=3
    )


class RecognitionAssessment(Contract):
    status: Literal["recognized", "probable", "ambiguous", "unrecognized"]
    entity_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = Field(default="", max_length=700)


class RecognitionResult(RecognitionAssessment):
    name: str | None = None
    basis: str | None = None
    gate_errors: list[str] = Field(default_factory=list)
    candidate_support: list[dict] = Field(default_factory=list)
    assessment: RecognitionAssessment | None = None


SlotReason = Literal[
    "missing_source",
    "insufficient_evidence",
    "entity_ambiguous",
    "image_unreadable",
    "identity_unconfirmed",
    "unsupported_request",
    "source_conflict",
    "incomplete_answer",
    "verification_unavailable",
    "no_retrieved_sources",
    "no_supporting_source",
    "invalid_verifier_response",
    "invalid_visual_grounding",
    "count_grounding_missing",
    "object_class_uncertain",
    "relation_quote_mismatch",
    "nearest_scope_required",
    "nearest_relation_required",
]


class SlotAssessment(Contract):
    slot_id: str
    status: Literal["complete", "partial", "unanswered", "conflicted"]
    missing_information: list[str] = Field(default_factory=list, max_length=5)


class SlotResult(Contract):
    slot_id: str
    question: str
    evidence_type: Literal["visual", "historical", "identity", "mixed"]
    status: Literal["answered", "partial", "unanswered", "unsupported", "conflicted"]
    reason_codes: list[SlotReason] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class EvidenceReview(Contract):
    claims: list[AssessedClaim] = Field(max_length=40)
    recognition: RecognitionAssessment | None = None
    slot_assessments: list[SlotAssessment] = Field(max_length=40)


def validate_review_contract(review, slots):
    """Check the verifier's semantic response contract before accepting or repairing it."""
    allowed = {slot["slot_id"]: slot for slot in slots}
    errors, seen = [], set()
    for assessment in review.slot_assessments:
        identifier = assessment.slot_id
        if identifier not in allowed:
            errors.append("unknown_assessment_slot:" + identifier)
        if identifier in seen:
            errors.append("duplicate_assessment_slot:" + identifier)
        seen.add(identifier)
        if assessment.status == "complete" and identifier in allowed:
            if allowed[identifier]["evidence_type"] != "identity" and not any(
                claim.slot_id == identifier and claim.verdict == "supported"
                for claim in review.claims
            ):
                errors.append("complete_without_supported_claim:" + identifier)
            if assessment.missing_information:
                errors.append("complete_with_missing_information:" + identifier)
    for identifier in allowed.keys() - seen:
        errors.append("missing_assessment_slot:" + identifier)
    for claim in review.claims:
        if claim.slot_id not in allowed:
            errors.append("unknown_claim_slot:" + claim.slot_id)
    return sorted(set(errors))


def is_count_question(question):
    return bool(
        re.search(
            r"\b(?:bao nhieu|may cot|may tru|may cua|so luong|how many|number of|count)\b",
            normalized_text(question),
        )
    )


def _box_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0


def annotate_count_grounding(
    findings,
    evidence,
    slots,
    *,
    reject_suspected_axis_swap=True,
    duplicate_iou_threshold=0.85,
):
    """Attach backend-checked instance records to already registered visual evidence.

    Observation indices address visual rows only, so preceding source/OCR records cannot
    shift the mapping. Stable IDs remain those assigned by the caller. This function
    does not assert that a model's object classification is independently correct.
    """
    rows = [{**item, "count_grounding": []} for item in evidence]
    visual = [item for item in rows if item["kind"] == "visual"]
    allowed = {slot["slot_id"]: slot for slot in slots}
    warnings = []
    for index, observation in enumerate(findings.observations):
        if index >= len(visual):
            break
        errors = []
        if observation.box is not None and reject_suspected_axis_swap:
            errors.extend(geometry_issues(observation.text, observation.box))
        if errors:
            visual[index]["grounding_errors"] = list(
                dict.fromkeys([*visual[index].get("grounding_errors", []), *errors])
            )
    seen_slots = set()
    for finding in findings.count_findings:
        identifier = finding.slot_id
        shared_errors = []
        if identifier not in allowed:
            warnings.append({"slot_id": identifier, "code": "unknown_count_slot"})
            continue
        if identifier in seen_slots:
            shared_errors.append("duplicate_count_finding")
            # Also invalidate the earlier records for this slot.
            for row in visual:
                for record in row["count_grounding"]:
                    if record["slot_id"] == identifier:
                        record["errors"].append("duplicate_count_finding")
        seen_slots.add(identifier)
        if not re.search(
            r"\b" + re.escape(normalized_text(finding.object_class)) + r"s?\b",
            normalized_text(allowed[identifier]["question"]),
        ):
            shared_errors.append("count_object_class_mismatch")
        confirmed = [item for item in finding.instances if item.classification == "confirmed"]
        if finding.count != len(confirmed):
            shared_errors.append("count_instance_total_mismatch")
        if any(item.classification == "uncertain" for item in finding.instances):
            shared_errors.append("object_class_uncertain")
        indices = [item.observation_index for item in confirmed]
        if len(indices) != len(set(indices)):
            shared_errors.append("duplicate_count_instance")
        boxes = [item.box.as_list() for item in confirmed if item.box]
        if any(
            _box_iou(box, other) >= duplicate_iou_threshold
            for index, box in enumerate(boxes)
            for other in boxes[index + 1 :]
        ):
            shared_errors.append("duplicate_count_instance")
        for instance in finding.instances:
            errors = list(shared_errors)
            index = instance.observation_index
            if index >= len(findings.observations) or index >= len(visual):
                warnings.append({"slot_id": identifier, "code": "count_observation_missing"})
                shared_errors.append("count_observation_missing")
                continue
            if instance.classification != "confirmed":
                errors.append("object_class_uncertain")
            if normalized_text(instance.object_class) != normalized_text(finding.object_class):
                errors.append("count_object_class_mismatch")
            if instance.box is None:
                errors.append("count_instance_box_missing")
            else:
                observation = findings.observations[index]
                box = instance.box.as_list()
                if reject_suspected_axis_swap:
                    errors.extend(geometry_issues(observation.text, box))
                if observation.box is None or _box_iou(box, observation.box) < 0.5:
                    errors.append("count_observation_box_mismatch")
            errors.extend(visual[index].get("grounding_errors", []))
            visual[index]["count_grounding"].append(
                {
                    "slot_id": identifier,
                    "object_class": finding.object_class,
                    "declared_count": finding.count,
                    "instance_index": index,
                    "classification": instance.classification,
                    "errors": sorted(set(errors)),
                }
            )
        # Missing/out-of-range instances invalidate all records in the finding.
        for row in visual:
            for record in row["count_grounding"]:
                if record["slot_id"] == identifier:
                    record["errors"] = sorted(set([*record["errors"], *shared_errors]))
                    for error in record["errors"]:
                        warnings.append({"slot_id": identifier, "code": error})
    return rows, warnings


def _count_claim_errors(claim, slot, refs):
    records = [
        (evidence.evidence_id, record)
        for evidence in refs
        for record in evidence.count_grounding
        if record.get("slot_id") == slot["slot_id"]
    ]
    if not records:
        return ["count_grounding_missing"]
    errors = {error for _, record in records for error in record.get("errors", [])}
    declared = {record["declared_count"] for _, record in records}
    instances = {record["instance_index"] for _, record in records if not record.get("errors")}
    if len(declared) != 1 or declared != {len(instances)}:
        errors.add("count_instance_total_mismatch")
    # Prefer a count attached to the object class. Additional per-object descriptions
    # ("two poles, one on each side") must not change the actual answer count.
    words = normalized_text(claim["text"])
    names = {
        "khong": 0,
        "mot": 1,
        "hai": 2,
        "ba": 3,
        "bon": 4,
        "nam": 5,
        "sau": 6,
        "bay": 7,
        "tam": 8,
        "chin": 9,
        "muoi": 10,
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    units = {**names, "tu": 4, "lam": 5}
    unit_pattern = "|".join(word for word, value in units.items() if value < 10)
    number_pattern = (
        r"\d{1,3}|(?:"
        + unit_pattern
        + r")\s+muoi(?:\s+(?:"
        + unit_pattern
        + r"))?|muoi(?:\s+(?:"
        + unit_pattern
        + r"))?|"
        + "|".join(names)
    )

    def number_value(value):
        if value.isdigit():
            return int(value)
        tokens = value.split()
        if "muoi" in tokens and len(tokens) > 1:
            index = tokens.index("muoi")
            return (units[tokens[0]] * 10 if index else 10) + (
                units[tokens[-1]] if len(tokens) > index + 1 else 0
            )
        return names.get(value)

    objects = {normalized_text(record["object_class"]) for _, record in records}
    values = set()
    for object_class in objects:
        pattern = r"\b(" + number_pattern + r")\s+(?:\w+\s+){0,2}" + re.escape(object_class)
        for value in re.findall(pattern, words):
            values.add(number_value(value))
    if not values:
        values = {int(value) for value in re.findall(r"\b\d{1,3}\b", words)}
    if not values and re.fullmatch(number_pattern, words):
        values = {number_value(words)}
    if values != declared:
        errors.add("count_value_unverifiable")
    return sorted(errors)


class CheckedClaim(AssessedClaim):
    claim_id: str
    gate_errors: list[str] = Field(default_factory=list)


class Clarification(Contract):
    clarification_id: str
    revision: int = Field(default=1, ge=1)
    reason: Literal["entity_ambiguous", "image_unreadable", "missing_evidence"]
    question: str
    options: list[str] = Field(default_factory=list)
    rounds: int = Field(default=0, ge=0)


def claim_risks(text, policy):
    """Conservative text checks supplement the model's optional risk labels."""
    normalized = normalized_text(text)
    risks = set()
    if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]", text):
        risks.add("han_nom_reading")
    han_context = re.search(r"\b(?:chu han|han nom|han tu|hoanh phi|cau doi)\b", normalized)
    if han_context and (
        re.search(
            r"\b(?:phien am|phien doc|dich nghia|doc tu|doc la|doc thanh|am han viet|nghia la)\b",
            normalized,
        )
        or re.search(r"(?:ghi|viết|khắc|mang)\s+[\"'“‘]", text, re.IGNORECASE)
    ):
        risks.add("han_nom_reading")
    tokens = " " + normalized + " "
    if any(" " + normalized_text(term) + " " in tokens for term in policy.specific_material_terms):
        risks.add("specific_material")
    if re.search(
        r"\b(?:bang|duc|chat lieu|lu huong|dinh|chuong|tuong|cot)(?:\s+\w+){0,2}\s+(?:dong|vang|bac)\b",
        normalized,
    ):
        risks.add("specific_material")
    if re.search(
        r"\b(?:[12]\d{3}|nam\s+\d{1,4}|the ky (?:\d+|[ivxlcdm]+)|thoi vua|nien dai|khoi dung|tai dung|trieu dai)\b",
        normalized,
    ):
        risks.add("historical_date")
    return risks


def check_claims(
    review,
    evidence,
    slots,
    policy,
    *,
    identity_resolved,
    selected_entity_id=None,
    require_count_grounding=False,
    original_question=None,
    question_subject=None,
):
    """Validate citations and exact quotations in addition to the model's semantic verdict."""
    registry = {e["evidence_id"]: Evidence.model_validate(e) for e in evidence}
    allowed_slots = {slot["slot_id"]: slot for slot in slots}
    checked = []
    for proposed in review.claims[: policy.max_claims]:
        claim = proposed.model_dump(mode="json")
        reasons = []
        risks = claim_risks(claim["text"], policy.claim_policy) | set(proposed.risk_tags)
        claim["risk_tags"] = sorted(risks)
        if "han_nom_reading" in risks and not policy.claim_policy.allow_han_nom_reading:
            reasons.append("han_nom_reading_unsupported")
        factual_risk = (
            "specific_material" in risks
            and policy.claim_policy.require_source_for_specific_materials
        ) or ("historical_date" in risks and policy.claim_policy.require_source_for_dates)
        refs = [registry[key] for key in claim["evidence_ids"] if key in registry]
        if claim["slot_id"] not in allowed_slots:
            reasons.append("unknown_slot")
        if (
            not refs
            or not set(claim["evidence_ids"]) <= set(registry)
            or len(claim["evidence_ids"]) != len(set(claim["evidence_ids"]))
        ):
            reasons.append("unregistered_evidence")
        if (
            factual_risk
            or claim["kind"] in {"historical", "interpretation"}
            or allowed_slots.get(claim["slot_id"], {}).get("evidence_type")
            in {"historical", "mixed"}
        ):
            if not identity_resolved:
                reasons.append("identity_unresolved")
            sources = [e for e in refs if e.kind == "source"]
            if not sources:
                reasons.append("source_required")
                if factual_risk:
                    reasons.append("factual_attribute_requires_source")
            for source in sources:
                if source.entity_id is None:
                    reasons.append("source_entity_unresolved")
                elif selected_entity_id is not None and source.entity_id != selected_entity_id:
                    reasons.append("source_entity_mismatch")
                quotes = [
                    q.quote for q in proposed.quotations if q.evidence_id == source.evidence_id
                ]
                if not any(
                    len(q.strip()) >= policy.min_quote_chars and q in source.text for q in quotes
                ):
                    reasons.append("supporting_quote_missing")
                if policy.claim_policy.require_relation_quote and (
                    original_question or question_subject
                ):
                    from core.relations import question_relation, validate_source_relation

                    relation_rules = {
                        k: dict(v) for k, v in policy.claim_policy.source_relation_rules.items()
                    }
                    questions = getattr(policy, "questions", None)
                    if questions is not None:
                        nearest_rule = relation_rules.setdefault("nearest", {})
                        nearest_rule.setdefault(
                            "question_patterns",
                            [
                                *questions.nearest_patterns,
                                *[
                                    re.escape(normalized_text(term))
                                    for term in questions.nearest_terms
                                ],
                            ],
                        )
                        nearest_rule.setdefault(
                            "scope_patterns",
                            [
                                re.escape(normalized_text(term))
                                for term in questions.nearest_scope_terms
                            ]
                            if questions.require_nearest_scope
                            else [".*"],
                        )
                    slot_question = allowed_slots.get(claim["slot_id"], {}).get("question", "")
                    relation_question = (
                        slot_question
                        if question_relation(slot_question, relation_rules)
                        else original_question or slot_question
                    )

                    relation_errors = [
                        validate_source_relation(
                            claim["text"],
                            quote,
                            subject=question_subject,
                            question=relation_question,
                            rules=relation_rules,
                        )
                        for quote in quotes
                    ]
                    if relation_errors and all(relation_errors):
                        reasons.extend(relation_errors)
        if claim["kind"] in {"visual", "identity"} and not any(
            e.kind in {"visual", "ocr"} for e in refs
        ):
            reasons.append("image_evidence_required")
        if claim["kind"] == "visual":
            reasons.extend(error for ref in refs for error in ref.grounding_errors)
        slot = allowed_slots.get(claim["slot_id"], {})
        if (
            require_count_grounding
            and slot.get("evidence_type") == "visual"
            and is_count_question(slot.get("question", ""))
        ):
            reasons.extend(_count_claim_errors(claim, slot, refs))
        if claim["kind"] == "identity" and not identity_resolved:
            reasons.append("identity_unresolved")
        for quote in proposed.quotations:
            if (
                quote.evidence_id not in claim["evidence_ids"]
                or quote.evidence_id not in registry
                or quote.quote not in registry[quote.evidence_id].text
            ):
                reasons.append("invalid_quote")
        if re.search(r"https?://|\[(?:wiki_|web_)[^]]+\]", claim["text"]):
            reasons.append("model_generated_citation")
        claim["claim_id"] = stable_id("claim", {"text": claim["text"], "slot_id": claim["slot_id"]})
        claim["gate_errors"] = sorted(set(reasons))
        if reasons:
            claim["verdict"] = "insufficient"
        existing = next((c for c in checked if c["claim_id"] == claim["claim_id"]), None)
        if existing and existing["verdict"] != claim["verdict"]:
            existing["verdict"] = "insufficient"
            existing["gate_errors"] = sorted(
                set([*existing["gate_errors"], "conflicting_duplicate"])
            )
        elif existing is None:
            checked.append(claim)
    return checked
