from concurrent.futures import ThreadPoolExecutor

from core.retrieval_cache import (
    CachedSearchEngine,
    SharedRetrievalCache,
    file_revision,
    percentiles,
)


def payload(source):
    return {
        "status": "success",
        "error": None,
        "sources": [source],
        "context_text": "public text",
        "keyword_used": "private user question must not be persisted",
        "authorization": "not-a-real-token",
    }


def test_shared_cache_survives_instances_and_invalidates_before_withdrawal(tmp_path, source):
    database = tmp_path / "cache.sqlite"
    revision = ["published-v1"]

    class Engine:
        calls = 0

        def search_heritage(self, **kwargs):
            self.calls += 1
            return (
                payload(source)
                if revision[0] == "published-v1"
                else {"status": "empty", "sources": []}
            )

    engine = Engine()
    first = CachedSearchEngine(
        engine, SharedRetrievalCache(database), revision_provider=lambda: revision[0]
    )
    assert first.search_heritage("Test monument", "year?")["retrieval_cache"]["hit"] is False
    second = CachedSearchEngine(
        engine, SharedRetrievalCache(database), revision_provider=lambda: revision[0]
    )
    assert second.search_heritage("Test monument", "year?")["retrieval_cache"]["hit"] is True
    assert engine.calls == 1
    revision[0] = "withdrawn-v2"
    assert second.search_heritage("Test monument", "year?")["status"] == "empty"
    assert engine.calls == 2
    # Only the whitelisted public source fields were persisted, never auth/query echoes.
    with second.cache.connect() as connection:
        stored = connection.execute("SELECT payload FROM retrieval_cache").fetchone()[0]
    assert "private user question" not in stored
    assert "authorization" not in stored and "not-a-real-token" not in stored


def test_ttl_size_lru_and_concurrent_writers_are_bounded(tmp_path):
    now = [10.0]
    cache = SharedRetrievalCache(
        tmp_path / "cache.sqlite",
        ttl_seconds=5,
        max_entries=3,
        max_bytes=1600,
        clock=lambda: now[0],
    )
    cache.put("n", "expired", {"value": "x"})
    now[0] = 16
    assert cache.get("n", "expired") is None
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda i: cache.put("n", str(i), {"value": "x" * 100}), range(16)))
    assert cache.stats()["entries"] <= 3
    assert cache.stats()["payload_bytes"] <= 1600
    assert not cache.put("n", "too-large", {"value": "x" * 2000})
    cache.invalidate("n")
    assert cache.stats()["entries"] == 0


def test_errors_draft_sources_and_credential_urls_are_never_cached(tmp_path, source):
    class Engine:
        def __init__(self, result):
            self.result, self.calls = result, 0

        def search_heritage(self, **kwargs):
            self.calls += 1
            return self.result

    for index, result in enumerate(
        [
            {"status": "timeout", "error": "SearchTimeout", "sources": []},
            payload({**source, "annotation_status": "draft"}),
            payload({**source, "url": "https://username:password@example.test/private"}),
            payload({**source, "url": "https://example.test/private?access_token=not-real"}),
        ]
    ):
        cache = SharedRetrievalCache(tmp_path / f"cache-{index}.sqlite")
        engine = Engine(result)
        wrapped = CachedSearchEngine(engine, cache, revision_provider=lambda: "v1")
        wrapped.search_heritage("test", "question")
        wrapped.search_heritage("test", "question")
        assert engine.calls == 2 and cache.stats()["entries"] == 0


def test_unavailable_cache_falls_back_and_racing_withdrawal_cannot_hit(tmp_path, source):
    import sqlite3

    class Engine:
        calls = 0

        def search_heritage(self, **kwargs):
            self.calls += 1
            return payload(source)

    class BrokenCache:
        def get(self, *args):
            raise sqlite3.DatabaseError("synthetic unavailable cache")

    engine = Engine()
    wrapper = CachedSearchEngine(engine, BrokenCache(), revision_provider=lambda: "v1")
    assert wrapper.search_heritage("test", "question")["status"] == "success"
    assert engine.calls == 1 and wrapper.last_cache["status"] == "unavailable"
    cache = SharedRetrievalCache(tmp_path / "cache.sqlite")
    stable = CachedSearchEngine(engine, cache, revision_provider=lambda: "v1")
    stable.search_heritage("test", "question")
    calls = [0]

    def changed_during_read():
        calls[0] += 1
        return "v1" if calls[0] == 1 else "withdrawn-v2"

    racing = CachedSearchEngine(engine, cache, revision_provider=changed_during_read)
    assert not racing.search_heritage("test", "question")["retrieval_cache"]["hit"]
    assert engine.calls == 3


def test_file_revision_and_latency_percentiles(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    before = file_revision([corpus])
    corpus.write_text("source revision1", encoding="utf-8")
    after = file_revision([corpus])
    assert before != after
    corpus.write_text("source revision2", encoding="utf-8")
    assert file_revision([corpus]) != after
    assert percentiles([3, 1, 2, None]) == {"count": 3, "p50_seconds": 2, "p95_seconds": 3}


def test_tool_executor_does_not_bypass_revision_checks_within_one_run(tmp_path, source, photo):
    from core.tools import ToolExecutor
    from tests.conftest import FakeLLM

    revision = ["published"]

    class Engine:
        def search_heritage(self, **kwargs):
            return (
                payload(source)
                if revision[0] == "published"
                else {"status": "empty", "sources": []}
            )

    engine = CachedSearchEngine(
        Engine(),
        SharedRetrievalCache(tmp_path / "cache.sqlite"),
        revision_provider=lambda: revision[0],
    )
    tools = ToolExecutor(FakeLLM(), photo)
    tools.cached_search(engine, monument_hint="test", query="question")
    tools.cached_search(engine, monument_hint="test", query="question")
    assert tools.calls[-1]["shared_cache_hit"]
    revision[0] = "withdrawn"
    assert tools.cached_search(engine, monument_hint="test", query="question")["status"] == "empty"
    assert not tools.calls[-1]["shared_cache_hit"]
