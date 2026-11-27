"""Wikipedia retrieval with explicit outcomes; navigation links are not evidence."""

import hashlib
import json
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus

import requests

from core.entities import DEFAULT_CATALOG, EntityCatalog, mentions
from core.evidence import normalized_text, stable_id
from core.observability import trace_operation
from core.relations import country_relation_signal
from core.schemas import SourceRecord

RELATION_RULES = {
    "country": {
        "triggers": ["quốc gia nào", "nước nào", "which country", "what country"],
        "query_terms": ["quốc gia"],
        "coverage_terms": [
            "quốc gia",
            "đất nước",
            "country",
            "nằm ở",
            "nằm tại",
            "thuộc",
            "tỉnh",
            "thành phố",
        ],
    },
    "designation": {
        "triggers": [
            "xếp hạng",
            "hạng di tích",
            "danh hiệu",
            "tình trạng bảo tồn",
            "designation",
            "heritage status",
            "được công nhận",
        ],
        "query_terms": ["xếp hạng di tích"],
        "coverage_terms": [
            "xếp hạng",
            "di tích quốc gia",
            "di tích cấp",
            "di sản thế giới",
            "khu Ramsar",
            "khu dự trữ sinh quyển",
            "designation",
            "national monument",
            "world heritage",
        ],
    },
    "nearest": {
        "triggers": ["gần nhất", "gần", "lân cận", "nearest", "nearby"],
        "query_terms": ["gần nhất khoảng cách"],
        "coverage_terms": [
            "cách",
            "gần nhất",
            "nearest",
            "distance",
        ],
        "coverage_patterns": [
            r"\b(?:cach|khoang cach|distance)\b.{0,180}\b\d+(?:[.,]\d+)?\s*(?:km|met|m|kilomet|kilometer|kilometre)\b",
            r"\b(?:gan nhat|nearest)\b",
        ],
    },
}


class RetrievalBudgetExceeded(RuntimeError):
    """The configured HTTP request cap was reached before the next request."""


def relation_rules(policy):
    """Merge configuration overrides without putting facts or answers into retrieval rules."""
    rules = {name: dict(rule) for name, rule in RELATION_RULES.items()}
    for name, override in getattr(policy, "relation_rules", {}).items():
        rules[name] = {**rules.get(name, {}), **override}
    return rules


def country_question_subject(query):
    """Use an explicit final relation subject, never a deictic label or an inferred answer."""
    clauses = re.split(r"[,;.!?\n]|\b(?:và|and|còn)\b", query, flags=re.IGNORECASE)
    for clause in reversed(clauses):
        match = re.fullmatch(
            r"\s*(.+?)\s+(?:(?:trong|ở)\s+(?:ảnh|hình)\s+)?"
            r"(?:thuộc|nằm ở|nằm trong|ở)\s+(?:quốc gia|nước)\s+nào\s*",
            clause,
            re.IGNORECASE,
        )
        if not match:
            continue
        subject = match[1].strip()
        normalized = normalized_text(subject)
        if (
            not 1 <= len(subject) <= 100
            or re.search(
                r"\b(?:anh|hinh|nay|do|noi|dia danh|dia diem|cong trinh|"
                r"di tich|thanh pho nay|tinh nay|duoc|nam|thuoc|nao)\b",
                normalized,
            )
            or not any(character.isupper() for character in subject)
        ):
            continue
        return subject
    return None


def retrieval_plan(monument_hint, query, policy, catalog, *, subject=None, relation=None):
    rules = relation_rules(policy)
    enabled = getattr(policy, "relation_aware", True)
    if enabled and relation is None:
        relation = next(
            (name for name, rule in rules.items() if mentions(query, rule.get("triggers", []))),
            None,
        )
    if not enabled:
        relation = None
    selected_subject = (
        subject
        or (country_question_subject(query) if relation == "country" else None)
        or monument_hint.strip()
    )
    identifier = catalog.resolve(selected_subject)
    terms = catalog.terms(identifier) if identifier else [selected_subject]
    # A search alias is only a way to find documents; it does not resolve image identity.
    qualified = re.fullmatch(r"(.+?)\s*\([^()]+\)\s*", selected_subject)
    if qualified and not identifier:
        terms.append(qualified[1].strip())
    terms = list(dict.fromkeys(term for term in terms if term.strip()))
    rule = rules.get(relation, {})
    if relation and rule:
        suffix = " ".join(rule.get("query_terms", []))
        queries = [f'"{term.replace(chr(34), "")}" {suffix}'.strip() for term in terms]
        queries.extend(terms)
    elif policy.entity_first and terms:
        queries = [f'"{term.replace(chr(34), "")}"' for term in terms] + terms
    else:
        queries = [(selected_subject + " " + query).strip(), selected_subject]
    return {
        "subject": selected_subject,
        "subject_origin": "explicit"
        if subject
        else "question"
        if selected_subject != monument_hint.strip()
        else "image_candidate",
        "entity_id": identifier,
        "terms": terms,
        "relation": relation,
        "coverage_terms": rule.get("coverage_terms", []),
        "coverage_patterns": rule.get("coverage_patterns", []),
        "queries": list(dict.fromkeys(q[:200] for q in queries if q.strip()))[: policy.max_queries],
    }


def relation_signal(source, plan):
    """Lexical coverage only; semantic verification and quote gates remain mandatory."""
    if not plan["relation"]:
        return True
    text = source.get("snippet", "")
    if plan["relation"] == "country":
        return country_relation_signal(text, subject=plan["terms"])
    if not mentions(text, plan["coverage_terms"]):
        return False
    patterns = plan["coverage_patterns"]
    return not patterns or any(re.search(pattern, normalized_text(text)) for pattern in patterns)


class HeritageSearchEngine:
    def __init__(
        self, timeout=6, remaining_seconds=None, policy=None, entity_catalog=None, cancel_check=None
    ):
        self.timeout = timeout
        self.policy = policy
        self.catalog = EntityCatalog(entity_catalog or DEFAULT_CATALOG) if policy else None
        if policy:
            self.timeout = policy.timeout_seconds
        self.remaining_seconds = remaining_seconds
        self.cancel_check = cancel_check
        self.headers = {"User-Agent": "HeritageVQA/0.2 (research prototype)"}
        self._request_budget = ContextVar(f"retrieval_budget_{id(self)}", default=None)
        # Recovery may supply the preceding search's attempts and remaining run budget.
        # Keep these out of the method signature so existing search adapters still work.
        self.exclude_queries = []
        self.http_request_budget = None

    def _get(self, url, *, params, headers):
        timeout = self.request_timeout()
        budget = self._request_budget.get()
        if budget is not None:
            if budget["used"] >= budget["limit"]:
                raise RetrievalBudgetExceeded("Source retrieval request budget reached")
            budget["used"] += 1
        return requests.get(url, params=params, headers=headers, timeout=timeout)

    def request_timeout(self):
        if self.cancel_check:
            self.cancel_check()
        remaining = self.remaining_seconds() if self.remaining_seconds else self.timeout
        if remaining <= 0:
            raise requests.Timeout("Run deadline reached before source retrieval")
        return min(self.timeout, remaining)

    def search_wikipedia(self, query, limit=2, *, focus_query=None, entity_terms=()):
        api = "https://vi.wikipedia.org/w/api.php"
        response = self._get(
            api,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": self.policy.candidate_limit if self.policy else limit,
                "format": "json",
                "utf8": 1,
            },
            headers=self.headers,
        )
        response.raise_for_status()
        items = response.json().get("query", {}).get("search", [])
        if not items:
            return []
        records = []
        plan = (
            retrieval_plan(
                entity_terms[0] if entity_terms else "",
                focus_query or query,
                self.policy,
                self.catalog,
            )
            if self.policy
            else None
        )
        for page in self._wikipedia_pages(items, entity_terms):
            if "missing" in page or not page.get("extract", "").strip():
                continue
            url = page.get("fullurl") or f"https://vi.wikipedia.org/wiki/{quote(page['title'])}"
            text = page["extract"].strip()
            if self.policy:
                snippet, locator = relevant_passage(
                    text[:60000],
                    focus_query or query,
                    self.policy.max_source_chars,
                    required_terms=() if mentions(page["title"], entity_terms) else entity_terms,
                    preferred_terms=plan["coverage_terms"],
                    relation_subject=entity_terms,
                    relation=plan["relation"],
                )
            else:
                snippet, locator = text[:1200], None
            revision = str(page["lastrevid"]) if page.get("lastrevid") else None
            source_id = (
                "wiki_" + hashlib.sha256(f"{url}:{revision}:{snippet}".encode()).hexdigest()[:16]
            )
            records.append(
                SourceRecord(
                    source_id=source_id,
                    title=page["title"],
                    url=url,
                    type="wiki",
                    snippet=snippet,
                    revision_id=revision,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    **(
                        {
                            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                            "locator": locator,
                            "publisher": "Wikipedia tiếng Việt",
                        }
                        if self.policy
                        else {}
                    ),
                ).model_dump(mode="json")
            )
            if (
                self.policy
                and sum(
                    bool(r["snippet"].strip())
                    and (
                        not getattr(self.policy, "require_relation_coverage", True)
                        or relation_signal(r, plan)
                    )
                    for r in records
                )
                >= self.policy.max_results
            ):
                break
        return records

    def _wikipedia_pages(self, items, entity_terms):
        titles = list(dict.fromkeys(item["title"] for item in items))
        if self.policy:
            identifier = next(
                (self.catalog.resolve(t) for t in entity_terms if self.catalog.resolve(t)), None
            )
            parents = (
                [
                    term
                    for parent in self.catalog.ancestors(identifier)
                    for term in self.catalog.terms(parent)
                ]
                if identifier
                else []
            )
            titles.sort(
                key=lambda title: (
                    normalized_text(title) in {normalized_text(term) for term in entity_terms},
                    mentions(title, entity_terms),
                    mentions(title, parents),
                    bool(re.search(r"\b(?:chua|den|di tich)\b", normalized_text(title))),
                ),
                reverse=True,
            )
            batches = [[title] for title in titles[: self.policy.candidate_limit]]
        else:
            batches = [titles]
        succeeded, last_error = False, None
        for batch in batches:
            params = {
                "action": "query",
                "prop": "extracts|info",
                "inprop": "url",
                "explaintext": 1,
                "titles": "|".join(batch),
                "format": "json",
            }
            if self.policy:
                # TextExtracts only supports multiple articles for intro mode. A present
                # exintro=0 still enables the boolean flag; full text must omit it.
                params["exlimit"] = 1
            else:
                params["exintro"] = 1
            try:
                response = self._get(
                    "https://vi.wikipedia.org/w/api.php",
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                payload = response.json()
                if "error" in payload:
                    raise ValueError("WikipediaAPIError")
                pages = payload.get("query", {}).get("pages", {})
                succeeded = True
                yield from pages.values()
            except (requests.RequestException, TimeoutError, ValueError) as error:
                last_error = error
                if self.remaining_seconds and self.remaining_seconds() <= 0:
                    break
        if last_error is not None and not succeeded:
            raise last_error

    @staticmethod
    def generate_maps_link(monument_name):
        return {
            "title": f"Tìm trên bản đồ: {monument_name}",
            "url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(monument_name)}",
            "type": "maps",
        }

    def search_heritage(self, monument_hint, query, *, subject=None, relation=None):
        """Retrieve sources; optional subject/relation override inferred question intent."""
        token = None
        if self.policy:
            limit = getattr(self.policy, "max_http_requests", 24)
            if self.http_request_budget is not None:
                limit = min(limit, max(0, int(self.http_request_budget)))
            token = self._request_budget.set({"used": 0, "limit": limit})
        try:
            return self._traced_search(monument_hint, query, subject=subject, relation=relation)
        finally:
            if token is not None:
                self._request_budget.reset(token)

    def _traced_search(self, monument_hint, query, *, subject=None, relation=None):
        with trace_operation(
            "search.wikipedia",
            "retriever",
            inputs={"query": query, "identified_monument": monument_hint},
        ) as span:
            result = self._search_heritage(monument_hint, query, subject=subject, relation=relation)
            span.outputs = {
                "status": result["status"],
                "source_count": len(result["sources"]),
                "sources": result["sources"],
            }
            if result["error"]:
                span.error = result["error"]
                span.metadata["error_type"] = result["error"]
            return result

    def _search_heritage(self, monument_hint, query, *, subject=None, relation=None):
        if self.policy:
            return self._search_evidence(monument_hint, query, subject=subject, relation=relation)
        keyword = (monument_hint or query).strip()[:1000]
        navigation = [self.generate_maps_link(keyword)] if monument_hint.strip() else []
        try:
            sources = self.search_wikipedia(keyword)
            status = "success" if sources else "empty"
            error = None
        except (requests.Timeout, TimeoutError):
            sources, status, error = [], "timeout", "SearchTimeout"
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            sources, status, error = [], "error", type(exc).__name__
        context = "\n\n".join(f"[{s['source_id']}] {s['title']}\n{s['snippet']}" for s in sources)
        return {
            "status": status,
            "error": error,
            "keyword_used": keyword,
            "sources": sources,
            "navigation_links": navigation,
            "context_text": context,
        }

    def _search_evidence(self, monument_hint, query, *, subject=None, relation=None):
        plan = retrieval_plan(
            monument_hint, query, self.policy, self.catalog, subject=subject, relation=relation
        )
        identifier, terms = plan["entity_id"], plan["terms"]
        excluded = {keyword.strip() for keyword in self.exclude_queries}
        skipped = [keyword for keyword in plan["queries"] if keyword in excluded]
        queries = [keyword for keyword in plan["queries"] if keyword not in excluded]
        budget = self._request_budget.get()
        name = terms[0] if terms else ""
        attempts, sources, rejected = [], [], 0
        diagnostics = {
            "subject": plan["subject"],
            "subject_origin": plan["subject_origin"],
            "relation": plan["relation"],
            "coverage_method": "lexical_candidate_only",
            "coverage_status": "missing" if plan["relation"] else "not_requested",
            "attempts": [],
            "skipped_queries": skipped,
            "rejected_sources": [],
            "http_requests": 0,
            "http_request_limit": budget["limit"]
            if budget
            else getattr(self.policy, "max_http_requests", 24),
            "stop_reason": None,
        }
        error = None

        def accept(items):
            nonlocal rejected
            accepted = []
            for source in items:
                reason = None
                if not source.get("snippet", "").strip():
                    reason = "empty_passage"
                elif (
                    self.policy.require_entity_mention
                    and terms
                    and not mentions(source["title"] + " " + source["snippet"], terms)
                ):
                    reason = "entity_not_mentioned"
                elif (
                    plan["relation"]
                    and getattr(self.policy, "require_relation_coverage", True)
                    and not relation_signal(source, plan)
                ):
                    reason = "relation_not_covered"
                if reason:
                    rejected += 1
                    diagnostics["rejected_sources"].append(
                        {"source_id": source.get("source_id"), "reason": reason}
                    )
                    continue
                accepted.append(source)
            return accepted

        try:
            if self.cancel_check:
                self.cancel_check()
            sources = accept(self.curated_sources((name + " " + query).strip(), entity_terms=terms))
            wiki_allowed = any(
                "vi.wikipedia.org" == d or "vi.wikipedia.org".endswith("." + d)
                for d in self.policy.allowed_domains
            )
            if self.policy.wikipedia_enabled and wiki_allowed:
                if skipped and not queries:
                    diagnostics["stop_reason"] = "queries_already_attempted"
                for keyword in queries:
                    if len(sources) >= self.policy.max_results:
                        diagnostics["stop_reason"] = "source_limit"
                        break
                    if self.cancel_check:
                        self.cancel_check()
                    attempts.append(keyword)
                    attempt = {"query": keyword, "status": "empty", "found": 0, "accepted": 0}
                    diagnostics["attempts"].append(attempt)
                    try:
                        found = self.search_wikipedia(
                            keyword,
                            focus_query=(query + " " + " ".join(plan["coverage_terms"])).strip(),
                            entity_terms=terms if self.policy.require_entity_mention else (),
                        )
                        attempt["found"] = len(found)
                        found = accept(found)
                        sources.extend(found)
                        attempt["accepted"] = len(found)
                        attempt["status"] = "candidate_found" if found else "no_coverage"
                        # Entity mention alone no longer stops a relation-specific search.
                        if found:
                            diagnostics["stop_reason"] = "candidate_found"
                            break
                    except RetrievalBudgetExceeded:
                        attempt["status"] = "request_budget_exhausted"
                        diagnostics["stop_reason"] = "request_budget_exhausted"
                        error = "RetrievalBudgetExceeded"
                        break
                    except (requests.RequestException, TimeoutError, ValueError) as exc:
                        error = (
                            "SearchTimeout"
                            if isinstance(exc, (requests.Timeout, TimeoutError))
                            else type(exc).__name__
                        )
                        attempt["status"] = "error"
                        attempt["error"] = error
                        if self.remaining_seconds and self.remaining_seconds() <= 0:
                            diagnostics["stop_reason"] = "deadline"
                            break
            sources = list({s["source_id"]: s for s in sources}.values())
            # Prefer documents about the entity, then passages mentioning it within a parent document.
            parent_terms = (
                [
                    term
                    for parent in self.catalog.ancestors(identifier)
                    for term in self.catalog.terms(parent)
                ]
                if identifier
                else []
            )
            sources.sort(
                key=lambda s: (
                    normalized_text(s["title"]) in {normalized_text(term) for term in terms},
                    relation_signal(s, plan),
                    mentions(s["title"], terms),
                    mentions(s["title"], parent_terms),
                ),
                reverse=True,
            )
            sources = sources[: self.policy.max_results]
            status = (
                "success"
                if sources
                else "timeout"
                if error == "SearchTimeout"
                else "error"
                if error
                else "empty"
            )
        except (requests.RequestException, TimeoutError, ValueError, KeyError, TypeError) as exc:
            sources = []
            status = "timeout" if isinstance(exc, (requests.Timeout, TimeoutError)) else "error"
            error = "SearchTimeout" if status == "timeout" else type(exc).__name__
        budget = self._request_budget.get()
        diagnostics["http_requests"] = budget["used"] if budget else 0
        diagnostics["coverage_status"] = (
            "candidate_found"
            if sources and plan["relation"]
            else "missing"
            if plan["relation"]
            else "not_requested"
        )
        diagnostics["stop_reason"] = diagnostics["stop_reason"] or (
            "source_limit" if len(sources) >= self.policy.max_results else "queries_exhausted"
        )
        return {
            "status": status,
            "error": error if not sources else None,
            "keyword_used": attempts[0] if attempts else name or query,
            "sources": sources,
            "navigation_links": [self.generate_maps_link(name)] if name else [],
            "context_text": "\n\n".join(
                f"[{s['source_id']}] {s['title']}\n{s['snippet']}" for s in sources
            ),
            "search_queries": attempts,
            "rejected_source_count": rejected,
            "entity_filter_applied": bool(terms and self.policy.require_entity_mention),
            "retrieval_diagnostics": diagnostics,
        }

    def curated_sources(self, query, *, entity_terms=()):
        path = Path(self.policy.corpus_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        if not path.is_file():
            return []
        tokens = set(normalized_text(query).split())
        plan = retrieval_plan("", query, self.policy, self.catalog)
        ranked = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = SourceRecord.model_validate(json.loads(line))
            if (
                record.annotation_status != "reviewed"
                or record.type == "maps"
                or not record.reviewer
                or not record.reviewed_at
            ):
                continue
            if record.content_hash != hashlib.sha256(record.snippet.encode()).hexdigest():
                continue
            from urllib.parse import urlsplit

            parsed_url = urlsplit(str(record.url))
            host = parsed_url.hostname or ""
            if parsed_url.scheme != "https" or parsed_url.username:
                continue
            if not any(
                host == allowed or host.endswith("." + allowed)
                for allowed in self.policy.allowed_domains
            ):
                continue
            overlap = len(
                tokens & set(normalized_text(record.title + " " + record.snippet).split())
            )
            if overlap:
                # Each returned chunk has a reproducible locator/version, never an invented URL.
                passage, locator = relevant_passage(
                    record.snippet,
                    query,
                    self.policy.max_source_chars,
                    required_terms=() if mentions(record.title, entity_terms) else entity_terms,
                    preferred_terms=plan["coverage_terms"],
                    relation_subject=entity_terms,
                    relation=plan["relation"],
                )
                item = record.model_dump(mode="json")
                item.update(
                    snippet=passage,
                    locator=locator,
                    content_hash=hashlib.sha256(record.snippet.encode()).hexdigest(),
                )
                item["source_id"] = stable_id("web", item)
                ranked.append((overlap, item))
        return [
            item
            for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[
                : max(self.policy.max_results, self.policy.candidate_limit)
            ]
        ]


def relevant_passage(
    text,
    query,
    max_chars,
    *,
    required_terms=(),
    preferred_terms=(),
    relation_subject=(),
    relation=None,
):
    stopwords = {
        "la",
        "va",
        "cua",
        "co",
        "khong",
        "cac",
        "nhung",
        "hay",
        "cho",
        "toi",
        "nay",
        "trong",
        "anh",
        "thong",
        "tin",
        "nao",
        "voi",
        "neu",
        "chua",
        "du",
        "can",
        "cu",
        "the",
    }
    tokens = set(normalized_text(query).split()) - stopwords
    chunks = []
    paragraphs = list(re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text))
    for index, match in enumerate(paragraphs):
        start = match.start()
        value = match.group()
        for offset in range(0, len(value), max_chars):
            position = start + offset
            # Include a heading and its following paragraphs as one contiguous, bounded passage.
            end = paragraphs[min(index + 2, len(paragraphs) - 1)].end()
            chunk = text[
                position : min(
                    position + max_chars, max(position + min(len(value) - offset, max_chars), end)
                )
            ]
            if required_terms and not mentions(chunk, required_terms):
                continue
            score = len(tokens & set(normalized_text(chunk).split()))
            score += 2 * sum(mentions(chunk, [term]) for term in preferred_terms)
            relation_score = int(
                relation == "country" and country_relation_signal(chunk, subject=relation_subject)
            )
            chunks.append((relation_score, score, position, chunk))
    if not chunks:
        return "", "chars:0:0"
    _, _, start, snippet = max(chunks, key=lambda c: (c[0], c[1], -c[2]))
    return snippet, f"chars:{start}:{start + len(snippet)}"
