"""Bounded cross-process cache for public retrieval artifacts, never model responses."""

import copy
import hashlib
import json
import math
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from core.schemas import SourceRecord


class SharedRetrievalCache:
    def __init__(
        self,
        path,
        *,
        ttl_seconds=300,
        max_entries=512,
        max_bytes=16_000_000,
        clock=time.time,
    ):
        if ttl_seconds <= 0 or max_entries < 1 or max_bytes < 1024:
            raise ValueError("Cache limits must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.clock = clock
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(f"PRAGMA journal_size_limit={int(max_bytes)}")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS retrieval_cache ("
                "namespace TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL, "
                "size INTEGER NOT NULL, expires REAL NOT NULL, touched REAL NOT NULL, "
                "PRIMARY KEY(namespace,key))"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=3)
        try:
            connection.execute("PRAGMA busy_timeout=3000")
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, namespace, key):
        now = self.clock()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload,expires FROM retrieval_cache WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
            if row is None:
                return None
            if row[1] <= now:
                connection.execute(
                    "DELETE FROM retrieval_cache WHERE namespace=? AND key=? AND expires<=?",
                    (namespace, key, now),
                )
                return None
            connection.execute(
                "UPDATE retrieval_cache SET touched=? WHERE namespace=? AND key=?",
                (now, namespace, key),
            )
            try:
                return json.loads(row[0])
            except (TypeError, ValueError):
                connection.execute(
                    "DELETE FROM retrieval_cache WHERE namespace=? AND key=?", (namespace, key)
                )
                return None

    def put(self, namespace, key, value):
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        size = len(payload.encode("utf-8"))
        if size > self.max_bytes:
            return False
        now = self.clock()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM retrieval_cache WHERE expires<=?", (now,))
            connection.execute(
                "INSERT INTO retrieval_cache(namespace,key,payload,size,expires,touched) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET "
                "payload=excluded.payload,size=excluded.size,expires=excluded.expires,"
                "touched=excluded.touched",
                (namespace, key, payload, size, now + self.ttl_seconds, now),
            )
            while True:
                count, total = connection.execute(
                    "SELECT count(*),coalesce(sum(size),0) FROM retrieval_cache"
                ).fetchone()
                if count <= self.max_entries and total <= self.max_bytes:
                    break
                connection.execute(
                    "DELETE FROM retrieval_cache WHERE rowid IN "
                    "(SELECT rowid FROM retrieval_cache ORDER BY touched,rowid LIMIT 1)"
                )
        return True

    def invalidate(self, namespace=None):
        with self.connect() as connection:
            if namespace is None:
                connection.execute("DELETE FROM retrieval_cache")
            else:
                connection.execute("DELETE FROM retrieval_cache WHERE namespace=?", (namespace,))

    def stats(self):
        with self.connect() as connection:
            count, size = connection.execute(
                "SELECT count(*),coalesce(sum(size),0) FROM retrieval_cache WHERE expires>?",
                (self.clock(),),
            ).fetchone()
        return {"entries": count, "payload_bytes": size}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def file_revision(paths):
    """Include corpus/entity content versions in keys; a withdrawal changes the key."""
    return digest(
        {
            str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if Path(path).is_file()
            else None
            for path in paths
        }
    )


def public_search_payload(value):
    """Whitelist source fields. Do not persist query echoes, credentials or model artifacts."""
    if not isinstance(value, dict) or value.get("status") != "success" or value.get("error"):
        return None
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        return None
    safe = []
    try:
        for source in sources:
            parsed = SourceRecord.model_validate(source)
            url = urlsplit(str(parsed.url))
            if (
                not parsed.snippet.strip()
                or parsed.type == "maps"
                or parsed.annotation_status == "draft"
                or url.username
                or url.password
                or any(
                    name.casefold()
                    in {
                        "key",
                        "token",
                        "api_key",
                        "access_token",
                        "auth",
                        "signature",
                        "password",
                        "credential",
                    }
                    for name, _ in parse_qsl(url.query)
                )
            ):
                return None
            safe.append(parsed.model_dump(mode="json"))
    except (TypeError, ValueError):
        return None
    return {
        "status": "success",
        "error": None,
        "sources": safe,
        "navigation_links": [],
        "context_text": "\n\n".join(
            f"[{item['source_id']}] {item['title']}\n{item['snippet']}" for item in safe
        ),
        "rejected_source_count": int(value.get("rejected_source_count", 0)),
        "entity_filter_applied": bool(value.get("entity_filter_applied", False)),
    }


class CachedSearchEngine:
    """Wrap a retriever, never KnowledgeAgent.retrieve (which also calls an LLM).

    revision_provider must include current publication/withdrawal and entity
    revisions. It is consulted on every hit, independently of the TTL.
    """

    def __init__(self, engine, cache, *, revision_provider, namespace="retrieval-v1"):
        self.engine = engine
        self.cache = cache
        self.revision_provider = revision_provider
        self.namespace = namespace
        self.last_cache = {"hit": False, "status": "not_used"}

    def __getattr__(self, name):
        return getattr(self.engine, name)

    def search_heritage(self, monument_hint, query):
        started = time.monotonic()
        revision = self.revision_provider()
        key = digest({"hint": monument_hint, "query": query, "revision": revision})
        cache_available = True
        try:
            value = self.cache.get(self.namespace, key)
        except (sqlite3.Error, OSError, ValueError):
            value, cache_available = None, False
        if value is not None and revision == self.revision_provider():
            self.last_cache = {"hit": True, "status": "hit"}
            return {
                **copy.deepcopy(value),
                "keyword_used": monument_hint,
                "search_queries": [],
                "retrieval_cache": {"hit": True, "duration": time.monotonic() - started},
            }
        result = self.engine.search_heritage(monument_hint=monument_hint, query=query)
        safe = public_search_payload(result)
        stored = False
        if cache_available and safe is not None and revision == self.revision_provider():
            try:
                stored = self.cache.put(self.namespace, key, safe)
            except (sqlite3.Error, OSError, ValueError):
                cache_available = False
        self.last_cache = {
            "hit": False,
            "status": "stored" if stored else "not_cacheable" if cache_available else "unavailable",
        }
        return {
            **result,
            "retrieval_cache": {"hit": False, "duration": time.monotonic() - started},
        }


def percentiles(values):
    values = sorted(
        float(item) for item in values if item is not None and math.isfinite(float(item))
    )
    if not values:
        return {"count": 0, "p50_seconds": None, "p95_seconds": None}
    return {
        "count": len(values),
        "p50_seconds": values[max(0, math.ceil(len(values) * 0.5) - 1)],
        "p95_seconds": values[max(0, math.ceil(len(values) * 0.95) - 1)],
    }
