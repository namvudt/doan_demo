"""Small configurable intent rules; preserve the original query for semantic verification."""

import re

from core.evidence import normalized_text, stable_id

DEFAULT_NEAREST_PATTERNS = (
    r"\bgan\b[^.!?;\n]{0,80}\bnhat\b",
    r"\b(?:closest|nearest)\b",
)
DEFAULT_NEAREST_SCOPE_TERMS = (
    "trong số",
    "trong phạm vi",
    "trong bán kính",
    "among",
    "within",
    "listed",
)


def is_nearest_query(query, policy):
    """Recognize comparison intent, including separated Vietnamese 'gần ... nhất'.

    Regexes operate on normalized text and are configurable. A bare 'gần đây'
    does not request a nearest-place comparison, whether spatial or temporal.
    """
    patterns = getattr(policy, "nearest_patterns", DEFAULT_NEAREST_PATTERNS)
    terms = getattr(policy, "nearest_terms", ())
    for part in re.split(r"[.!?;\n]", query):
        text = normalized_text(part)
        pattern_text = re.sub(r"\bgan day\b", " ", text)
        for pattern in patterns:
            if re.search(pattern, pattern_text, flags=re.IGNORECASE):
                return True
        if any(
            re.search(r"(?<!\w)" + re.escape(normalized_text(term)) + r"(?!\w)", text)
            for term in terms
            if term.strip()
        ):
            return True
    return False


def nearest_scope_missing(query, policy):
    """A nearest claim needs a comparison set or bounded search area.

    This diagnoses missing context, not evidence quality. Explicit scope still
    needs suitable evidence before any nearest answer can be accepted.
    """
    if not getattr(policy, "require_nearest_scope", True) or not is_nearest_query(query, policy):
        return False
    text = normalized_text(query)
    return not any(
        re.search(r"(?<!\w)" + re.escape(normalized_text(term)) + r"(?!\w)", text)
        for term in getattr(policy, "nearest_scope_terms", DEFAULT_NEAREST_SCOPE_TERMS)
        if term.strip()
    )


def effective_relation_question(query, context, policy):
    """Add only a user's explicit comparison scope to an unscoped relation.

    The original question remains the persisted user query. This derived string
    is a planning condition, never a source or an asserted geographic answer.
    Unrelated answers, unknown responses, factual assertions and instructions
    cannot satisfy the missing comparison scope.
    """
    if not nearest_scope_missing(query, policy) or response_is_unknown(context, policy):
        return query
    answer = context.get("answer")
    max_chars = getattr(policy, "nearest_scope_max_chars", 500)
    if not isinstance(answer, str) or not answer.strip() or len(answer) > max_chars:
        return query
    terms = sorted(
        {
            normalized_text(term)
            for term in getattr(policy, "nearest_scope_terms", DEFAULT_NEAREST_SCOPE_TERMS)
            if term.strip()
        },
        key=len,
        reverse=True,
    )
    if not terms:
        return query
    # Retain the user's spelling while comparing normalized tokens. Sentence
    # boundaries discard a trailing instruction instead of forwarding it.
    forbidden = (
        r"\b(?:hay|bo qua|bat buoc|khong can nguon|ignore|disregard|override|"
        r"instructions?|system|prompt|return|respond|assert|tra loi|dap an|ket luan|"
        r"khang dinh|chac chan|evidence|quotation|citation)\b"
        r"|\b(?:gan nhat la|la gan nhat|closest is|nearest is|"
        r"thuoc|cach|nam o|duoc|is the|is closest|is nearest)\b"
    )
    for clause in re.split(r"[;\n!?]|(?<!\d)\.(?!\d)", answer):
        words = list(re.finditer(r"\S+", clause))
        normalized_words = [normalized_text(word.group()).strip() for word in words]
        for start in range(len(words)):
            remainder = " ".join(normalized_words[start:])
            term = next(
                (term for term in terms if remainder == term or remainder.startswith(term + " ")),
                None,
            )
            if term is None:
                continue
            scope = clause[words[start].start() :].strip(" ,:\t\"'“”‘’")
            value = normalized_text(scope)
            suffix = value[len(term) :].strip()
            # A marker without actual choices or an area is not useful context.
            if (
                not suffix
                or suffix in {"nay", "do", "nao", "nhung noi nay", "cac noi nay"}
                or re.search(forbidden, value)
                or re.search(r"https?://|[{}<>]", scope, flags=re.IGNORECASE)
            ):
                return query
            # A radius must contain a positive numeric distance with units.
            if "ban kinh" in term or (term == "within" and re.search(r"\d", suffix)):
                radius = re.search(
                    r"\b(\d+(?:[.,]\d+)?)\s*(?:km|m|kilometres?|kilometers?|metres?|meters?)\b",
                    scope,
                    flags=re.IGNORECASE,
                )
                if radius is None or float(radius[1].replace(",", ".")) <= 0:
                    return query
            return query + "\nPhạm vi so sánh do người dùng chọn (dữ liệu): " + scope
    return query


def preserve_nearest_condition(slots, query, policy):
    """Prevent a planner turning 'nearest' into a generic nearby-place question.

    Existing nearest slots retain their IDs and wording. If the planner omitted
    the comparison, restore the actual question rather than inventing a place or
    a comparison set. A separate event/history question is never overwritten.
    """
    if not is_nearest_query(query, policy):
        return slots
    result = [dict(slot) for slot in slots]
    matching = [i for i, slot in enumerate(result) if is_nearest_query(slot["question"], policy)]
    if matching:
        for index in matching:
            slot = result[index]
            if slot["evidence_type"] not in {"historical", "mixed"}:
                slot["evidence_type"] = "mixed"
            # Preserve the original explicit comparison frame if paraphrasing
            # retained 'nearest' but dropped the bounded scope.
            if not nearest_scope_missing(query, policy) and nearest_scope_missing(
                slot["question"], policy
            ):
                slot["question"] = query
        return result
    eligible = [
        i
        for i, slot in enumerate(result)
        if slot["evidence_type"] in {"historical", "mixed"}
        and slot.get("aspect") not in {"construction", "restoration", "reconstruction"}
        and not any(
            normalized_text(term) in normalized_text(slot["question"])
            for terms in policy.history_facets.values()
            for term in terms
        )
    ]
    if len(eligible) == 1:
        result[eligible[0]]["question"] = query
    else:
        result.append(
            {
                "slot_id": stable_id("slot", {"relation": "nearest", "question": query}),
                "question": query,
                "evidence_type": "mixed",
            }
        )
    return result


def clauses(query):
    return [
        normalized_text(part)
        for part in re.split(
            r"[,;.!?\n]|\b(?:và|rồi|sau đó|đồng thời|and|then)\b", query, flags=re.IGNORECASE
        )
        if part.strip()
    ]


def requires_certainty(query, policy):
    for clause in clauses(query):
        for term in policy.certainty_terms:
            term = normalized_text(term)
            for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", clause):
                prefix = " ".join(clause[: match.start()].split()[-6:])
                if not any(
                    normalized_text(negation) in prefix for negation in policy.certainty_negations
                ):
                    return True
    return False


def response_is_unknown(context, policy):
    if context.get("response_type") == "unknown":
        return True
    if context.get("selected_candidate"):
        return False
    answer = normalized_text(context.get("answer", ""))
    return bool(answer) and answer in {normalized_text(text) for text in policy.unknown_answers}


def asks_han_reading(text):
    value = normalized_text(text)
    return bool(
        re.search(r"\b(?:doc|dich|phien am|phien doc)\b.*\b(?:han|nom|hoanh phi|cau doi)\b", value)
    )


def mixed_han_request(query):
    supported = r"\b(?:mo ta|kien truc|nhan dien|lich su|khoi dung|trung tu|cong trinh nao|dia diem|o dau)\b"
    return any(not asks_han_reading(part) and re.search(supported, part) for part in clauses(query))


def atomic_slots(slots, query, policy):
    """Split common compound event questions; do not turn an explicit OR into an AND."""
    result = []
    original = normalized_text(query)
    alternative = bool(re.search(r"\b(?:hoac|or)\b", original))
    for slot in slots:
        facets = [
            key
            for key, terms in policy.history_facets.items()
            if any(normalized_text(term) in original for term in terms)
            and any(normalized_text(term) in normalized_text(slot["question"]) for term in terms)
        ]
        if (
            policy.split_history_slots
            and not alternative
            and len(facets) > 1
            and slot["evidence_type"] == "historical"
        ):
            for facet in facets:
                result.append(
                    {
                        **slot,
                        "slot_id": stable_id("slot", {"parent": slot["slot_id"], "aspect": facet}),
                        "question": policy.facet_questions.get(facet, slot["question"]),
                        "aspect": facet,
                    }
                )
        else:
            result.append(slot)
    return preserve_nearest_condition(result, query, policy)
