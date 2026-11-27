"""Conservative relation checks supplement model verdicts and exact-quotation gates.

These rules check a small set of explicit linguistic constructions. Passing is not
a guarantee of truth; unsupported constructions remain unverified. Rules contain
relation syntax, never a destination's answer or a benchmark reference.
"""

import re

from core.evidence import normalized_text

GEO_PREFIX = r"(?:(?:tinh|thanh pho|huyen|huyen dao|dac khu|xa|phuong|thi xa|dao|quan dao|vung|khu bao ton|vuon quoc gia|province|city|island|district|special administrative region)\s+)?"
GEO_CLASS = (
    r"(?:tinh|thanh pho|huyen dao|huyen|dac khu|xa|phuong|thi xa|dao|quan dao|vung|khu vuc|"
    r"khu bao ton|vuon quoc gia|province|city|island|archipelago|district|special administrative region)"
)
LINK = r"(?:thuoc(?:\s+(?:quoc gia|dat nuoc|nuoc|chu quyen))?|nam\s+(?:o|tai|trong)|toa lac\s+(?:o|tai)|is\s+(?:located\s+)?in|belongs to)"

DEFAULT_SOURCE_RELATION_RULES = {
    "country": {
        "question_patterns": [r"\b(?:quoc gia nao|nuoc nao|which country|what country)\b"],
        "claim_object_patterns": [
            rf"^{GEO_PREFIX}{{subject}}\s+{LINK}\s+(?P<object>[\w ]+)$",
            rf"^{GEO_PREFIX}{{subject}}\s+la\s+(?:mot\s+)?{GEO_CLASS}\b.{{0,100}}?\s+(?:cua|thuoc)\s+(?P<object>[\w ]+)$",
        ],
        "quote_patterns": [
            rf"^{GEO_PREFIX}{{subject}}\s+{LINK}\s+(?:(?:phia|mien|vung|khu vuc|cuc|bac|nam|dong|tay|noi dia|cua)\s+){{0,8}}{{object}}$",
            rf"^{GEO_PREFIX}{{subject}}\s+(?:la|is)\s+(?:mot\s+|an?\s+|the\s+)?{GEO_CLASS}\b.{{0,140}}?\s+(?:cua|thuoc|of|in)\s+{{object}}$",
            rf"^{GEO_PREFIX}{{subject}}\s+la\s+(?:mot\s+)?{GEO_CLASS}\s+(?:(?:mien nui|vung cao|dong bang|ven bien|mien bac|mien nam|phia bac|phia nam)\s+){{0,6}}(?:nam\s+)?(?:o|tai|thuoc)\s+.{{0,80}}?{{object}}$",
        ],
        "negation_patterns": [r"\b(?:khong|chua|not|never)\b"],
    },
    "nearest": {
        "question_patterns": [r"\b(?:gan\b.{0,100}\bnhat|nearest|closest)\b"],
        "scope_patterns": [
            r"\b(?:trong so|trong danh sach|trong tap|trong pham vi|among|within|of the listed)\b"
        ],
        "quote_patterns": [r"\b(?:gan nhat|nearest|closest)\b"],
        "claim_object_patterns": [
            r"^(?P<object>[\w ]+?)\s+(?:la\s+)?(?:noi\s+|dia danh\s+|diem den\s+)?(?:o\s+)?(?:gan nhat|nearest to|closest to)\s+{subject}$",
            r"^(?P<object>[\w ]+?)\s+(?:la\s+)?(?:noi\s+|dia danh\s+|diem den\s+)?gan\s+{subject}\s+nhat$",
            r"^{subject}\s+(?:co\s+)?(?:noi\s+|dia danh\s+|diem den\s+)?gan nhat\s+(?:la\s+)?(?P<object>[\w ]+)$",
        ],
        "link_patterns": [
            r"\b{object}\s+(?:la\s+)?(?:noi\s+|dia danh\s+|diem den\s+)?(?:o\s+)?(?:gan nhat|nearest to|closest to)\s+{subject}\b",
            r"\b{object}\s+(?:la\s+)?(?:noi\s+|dia danh\s+|diem den\s+)?gan\s+{subject}\s+nhat\b",
            r"\b{subject}\s+(?:co\s+)?(?:noi\s+|dia danh\s+|diem den\s+)?gan nhat\s+(?:la\s+)?{object}\b",
        ],
    },
}


def merged_relation_rules(rules=None):
    merged = {name: dict(rule) for name, rule in DEFAULT_SOURCE_RELATION_RULES.items()}
    for name, override in (rules or {}).items():
        merged[name] = {**merged.get(name, {}), **override}
    return merged


def question_relation(question, rules=None):
    text = normalized_text(question)
    return next(
        (
            name
            for name, rule in merged_relation_rules(rules).items()
            if any(re.search(pattern, text) for pattern in rule.get("question_patterns", []))
        ),
        None,
    )


def _subject_pattern(subject):
    if isinstance(subject, dict):
        names = [subject.get("name", ""), *subject.get("aliases", [])]
    elif isinstance(subject, (list, tuple)):
        names = list(subject)
    else:
        names = [subject or ""]
    names = {normalized_text(name) for name in names if isinstance(name, str) and name.strip()}
    return (
        "(?:" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + ")"
        if names
        else None
    )


def _sentences(text, *, include_clauses=True):
    # Keep subjects and relations in one sentence. Splitting before normalization
    # prevents a valid subject in one sentence legitimizing another sentence.
    sentences = [part for part in re.split(r"[.!?;\n]+", text) if part.strip()]
    if include_clauses:
        sentences.extend(clause for sentence in list(sentences) for clause in sentence.split(","))
    return list(dict.fromkeys(normalized_text(part) for part in sentences if part.strip()))


def _render(pattern, subject, object_pattern):
    # Replace literal placeholders only: regex quantifiers such as {0,8} stay intact.
    return pattern.replace("{subject}", subject).replace("{object}", object_pattern)


def country_relation_signal(quotation, *, subject, rules=None):
    """Whether a passage contains an explicit subject-to-country construction."""
    subject_pattern = _subject_pattern(subject)
    if not subject_pattern:
        return False
    rule = merged_relation_rules(rules)["country"]
    for sentence in _sentences(quotation):
        if any(re.search(pattern, sentence) for pattern in rule.get("negation_patterns", [])):
            continue
        if any(
            re.search(_render(pattern, subject_pattern, r"[\w ]+"), sentence)
            for pattern in rule.get("quote_patterns", [])
        ):
            return True
    return False


def validate_source_relation(claim_text, quotation, *, subject, question, rules=None):
    """Return an error code when an explicit question relation lacks quoted support.

    ``subject`` accepts a name, alias list, or ``{"name": ..., "aliases": [...]}``.
    The caller still validates source identity, exact quote containment and slot
    coverage. Unknown relations are left to those existing checks and the verifier.
    """
    merged = merged_relation_rules(rules)
    relation = question_relation(question, merged)
    if relation is None:
        return None
    rule = merged[relation]
    subject_pattern = _subject_pattern(subject)
    if relation == "nearest":
        if not any(
            re.search(pattern, normalized_text(question))
            for pattern in rule.get("scope_patterns", [])
        ):
            return "nearest_scope_required"
        if not all(
            any(
                re.search(pattern, normalized_text(text))
                for pattern in rule.get("quote_patterns", [])
            )
            for text in (claim_text, quotation)
        ):
            return "nearest_relation_required"
        if not subject_pattern:
            return "nearest_relation_required"
        for sentence in _sentences(claim_text):
            for pattern in rule.get("claim_object_patterns", []):
                match = re.search(_render(pattern, subject_pattern, r"[\w ]+"), sentence)
                if not match or not match.groupdict().get("object"):
                    continue
                for quote in _sentences(quotation):
                    if any(
                        re.search(_render(link, subject_pattern, re.escape(match["object"])), quote)
                        for link in rule.get("link_patterns", [])
                    ):
                        return None
        return "nearest_relation_required"
    if not subject_pattern:
        return "relation_quote_mismatch"
    objects = set()
    for sentence in _sentences(claim_text):
        for pattern in rule.get("claim_object_patterns", []):
            match = re.search(_render(pattern, subject_pattern, r"[\w ]+"), sentence)
            if match and match.groupdict().get("object"):
                objects.add(match["object"])
    if not objects:
        return "relation_quote_mismatch"
    for sentence in _sentences(quotation):
        if any(re.search(pattern, sentence) for pattern in rule.get("negation_patterns", [])):
            continue
        for obj in objects:
            if any(
                re.search(_render(pattern, subject_pattern, re.escape(obj)), sentence)
                for pattern in rule.get("quote_patterns", [])
            ):
                return None
    return "relation_quote_mismatch"
