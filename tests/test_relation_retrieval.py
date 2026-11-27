"""Offline regressions for retrieval subject drift, relation coverage and request limits."""

from types import SimpleNamespace

import pytest
import requests

from core.config import RetrievalPolicy
from core.search import HeritageSearchEngine, country_question_subject, retrieval_plan


def record(key, title, text):
    return {
        "source_id": f"wiki_{key}",
        "title": title,
        "snippet": text,
        "type": "wiki",
        "url": "https://vi.wikipedia.org/wiki/Synthetic",
    }


def engine(tmp_path, **options):
    return HeritageSearchEngine(
        policy=RetrievalPolicy(corpus_path=str(tmp_path / "missing.jsonl"), **options)
    )


def test_entity_mention_does_not_stop_designation_search(monkeypatch, tmp_path):
    search = engine(tmp_path, max_results=1)
    queries = []

    def wikipedia(query, **kwargs):
        queries.append(query)
        if len(queries) == 1:
            return [record("bio", "Tiểu sử một người", "Người này từng đến Đền Thử Nghiệm.")]
        return [record("rank", "Đền Thử Nghiệm", "Đền Thử Nghiệm được xếp hạng di tích cấp tỉnh.")]

    monkeypatch.setattr(search, "search_wikipedia", wikipedia)
    result = search.search_heritage("Đền Thử Nghiệm", "Nơi này được xếp vào hạng di tích nào?")
    assert len(queries) == 2
    assert "xếp hạng" in queries[0]
    assert [s["source_id"] for s in result["sources"]] == ["wiki_rank"]
    diagnostics = result["retrieval_diagnostics"]
    assert diagnostics["relation"] == "designation"
    assert diagnostics["coverage_status"] == "candidate_found"
    assert diagnostics["rejected_sources"] == [
        {"source_id": "wiki_bio", "reason": "relation_not_covered"}
    ]
    assert diagnostics["attempts"][0]["accepted"] == 0


def test_country_relation_uses_explicit_last_subject(monkeypatch, tmp_path):
    search = engine(tmp_path)
    queries = []

    def wikipedia(query, **kwargs):
        queries.append(query)
        assert kwargs["entity_terms"] == ["Tỉnh Lam"]
        return [record("province", "Tỉnh Lam", "Tỉnh Lam là một tỉnh thuộc quốc gia Thử Nghiệm.")]

    monkeypatch.setattr(search, "search_wikipedia", wikipedia)
    query = "Nhà tù Hư Cấu nằm ở Tỉnh Lam, và Tỉnh Lam thuộc quốc gia nào?"
    result = search.search_heritage("Nhà tù Hư Cấu", query)
    assert len(queries) == 1 and '"Tỉnh Lam"' in queries[0]
    assert "Nhà tù" not in queries[0]
    assert result["retrieval_diagnostics"]["subject"] == "Tỉnh Lam"
    assert result["retrieval_diagnostics"]["subject_origin"] == "question"


@pytest.mark.parametrize(
    "query", ["Nơi này thuộc quốc gia nào?", "Địa danh trong ảnh thuộc nước nào?"]
)
def test_country_deictic_subject_keeps_image_candidate(query, tmp_path):
    search = engine(tmp_path)
    assert country_question_subject(query) is None
    plan = retrieval_plan("Đền Thử Nghiệm", query, search.policy, search.catalog)
    assert plan["subject"] == "Đền Thử Nghiệm"


def test_qualified_unknown_name_has_short_search_fallback(monkeypatch, tmp_path):
    search = engine(tmp_path)
    queries = []

    def wikipedia(query, **kwargs):
        queries.append(query)
        return (
            []
            if len(queries) == 1
            else [
                record("site", "Đền Thử Nghiệm", "Đền Thử Nghiệm được xếp hạng di tích cấp tỉnh.")
            ]
        )

    monkeypatch.setattr(search, "search_wikipedia", wikipedia)
    result = search.search_heritage("Đền Thử Nghiệm (Tỉnh Lam)", "Hạng di tích nào?")
    assert '"Đền Thử Nghiệm (Tỉnh Lam)"' in queries[0]
    assert queries[1] == '"Đền Thử Nghiệm" xếp hạng di tích'
    assert result["status"] == "success"
    assert search.catalog.resolve("Đền Thử Nghiệm (Tỉnh Lam)") is None


def test_nearest_relation_rejects_general_ecology_then_looks_for_distance(monkeypatch, tmp_path):
    search = engine(tmp_path)
    queries = []

    def wikipedia(query, **kwargs):
        queries.append(query)
        if len(queries) == 1:
            return [record("ecology", "Khu A", "Khu A có rừng ngập mặn, chim và cây xanh.")]
        return [record("distance", "Khu A", "Đảo B cách Khu A khoảng 8 km.")]

    monkeypatch.setattr(search, "search_wikipedia", wikipedia)
    result = search.search_heritage("Khu A", "Địa danh gần nơi trong ảnh nhất thuộc loại hình nào?")
    assert len(queries) == 2 and "khoảng cách" in queries[0]
    assert [s["source_id"] for s in result["sources"]] == ["wiki_distance"]
    assert result["retrieval_diagnostics"]["coverage_method"] == "lexical_candidate_only"


def test_relation_coverage_missing_has_no_grounding_context(monkeypatch, tmp_path):
    search = engine(tmp_path, max_queries=1)
    monkeypatch.setattr(
        search,
        "search_wikipedia",
        lambda *a, **k: [record("bio", "Tiểu sử", "Một người từng làm việc ở Đền Thử Nghiệm.")],
    )
    result = search.search_heritage("Đền Thử Nghiệm", "Hạng di tích nào?")
    assert result["status"] == "empty" and result["context_text"] == ""
    assert result["retrieval_diagnostics"]["coverage_status"] == "missing"
    assert result["retrieval_diagnostics"]["stop_reason"] == "queries_exhausted"


def test_road_kilometre_marker_is_not_a_nearest_destination_relation(monkeypatch, tmp_path):
    search = engine(tmp_path, max_queries=1)
    monkeypatch.setattr(
        search,
        "search_wikipedia",
        lambda *a, **k: [
            record("marker", "Site A", "Site A có cột mốc đường tại Km 432 và rừng cây.")
        ],
    )
    result = search.search_heritage("Site A", "Địa danh gần nhất thuộc loại hình nào?")
    assert result["status"] == "empty"
    assert (
        result["retrieval_diagnostics"]["rejected_sources"][0]["reason"] == "relation_not_covered"
    )


def test_relation_rules_can_be_overridden_without_code_changes(monkeypatch, tmp_path):
    search = engine(
        tmp_path,
        relation_rules={
            "custom": {
                "triggers": ["custom relation"],
                "query_terms": ["custom lookup"],
                "coverage_terms": ["documented custom value"],
            }
        },
    )
    monkeypatch.setattr(
        search,
        "search_wikipedia",
        lambda *a, **k: [record("custom", "Site A", "Site A has a documented custom value.")],
    )
    result = search.search_heritage("Site A", "What is the custom relation?")
    assert result["retrieval_diagnostics"]["relation"] == "custom"
    assert result["search_queries"] == ['"Site A" custom lookup']


def test_explicit_subject_and_relation_override_deictic_query(monkeypatch, tmp_path):
    search = engine(tmp_path)
    monkeypatch.setattr(
        search,
        "search_wikipedia",
        lambda *a, **k: [record("place", "Place A", "Place A is in a documented country.")],
    )
    result = search.search_heritage("Other site", "Where?", subject="Place A", relation="country")
    assert result["retrieval_diagnostics"]["subject"] == "Place A"
    assert result["retrieval_diagnostics"]["subject_origin"] == "explicit"
    assert result["status"] == "success"


def test_relation_behavior_can_be_disabled(monkeypatch, tmp_path):
    search = engine(tmp_path, relation_aware=False)
    monkeypatch.setattr(
        search,
        "search_wikipedia",
        lambda *a, **k: [record("bio", "Biography", "A person visited Site A.")],
    )
    result = search.search_heritage("Site A", "Which country?")
    assert result["status"] == "success" and result["search_queries"] == ['"Site A"']
    assert result["retrieval_diagnostics"]["relation"] is None


def test_request_budget_prevents_extract_after_search_and_resets(monkeypatch, tmp_path):
    search = engine(tmp_path, max_http_requests=1)
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs["params"])
        assert kwargs["params"].get("list") == "search"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"query": {"search": [{"title": "Site A"}]}},
        )

    monkeypatch.setattr("core.search.requests.get", get)
    for _ in range(2):
        result = search.search_heritage("Site A", "Which country?")
        diagnostics = result["retrieval_diagnostics"]
        assert result["error"] == "RetrievalBudgetExceeded"
        assert diagnostics["http_requests"] == diagnostics["http_request_limit"] == 1
        assert diagnostics["stop_reason"] == "request_budget_exhausted"
    assert len(calls) == 2


def test_exact_title_is_fetched_before_incidental_mentions(monkeypatch, tmp_path):
    search = engine(tmp_path, max_results=1)
    extracted = []

    def get(url, **kwargs):
        params = kwargs["params"]
        if params.get("list") == "search":
            payload = {
                "query": {"search": [{"title": "Biography about Site A"}, {"title": "Site A"}]}
            }
        else:
            extracted.append(params["titles"])
            payload = {
                "query": {
                    "pages": {
                        "1": {
                            "title": params["titles"],
                            "extract": "Site A thuộc quốc gia Thử Nghiệm.",
                        }
                    }
                }
            }
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr("core.search.requests.get", get)
    result = search.search_heritage("Site A", "Which country?")
    assert extracted == ["Site A"]
    assert result["status"] == "success"


def test_deadline_prevents_any_http_request(monkeypatch, tmp_path):
    search = engine(tmp_path)
    search.remaining_seconds = lambda: 0
    monkeypatch.setattr(
        "core.search.requests.get", lambda *a, **k: pytest.fail("deadline exceeded")
    )
    result = search.search_heritage("Site A", "Which country?")
    assert result["status"] == "timeout" and result["error"] == "SearchTimeout"
    assert result["retrieval_diagnostics"]["http_requests"] == 0


def test_cancel_before_next_query_is_not_swallowed(monkeypatch, tmp_path):
    search = engine(tmp_path)
    queries = []

    def wikipedia(query, **kwargs):
        queries.append(query)
        return []

    def cancel():
        if queries:
            raise RuntimeError("cancelled")

    search.cancel_check = cancel
    monkeypatch.setattr(search, "search_wikipedia", wikipedia)
    with pytest.raises(RuntimeError, match="cancelled"):
        search.search_heritage("Site A", "Which country?")
    assert len(queries) == 1


def test_transient_search_error_can_retry_but_is_bounded(monkeypatch, tmp_path):
    search = engine(tmp_path, max_queries=2)
    calls = []

    def wikipedia(query, **kwargs):
        calls.append(query)
        raise requests.Timeout()

    monkeypatch.setattr(search, "search_wikipedia", wikipedia)
    result = search.search_heritage("Site A", "Which country?")
    assert len(calls) == 2 and result["status"] == "timeout"
    assert all(a["error"] == "SearchTimeout" for a in result["retrieval_diagnostics"]["attempts"])
