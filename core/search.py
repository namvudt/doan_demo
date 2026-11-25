"""Wikipedia retrieval with explicit outcomes; navigation links are not evidence."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus

import requests

from core.entities import DEFAULT_CATALOG, EntityCatalog, mentions
from core.evidence import normalized_text, stable_id
from core.observability import trace_operation
from core.schemas import SourceRecord


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

    def request_timeout(self):
        if self.cancel_check:
            self.cancel_check()
        remaining = self.remaining_seconds() if self.remaining_seconds else self.timeout
        if remaining <= 0:
            raise requests.Timeout("Run deadline reached before source retrieval")
        return min(self.timeout, remaining)

    def search_wikipedia(self, query, limit=2, *, focus_query=None, entity_terms=()):
        api = "https://vi.wikipedia.org/w/api.php"
        response = requests.get(
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
            timeout=self.request_timeout(),
        )
        response.raise_for_status()
        items = response.json().get("query", {}).get("search", [])
        if not items:
            return []
        records = []
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
                and sum(bool(r["snippet"].strip()) for r in records) >= self.policy.max_results
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
                response = requests.get(
                    "https://vi.wikipedia.org/w/api.php",
                    params=params,
                    headers=self.headers,
                    timeout=self.request_timeout(),
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

    def search_heritage(self, monument_hint, query):
        with trace_operation(
            "search.wikipedia",
            "retriever",
            inputs={"query": query, "identified_monument": monument_hint},
        ) as span:
            result = self._search_heritage(monument_hint, query)
            span.outputs = {
                "status": result["status"],
                "source_count": len(result["sources"]),
                "sources": result["sources"],
            }
            if result["error"]:
                span.error = result["error"]
                span.metadata["error_type"] = result["error"]
            return result

    def _search_heritage(self, monument_hint, query):
        if self.policy:
            return self._search_evidence(monument_hint, query)
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

    def _search_evidence(self, monument_hint, query):
        identifier = self.catalog.resolve(monument_hint)
        terms = (
            self.catalog.terms(identifier)
            if identifier
            else _fallback_entity_terms(monument_hint)
        )
        name = terms[0] if terms else ""
        attempts, sources, rejected = [], [], 0
        error = None

        def accept(items):
            nonlocal rejected
            accepted = []
            for source in items:
                if not source.get("snippet", "").strip() or (
                    self.policy.require_entity_mention
                    and terms
                    and not mentions(source["title"] + " " + source["snippet"], terms)
                ):
                    rejected += 1
                    continue
                accepted.append(source)
            return accepted

        try:
            sources = accept(self.curated_sources((name + " " + query).strip(), entity_terms=terms))
            wiki_allowed = any(
                "vi.wikipedia.org" == d or "vi.wikipedia.org".endswith("." + d)
                for d in self.policy.allowed_domains
            )
            if self.policy.wikipedia_enabled and wiki_allowed:
                if self.policy.entity_first and terms:
                    queries = [f'"{term.replace(chr(34), "")}"' for term in terms]
                    # Retry without phrase quoting when the exact phrase produces no relevant sources.
                    queries.append(name)
                else:
                    queries = [(monument_hint + " " + query).strip(), name]
                queries = list(dict.fromkeys(q[:200] for q in queries if q.strip()))
                for keyword in queries[: self.policy.max_queries]:
                    if len(sources) >= self.policy.max_results:
                        break
                    attempts.append(keyword)
                    try:
                        found = self.search_wikipedia(
                            keyword,
                            focus_query=query,
                            entity_terms=terms if self.policy.require_entity_mention else (),
                        )
                        found = accept(found)
                        sources.extend(found)
                        # Relevant sources are sufficient; do not spend another query on unrelated results.
                        if found:
                            break
                    except (requests.RequestException, TimeoutError, ValueError) as exc:
                        error = (
                            "SearchTimeout"
                            if isinstance(exc, (requests.Timeout, TimeoutError))
                            else type(exc).__name__
                        )
                        if self.remaining_seconds and self.remaining_seconds() <= 0:
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
                key=lambda s: (mentions(s["title"], terms), mentions(s["title"], parent_terms)),
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
        }

    def curated_sources(self, query, *, entity_terms=()):
        path = Path(self.policy.corpus_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        if not path.is_file():
            return []
        tokens = set(normalized_text(query).split())
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
                : self.policy.max_results
            ]
        ]


def _fallback_entity_terms(monument_hint):
    raw = (monument_hint or "").strip()
    if not raw:
        return []
    head = raw
    while True:
        match = re.fullmatch(r"(.+?)\s*\(([^()]*)\)\s*", head)
        if not match:
            match = re.fullmatch(r"(.+?)\s+[-–—]\s+(.+)", head)
        if not match:
            match = re.fullmatch(r"(.+?)\s*,\s*(.+)", head)
        if not match:
            break
        candidate = match[1].strip()
        if len(candidate) < 3:
            break
        head = candidate
    return list(dict.fromkeys([head, raw]))


def relevant_passage(text, query, max_chars, *, required_terms=()):
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
            chunks.append((score, position, chunk))
    if not chunks:
        return "", "chars:0:0"
    _, start, snippet = max(chunks, key=lambda c: (c[0], -c[1]))
    return snippet, f"chars:{start}:{start + len(snippet)}"
