"""Per-question coverage based on checked claims and separate recognition evidence."""

from core.evidence import SlotResult


def slot_results(
    slots,
    claims,
    evidence,
    assessments,
    *,
    unsupported=(),
    recognition=None,
    identity_covered=False,
    readability="limited",
):
    registry = {e["evidence_id"]: e for e in evidence}
    by_slot = {}
    duplicates = set()
    for item in assessments:
        if item.slot_id in by_slot:
            duplicates.add(item.slot_id)
        by_slot[item.slot_id] = item
    results = []
    for slot in slots:
        identifier = slot["slot_id"]
        matched = [c for c in claims if c["slot_id"] == identifier]
        supported = [c for c in matched if c["verdict"] == "supported"]
        ids = list(dict.fromkeys(ref for c in supported for ref in c["evidence_ids"]))
        reasons = []
        status = "answered" if supported else "unanswered"
        assessment = by_slot.get(identifier)
        if identifier in unsupported:
            status, reasons, supported, ids = "unsupported", ["unsupported_request"], [], []
        elif slot["evidence_type"] == "identity" and recognition is not None:
            status = "answered" if identity_covered else "unanswered"
            if identity_covered:
                ids = recognition.get("evidence_ids", [])
            else:
                supported, ids = [], []
                reasons = [
                    "entity_ambiguous"
                    if recognition["status"] == "ambiguous"
                    else "image_unreadable"
                    if readability == "unreadable"
                    else "identity_unconfirmed"
                    if recognition["status"] in {"probable", "recognized"}
                    else "insufficient_evidence"
                ]
        else:
            if assessment and assessment.status == "complete" and not supported:
                reasons.append("invalid_verifier_response")
            if assessment and assessment.status == "conflicted":
                status, reasons = "conflicted", ["source_conflict"]
            elif assessment and (
                assessment.status in {"partial", "unanswered"} or assessment.missing_information
            ):
                status = "partial" if supported else "unanswered"
                reasons = ["incomplete_answer"]
            if supported and any(c.get("gate_errors") for c in matched) and status == "answered":
                status, reasons = "partial", ["incomplete_answer"]
            if identifier in duplicates:
                status, reasons = (
                    "partial" if supported else "unanswered",
                    ["invalid_verifier_response"],
                )
            gate_errors = {error for claim in matched for error in claim.get("gate_errors", [])}
            reasons.extend(
                code
                for code in (
                    "relation_quote_mismatch",
                    "nearest_scope_required",
                    "nearest_relation_required",
                )
                if code in gate_errors
            )
            if "count_grounding_missing" in gate_errors:
                reasons.append("count_grounding_missing")
            if "object_class_uncertain" in gate_errors:
                reasons.append("object_class_uncertain")
            if gate_errors & {
                "suspected_axis_swap",
                "count_instance_box_missing",
                "count_observation_box_mismatch",
                "count_instance_total_mismatch",
                "duplicate_count_instance",
                "count_observation_missing",
                "count_object_class_mismatch",
                "count_value_unverifiable",
                "duplicate_count_finding",
            }:
                reasons.append("invalid_visual_grounding")
            if status != "answered":
                has_source = any(
                    registry[ref]["kind"] == "source" for ref in ids if ref in registry
                )
                if slot["evidence_type"] in {"historical", "mixed"} and not has_source:
                    reasons.append("missing_source")
                    reasons.append(
                        "no_supporting_source"
                        if any(row["kind"] == "source" for row in registry.values())
                        else "no_retrieved_sources"
                    )
                elif slot["evidence_type"] in {"historical", "mixed"} and gate_errors & {
                    "supporting_quote_missing",
                    "invalid_quote",
                    "source_entity_mismatch",
                    "source_entity_unresolved",
                    "unregistered_evidence",
                }:
                    reasons.append("no_supporting_source")
                elif readability == "unreadable" and slot["evidence_type"] in {"visual", "mixed"}:
                    reasons.append("image_unreadable")
                elif not reasons:
                    reasons.append("insufficient_evidence")
        results.append(
            SlotResult(
                slot_id=identifier,
                question=slot["question"],
                evidence_type=slot["evidence_type"],
                status=status,
                reason_codes=list(dict.fromkeys(reasons)),
                claim_ids=[c["claim_id"] for c in supported],
                evidence_ids=ids,
            ).model_dump(mode="json")
        )
    return results
