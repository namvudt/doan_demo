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
    readability: Literal["adequate", "limited", "unreadable"] = "limited"


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
            cleaned["observations"].append(item)
    return VisualFindings.model_validate(cleaned), warnings


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


class Quotation(Contract):
    evidence_id: str
    quote: str = Field(min_length=1, max_length=1500)


class AssessedClaim(Contract):
    slot_id: str
    text: str = Field(min_length=1, max_length=2000)
    kind: Literal["visual", "historical", "interpretation", "identity"]
    verdict: Literal["supported", "contradicted", "insufficient", "not_assessable"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
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


class EvidenceReview(Contract):
    claims: list[AssessedClaim] = Field(default_factory=list, max_length=40)
    recognition: RecognitionAssessment | None = None


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


def check_claims(review, evidence, slots, policy, *, identity_resolved, selected_entity_id=None):
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
        if claim["kind"] in {"visual", "identity"} and not any(
            e.kind in {"visual", "ocr"} for e in refs
        ):
            reasons.append("image_evidence_required")
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
