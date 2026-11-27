"""Typed entity labels, explicit question subjects and conservative source binding.

Catalog labels help match names; they never constitute historical answer evidence.
Question subjects and candidates recognized in an image remain separate concepts.
"""

import json
import re
from pathlib import Path

from core.evidence import normalized_text, stable_id

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = "config/heritage/hanoi.entities.json"
DEFAULT_NON_CANDIDATE_TYPES = frozenset({"country", "administrative_area", "answer_value"})
DEFAULT_ANSWER_VALUES = frozenset(
    {"co", "khong", "yes", "no", "true", "false", "khong biet", "unknown", "none", "null"}
)
DEFAULT_SUBJECT_PATTERNS = (
    # Anchor at a clause boundary so "A nằm ở B, và B thuộc nước nào" selects B.
    r"(?:^|[,;]\s*(?:và\s+)?)\s*(?P<subject>[^,;!?\n]+?)"
    r"(?:\s+trong\s+(?:ảnh|hình)(?:\s+này)?)?\s+thuộc\s+(?:quốc gia|nước)\b",
    r"(?:^|[,;]\s*(?:và\s+)?)\s*(?P<subject>[^,;!?\n]+?)"
    r"(?:\s+trong\s+(?:ảnh|hình)(?:\s+này)?)?\s+"
    r"(?:nằm|tọa lạc)\s+(?:ở|tại)\s+(?:quốc gia|nước)\s+nào\b",
    r"^\s*(?P<subject>[^,;!?\n]+?)\s+(?:được\s+)?"
    r"(?:khởi dựng|xây dựng|trùng tu|tái dựng|thành lập)\b",
)


def _load_catalog(path, active=()):
    """Extend label catalogs without copying or silently recursing through cycles."""
    path = path.resolve()
    if path in active:
        raise ValueError("Entity catalog inheritance cycle")
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    parents = data.get("extends", [])
    if isinstance(parents, str):
        parents = [parents]
    merged, entities = {}, {}
    for parent in parents:
        parent_path = Path(parent)
        parent_path = parent_path if parent_path.is_absolute() else path.parent / parent_path
        inherited = _load_catalog(parent_path, (*active, path))
        entities.update({e["entity_id"]: e for e in inherited.get("entities", [])})
        merged.update({k: v for k, v in inherited.items() if k not in {"entities", "extends"}})
    entities.update(
        {
            e["entity_id"]: {
                **e,
                "_catalog_region": data.get("region", merged.get("region", "")),
            }
            for e in data.get("entities", [])
        }
    )
    merged.update({k: v for k, v in data.items() if k not in {"entities", "extends"}})
    merged["entities"] = list(entities.values())
    return merged


def mentions(text, terms):
    normalized = " " + normalized_text(text) + " "
    return any(" " + normalized_text(term) + " " in normalized for term in terms if term.strip())


class EntityCatalog:
    def __init__(self, path=DEFAULT_CATALOG):
        path = Path(path)
        path = path if path.is_absolute() else ROOT / path
        data = _load_catalog(path)
        self.region = data.get("region", "")
        self.entities = {e["entity_id"]: e for e in data.get("entities", [])}
        self.non_candidate_types = set(data.get("non_candidate_types", DEFAULT_NON_CANDIDATE_TYPES))
        self.answer_values = DEFAULT_ANSWER_VALUES | {
            normalized_text(value) for value in data.get("answer_values", [])
        }
        self.subject_patterns = data.get("subject_patterns", DEFAULT_SUBJECT_PATTERNS)
        self.index = {}
        for identifier in self.entities:
            for name in self.terms(identifier):
                self.index.setdefault(normalized_text(name), set()).add(identifier)

    def terms(self, identifier):
        entity = self.entities.get(identifier, {})
        return list(dict.fromkeys([entity["name"], *entity.get("aliases", [])])) if entity else []

    def ancestors(self, identifier):
        result = []
        parent = self.entities.get(identifier, {}).get("parent_id")
        while parent in self.entities and parent not in result and parent != identifier:
            result.append(parent)
            parent = self.entities[parent].get("parent_id")
        return result

    def _exact(self, name):
        ids = self.index.get(normalized_text(name), set())
        return next(iter(ids)) if len(ids) == 1 else None

    def resolve(self, name):
        exact = self._exact(name)
        if exact:
            return exact
        # Never pick a nested component from a substring of a site's name.
        match = re.fullmatch(r"(.+?)\s*\(([^()]*)\)\s*", name.strip())
        if not match:
            match = re.fullmatch(r"(.+?)\s*[-–—,]\s*(.+)", name.strip())
        if not match:
            return None
        ids = self.index.get(normalized_text(match[1]), set())
        matched = [
            identifier for identifier in ids if self._qualifier_matches(identifier, match[2])
        ]
        return matched[0] if len(matched) == 1 else None

    def _qualifier_matches(self, identifier, qualifier):
        locations = list(self.entities[identifier].get("localities", []))
        allowed = []
        for ancestor in self.ancestors(identifier):
            allowed.extend(self.terms(ancestor))
            if not locations:
                locations.extend(self.entities[ancestor].get("localities", []))
        allowed.extend(locations or [self.entities[identifier].get("_catalog_region", self.region)])
        remainder = normalized_text(qualifier)
        found = False
        for term in sorted({normalized_text(t) for t in allowed if t}, key=len, reverse=True):
            replacement, count = re.subn(r"(?<!\w)" + re.escape(term) + r"(?!\w)", " ", remainder)
            found |= count > 0
            remainder = " ".join(replacement.split())
        remainder = re.sub(r"\b(?:thuoc|tai)\b", "", remainder).strip()
        return found and not remainder

    def is_answer_value(self, name):
        value = normalized_text(name)
        identifier = self.resolve(name)
        return (
            value in self.answer_values
            or bool(re.fullmatch(r"[\d\s.,%+\-/]+", name.strip()))
            or self.entities.get(identifier, {}).get("entity_type") == "answer_value"
        )

    def candidates(self, names, *, allowed_types=None, reject_answer_values=True):
        """Return image candidates, excluding answers and broad administrative labels.

        Passing explicit allowed_types also permits non-visual subjects (e.g. a
        province) when the caller is resolving the subject of a named question.
        """
        result = {}
        for name in names:
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            identifier = self.resolve(name)
            entity = self.entities.get(identifier, {})
            entity_type = entity.get("entity_type", "heritage_site" if entity else "unknown")
            if reject_answer_values and self.is_answer_value(name):
                continue
            if allowed_types is not None:
                if entity_type not in allowed_types:
                    continue
            elif entity_type in self.non_candidate_types:
                continue
            key = identifier or stable_id("candidate", normalized_text(name))
            result[key] = {
                "entity_id": key,
                "name": entity.get("name", name),
                "entity_type": entity_type,
                "parent_id": entity.get("parent_id"),
                "catalog_status": entity.get("annotation_status", "draft") if entity else "unknown",
                "is_candidate": True,
            }
        return list(result.values())

    def most_specific(self, identifiers):
        ids = set(identifiers)
        leaves = [i for i in ids if not any(i in self.ancestors(other) for other in ids)]
        return leaves[0] if len(leaves) == 1 else None

    def source_mentions(self, candidate, text, *, independent=False):
        terms = self.terms(candidate["entity_id"]) or [candidate["name"]]
        kind = candidate.get("entity_type") or self.entities.get(candidate["entity_id"], {}).get(
            "entity_type", "unknown"
        )
        if independent and kind in {"place", "administrative_area"}:
            # The locality's name inside "Nhà tù Sơn La" or "Vườn quốc gia
            # Mũi Cà Mau" is not a separate mention of the province/cape.
            # Keep retrieval broad, but require an independent name for binding.
            normalized = " " + normalized_text(text) + " "
            longer_names = {
                normalized_text(name)
                for identifier in self.entities
                if identifier != candidate["entity_id"]
                for name in self.terms(identifier)
                if mentions(name, terms)
                and normalized_text(name) not in {normalized_text(term) for term in terms}
            }
            for name in sorted(longer_names, key=len, reverse=True):
                normalized = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", " ", normalized)
            text = normalized
        return mentions(text, terms)

    def source_entity(self, candidates, text, *, selected_entity_id=None):
        """Bind a source only to an actually mentioned, non-answer subject.

        A selected question subject can disambiguate a source mentioning both a
        landmark and its locality. Merely mentioning a country cannot make it a
        competing monument candidate. Distinct overlapping places stay distinct.
        """
        matches = []
        for candidate in candidates:
            identifier = candidate["entity_id"]
            kind = candidate.get("entity_type") or self.entities.get(identifier, {}).get(
                "entity_type", "unknown"
            )
            if kind in {"country", "answer_value"} or self.is_answer_value(candidate["name"]):
                continue
            if self.source_mentions(candidate, text, independent=True):
                matches.append(identifier)
        matches = list(dict.fromkeys(matches))
        if selected_entity_id in matches:
            return selected_entity_id
        return matches[0] if len(matches) == 1 else None

    def extract_subject(self, query, *, patterns=None, enabled=True):
        """Extract an explicit named subject, without claiming the photo depicts it.

        Relation templates must contain a named 'subject' regex group. A query
        that proposes a hypothetical identification is deliberately not promoted
        into a named subject. No answer facts are returned from the catalog.
        """
        if not enabled or re.search(
            r"\b(?:co the la|co phai|phai chang|hinh nhu|co ve la)\b", normalized_text(query)
        ):
            return None
        for pattern in patterns or self.subject_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if not match or "subject" not in match.groupdict():
                continue
            name = match.group("subject").strip(" \t\"'“”‘’:")
            name = re.sub(r"\s+trong\s+(?:ảnh|hình)(?:\s+này)?$", "", name, flags=re.I)
            name = re.sub(
                r"^(?:(?:hãy|vui lòng|xin)\s+)?(?:cho\s+(?:tôi\s+)?biết|giới thiệu về)\s*",
                "",
                name,
                flags=re.I,
            )
            name = re.sub(r"^(?:địa danh|địa điểm|di tích)\s+", "", name, flags=re.I)
            normalized = normalized_text(name)
            if (
                not normalized
                or normalized
                in {
                    "day",
                    "do",
                    "no",
                    "cong trinh",
                    "di tich",
                    "dia danh",
                    "dia diem",
                    "chua",
                    "ngoi chua",
                    "den",
                    "ngoi den",
                    "nha tu",
                    "hon dao",
                    "dao",
                    "thanh pho",
                    "tinh",
                    "khu vuc",
                    "canh vat",
                    "buc anh",
                    "hinh anh",
                }
                or re.search(r"\b(?:nay|kia|nao|trong anh|trong hinh)\b", normalized)
                or self.is_answer_value(name)
            ):
                continue
            identifier = self.resolve(name)
            if identifier is None and re.search(
                r"^(?:hay|vui long|xin|cho toi|cho biet|neu|mo ta|gioi thieu|phan tich|"
                r"noi gan|noi nay|o day|gan day|thong tin|cau hoi|khi nao|bao gio)\b"
                r"|\b(?:khoi dung|xay dung|trung tu|tai dung|khi nao|nam nao)\b",
                normalized,
            ):
                continue
            # Unknown names need an explicit proper-name signal. This prevents
            # "ngôi chùa" and other descriptions becoming asserted subjects.
            if identifier is None:
                words = name.split()
                generic_opening = normalized_text(words[0]) in {
                    "ngoi",
                    "nha",
                    "chua",
                    "den",
                    "dinh",
                    "dao",
                    "hon",
                    "toa",
                    "cong",
                    "khu",
                    "dia",
                    "vung",
                    "thanh",
                    "tinh",
                    "noi",
                }
                proper_words = words[1:] if generic_opening else words
                if not any(token[:1].isupper() for token in proper_words):
                    continue
            values = self.candidates(
                [name],
                allowed_types={
                    "heritage_site",
                    "place",
                    "protected_area",
                    "unknown",
                    "administrative_area",
                },
            )
            if values:
                return {**values[0], "subject_basis": "explicit_question"}
        return None
