"""Recognition policy over registered image evidence, independent from historical facts."""

from core.evidence import RecognitionResult, claim_risks


def safe_basis_text(text, claim_policy):
    """Recognition explanations cannot introduce facts that would require source verification."""
    if claim_risks(text, claim_policy):
        return "Đánh giá liên kết ứng viên với các quan sát ảnh; xem bằng chứng kèm theo."
    return text


def candidate_support(findings, visual_evidence, catalog):
    """Map model observation indices to backend IDs; never accept model-issued evidence IDs."""
    rows = []
    for proposed in findings.candidate_support:
        candidates = catalog.candidates([proposed.name])
        if not candidates:
            continue
        candidate = candidates[0]
        refs = list(
            dict.fromkeys(
                visual_evidence[index]["evidence_id"]
                for index in proposed.observation_indices
                if index < len(visual_evidence)
            )
        )
        rows.append(
            {
                "entity_id": candidate["entity_id"],
                "name": candidate["name"],
                "basis": proposed.basis,
                "evidence_ids": refs,
                "explanation": proposed.explanation,
            }
        )
    return rows


def check_recognition(
    assessment,
    candidates,
    support,
    evidence,
    policy,
    *,
    identity_resolved,
    readability="adequate",
    claim_policy=None,
):
    """Agreement alone, a user hint, source text or generic shape cannot identify the photo."""
    ambiguous = len(candidates) > 1
    fallback = "ambiguous" if ambiguous else "unrecognized"
    result = RecognitionResult(
        status=fallback,
        candidate_support=support,
        assessment=assessment,
        explanation="Chưa có đánh giá nhận diện được hỗ trợ bởi đặc điểm ảnh.",
    )
    if not assessment:
        result.gate_errors = ["recognition_assessment_missing"]
        return result.model_dump(mode="json")
    result.explanation = assessment.explanation
    if assessment.status in {"ambiguous", "unrecognized"}:
        result.status = assessment.status if not ambiguous else "ambiguous"
        return result.model_dump(mode="json")
    errors = []
    if readability == "unreadable":
        errors.append("recognition_image_unreadable")
    candidate = next((c for c in candidates if c["entity_id"] == assessment.entity_id), None)
    if not candidate or ambiguous or not identity_resolved:
        errors.append("recognition_candidate_unresolved")
    if candidate and claim_policy and claim_risks(candidate["name"], claim_policy):
        errors.append("recognition_content_requires_source")
    basis = next((s for s in support if s["entity_id"] == assessment.entity_id), {})
    if basis.get("basis") not in {"distinctive_configuration", "readable_name"}:
        errors.append("recognition_distinctive_basis_required")
    registry = {e["evidence_id"]: e for e in evidence}
    refs = list(dict.fromkeys(assessment.evidence_ids))
    if any(
        ref not in registry
        or registry[ref]["kind"] not in {"visual", "ocr"}
        or ref not in basis.get("evidence_ids", [])
        for ref in refs
    ):
        errors.append("recognition_image_evidence_required")
    if len(refs) < policy.min_observations:
        errors.append("recognition_observations_insufficient")
    result.gate_errors = errors
    if not errors:
        result.status = "probable" if policy.max_status == "probable" else assessment.status
        result.entity_id = candidate["entity_id"]
        result.name = candidate["name"]
        result.basis = basis["basis"]
        result.evidence_ids = refs
    return result.model_dump(mode="json")


def recognition_sentence(recognition):
    if not recognition or recognition["status"] not in {"probable", "recognized"}:
        return None
    name = recognition["name"]
    if recognition["status"] == "recognized":
        return f"Nhận diện tự động theo đặc điểm ảnh: {name}."
    return f"Công trình trong ảnh có thể là {name}, dựa trên các đặc điểm nhìn thấy."
