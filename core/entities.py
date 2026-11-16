"""Conservative entity labels: exact aliases and validated location/parent qualifiers."""

import json
import re
from pathlib import Path

from core.evidence import normalized_text, stable_id

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = "config/heritage/hanoi.entities.json"


def mentions(text, terms):
    normalized = " " + normalized_text(text) + " "
    return any(" " + normalized_text(term) + " " in normalized for term in terms if term.strip())


class EntityCatalog:
    def __init__(self, path=DEFAULT_CATALOG):
        path = Path(path)
        path = path if path.is_absolute() else ROOT / path
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        self.region = data.get("region", "")
        self.entities = {e["entity_id"]: e for e in data.get("entities", [])}
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
        allowed.extend(locations or [self.region])
        remainder = normalized_text(qualifier)
        found = False
        for term in sorted({normalized_text(t) for t in allowed if t}, key=len, reverse=True):
            replacement, count = re.subn(r"(?<!\w)" + re.escape(term) + r"(?!\w)", " ", remainder)
            found |= count > 0
            remainder = " ".join(replacement.split())
        remainder = re.sub(r"\b(?:thuoc|tai)\b", "", remainder).strip()
        return found and not remainder

    def candidates(self, names):
        result = {}
        for name in names:
            if not name.strip():
                continue
            identifier = self.resolve(name)
            entity = self.entities.get(identifier, {})
            key = identifier or stable_id("candidate", normalized_text(name))
            result[key] = {
                "entity_id": key,
                "name": entity.get("name", name),
                "parent_id": entity.get("parent_id"),
                "catalog_status": entity.get("annotation_status", "draft") if entity else "unknown",
                "is_candidate": True,
            }
        return list(result.values())

    def most_specific(self, identifiers):
        ids = set(identifiers)
        leaves = [i for i in ids if not any(i in self.ancestors(other) for other in ids)]
        return leaves[0] if len(leaves) == 1 else None

    def source_mentions(self, candidate, text):
        return mentions(text, self.terms(candidate["entity_id"]) or [candidate["name"]])
