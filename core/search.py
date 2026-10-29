"""Wikipedia retrieval with explicit outcomes; navigation links are not evidence."""

import hashlib
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus

import requests

from core.schemas import SourceRecord


class HeritageSearchEngine:
    def __init__(self, timeout=6, remaining_seconds=None):
        self.timeout = timeout
        self.remaining_seconds = remaining_seconds
        self.headers = {"User-Agent": "HeritageVQA/0.2 (research prototype)"}

    def request_timeout(self):
        remaining = self.remaining_seconds() if self.remaining_seconds else self.timeout
        if remaining <= 0:
            raise requests.Timeout("Run deadline reached before source retrieval")
        return min(self.timeout, remaining)

    def search_wikipedia(self, query, limit=2):
        api = "https://vi.wikipedia.org/w/api.php"
        response = requests.get(
            api,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
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
        response = requests.get(
            api,
            params={
                "action": "query",
                "prop": "extracts|info",
                "inprop": "url",
                "exintro": 1,
                "explaintext": 1,
                "titles": "|".join(item["title"] for item in items),
                "format": "json",
            },
            headers=self.headers,
            timeout=self.request_timeout(),
        )
        response.raise_for_status()
        records = []
        for page in response.json().get("query", {}).get("pages", {}).values():
            if "missing" in page or not page.get("extract", "").strip():
                continue
            url = page.get("fullurl") or f"https://vi.wikipedia.org/wiki/{quote(page['title'])}"
            snippet = page["extract"].strip()[:1200]
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
                ).model_dump(mode="json")
            )
        return records

    @staticmethod
    def generate_maps_link(monument_name):
        return {
            "title": f"Tìm trên bản đồ: {monument_name}",
            "url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(monument_name)}",
            "type": "maps",
        }

    def search_heritage(self, monument_hint, query):
        keyword = (monument_hint or query).strip()
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
