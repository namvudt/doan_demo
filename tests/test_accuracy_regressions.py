"""Regression cases for entity/query drift and unsupported attributes found in live tests."""

import json
from types import SimpleNamespace

import pytest

from core.config import AccuracyPolicy, RetrievalPolicy
from core.entities import EntityCatalog
from core.evidence import EvidenceReview, bounded_report, check_claims
from core.search import HeritageSearchEngine, relevant_passage


def source(title, snippet, key="test"):
    return {
        "source_id": "wiki_" + key,
        "title": title,
        "snippet": snippet,
        "url": "https://vi.wikipedia.org/wiki/Test",
        "type": "wiki",
    }


def test_site_component_and_qualified_aliases_do_not_create_false_ambiguity():
    catalog = EntityCatalog()
    names = [
        "Chùa Thiên Trù",
        "Chùa Thiên Trù (Quần thể Chùa Hương)",
        "Chùa Thiên Trù (Quần thể Chùa Hương, Hà Nội)",
        "Chùa Thiên Trù - Chùa Hương",
        "Chùa Thiên Trù–Chùa Hương",
    ]
    assert len(catalog.candidates(names)) == 1
    child = catalog.resolve(names[0])
    parent = catalog.resolve("Chùa Hương")
    assert child != parent and parent in catalog.ancestors(child)
    assert catalog.resolve("Chùa Thiên Trù (Huế)") is None
    assert catalog.resolve("Chùa Thiên Trù khác") is None
    assert catalog.resolve("Khuê Văn Các (Hoàng thành Thăng Long)") is None
    assert catalog.most_specific([child, parent]) == child
    assert catalog.most_specific([child, catalog.resolve("Chùa Một Cột")]) is None


def test_ambiguous_alias_needs_an_unambiguous_location(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "entities": [
                    {"entity_id": "a", "name": "Chùa thử nghiệm", "localities": ["Hà Nội"]},
                    {"entity_id": "b", "name": "Chùa thử nghiệm", "localities": ["Huế"]},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    catalog = EntityCatalog(path)
    assert catalog.resolve("Chùa thử nghiệm") is None
    assert catalog.resolve("Chùa thử nghiệm (Huế)") == "b"
    assert catalog.resolve("Chùa thử nghiệm (Hà Nội)") == "a"


def test_nonempty_wrong_search_results_trigger_a_short_alias_retry(monkeypatch, tmp_path):
    engine = HeritageSearchEngine(policy=RetrievalPolicy(corpus_path=str(tmp_path / "missing")))
    queries = []

    def search(query, **kwargs):
        queries.append(query)
        if len(queries) == 1:
            return [source("Hà Nội", "Tư liệu chung về thủ đô.", "wrong")]
        return [source("Chùa Hương", "Chùa Thiên Trù có một đoạn tư liệu thử nghiệm.", "right")]

    monkeypatch.setattr(engine, "search_wikipedia", search)
    question = "Mô tả kiến trúc, xác định công trình và đối chiếu lịch sử khởi dựng hoặc trùng tu."
    result = engine.search_heritage("Chùa Thiên Trù (Quần thể Chùa Hương)", question)
    assert result["status"] == "success"
    assert [s["source_id"] for s in result["sources"]] == ["wiki_right"]
    assert len(queries) == 2 and all(len(q) < 40 for q in queries)
    assert question not in " ".join(queries)
    assert result["rejected_source_count"] == 1


def test_unrelated_sources_never_become_grounding_context(monkeypatch, tmp_path):
    engine = HeritageSearchEngine(policy=RetrievalPolicy(corpus_path=str(tmp_path / "missing")))
    monkeypatch.setattr(
        engine,
        "search_wikipedia",
        lambda *args, **kwargs: [source("Tam Quốc", "Một triều đại khác.")],
    )
    result = engine.search_heritage("Chùa Thiên Trù", "Lịch sử khởi dựng?")
    assert result["status"] == "empty" and result["sources"] == []
    assert result["context_text"] == "" and result["entity_filter_applied"]


def test_parent_article_passage_must_name_the_component_and_keep_its_locator(monkeypatch, tmp_path):
    text = "Giới thiệu tổng quan.\n\nChùa Thiên Trù\n\nTư liệu thử nghiệm về việc trùng tu công trình.\n\nNội dung khác."
    extract_requests = []

    def get(*args, **kwargs):
        params = kwargs["params"]
        if params.get("list") == "search":
            payload = {"query": {"search": [{"title": "Chùa Hương"}, {"title": "Hà Nội"}]}}
        else:
            extract_requests.append(params)
            title = params["titles"]
            payload = {
                "query": {
                    "pages": {
                        "1": {
                            "title": title,
                            "extract": text
                            if title == "Chùa Hương"
                            else "Trùng tu nhiều công trình của thủ đô.",
                            "lastrevid": 1,
                        }
                    }
                }
            }
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr("core.search.requests.get", get)
    engine = HeritageSearchEngine(policy=RetrievalPolicy(corpus_path=str(tmp_path / "missing")))
    result = engine.search_heritage("Chùa Thiên Trù", "trùng tu")
    assert len(result["sources"]) == 1
    actual = result["sources"][0]
    assert all(
        "exintro" not in request and request["exlimit"] == 1 and "|" not in request["titles"]
        for request in extract_requests
    )
    assert "Chùa Thiên Trù" in actual["snippet"] and "trùng tu" in actual["snippet"]
    _, start, end = actual["locator"].split(":")
    assert text[int(start) : int(end)] == actual["snippet"]
    assert (
        relevant_passage("Một văn bản khác", "trùng tu", 500, required_terms=["Chùa Thiên Trù"])[0]
        == ""
    )


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Hoành phi ghi 香天寶剎.", "han_nom_reading_unsupported"),
        (
            "Chữ Hán được đọc từ phải sang trái là Hương Thiên Bảo Sát.",
            "han_nom_reading_unsupported",
        ),
        ("Bên trái có một lư hương đồng.", "factual_attribute_requires_source"),
        ("Phía sau là núi đá vôi.", "factual_attribute_requires_source"),
        ("Cột làm từ gỗ lim.", "factual_attribute_requires_source"),
        ("Công trình được xây năm 1989.", "factual_attribute_requires_source"),
        ("Công trình được xây năm 968.", "factual_attribute_requires_source"),
    ],
)
def test_visual_label_cannot_bypass_han_nom_or_factual_attribute_policy(text, reason):
    evidence = [{"evidence_id": "img", "kind": "visual", "text": text, "version": "test"}]
    review = EvidenceReview(
        claims=[
            {
                "slot_id": "visual",
                "text": text,
                "kind": "visual",
                "verdict": "supported",
                "evidence_ids": ["img"],
            }
        ]
    )
    checked = check_claims(
        review,
        evidence,
        [{"slot_id": "visual", "evidence_type": "visual"}],
        AccuracyPolicy(enabled=True),
        identity_resolved=True,
    )
    assert checked[0]["verdict"] == "insufficient" and reason in checked[0]["gate_errors"]


def test_safe_visual_observations_and_evidence_backed_materials_remain_answerable():
    policy = AccuracyPolicy(enabled=True)
    slots = [{"slot_id": "visual", "evidence_type": "visual"}]
    evidence = [
        {
            "evidence_id": "img",
            "kind": "visual",
            "text": "Mái cong, sân và cánh đồng phía sau.",
            "version": "v1",
        }
    ]
    plain = {
        "slot_id": "visual",
        "text": evidence[0]["text"],
        "kind": "visual",
        "verdict": "supported",
        "evidence_ids": ["img"],
    }
    assert (
        check_claims(
            EvidenceReview(claims=[plain]), evidence, slots, policy, identity_resolved=False
        )[0]["verdict"]
        == "supported"
    )
    quotation = "Nguồn thử nghiệm ghi vật liệu hiện vật là đồng thau."
    evidence.append(
        {
            "evidence_id": "src",
            "kind": "source",
            "source_id": "web_test",
            "entity_id": "target",
            "text": quotation,
            "version": "v1",
        }
    )
    factual = {
        **plain,
        "text": "Hiện vật được ghi là đồng thau trong nguồn.",
        "kind": "historical",
        "evidence_ids": ["src"],
        "quotations": [{"evidence_id": "src", "quote": quotation}],
    }
    assert (
        check_claims(
            EvidenceReview(claims=[factual]),
            evidence,
            slots,
            policy,
            identity_resolved=True,
            selected_entity_id="target",
        )[0]["verdict"]
        == "supported"
    )
    wrong = check_claims(
        EvidenceReview(claims=[factual]),
        evidence,
        slots,
        policy,
        identity_resolved=True,
        selected_entity_id="other",
    )[0]
    assert "source_entity_mismatch" in wrong["gate_errors"]


def test_intermediate_limit_does_not_change_original_evidence():
    text = "Đoạn báo cáo thử nghiệm.\n" * 100
    limited, truncated = bounded_report(text, 500)
    assert truncated and len(limited) <= 500
    assert bounded_report("Ngắn", 500) == ("Ngắn", False)


def test_han_reading_is_omitted_before_it_can_ground_an_answer(photo):
    from core.config import load_config
    from tests.conftest import FakeLLM
    from workflow.service import RunService

    cfg = load_config("config/hanoi-evidence.yaml")

    def response(role, kwargs):
        name = getattr(kwargs.get("response_schema"), "__name__", "")
        if name == "ExecutionPlan":
            return json.dumps(
                {
                    "selected_agents": ["visual_agent"],
                    "identified_monument": "Chùa Thiên Trù",
                    "candidates": [{"name": "Chùa Thiên Trù (Quần thể Chùa Hương)"}],
                    "requested_slots": [
                        {"slot_id": "visible", "question": "Chi tiết?", "evidence_type": "visual"}
                    ],
                    "regions": [
                        {"box": [0.1, 0.1, 0.5, 0.5], "purpose": "Đọc chữ Hán trên hoành phi"}
                    ],
                }
            )
        if name == "VisualFindings":
            return json.dumps(
                {
                    "observations": [{"text": "Hoành phi ghi 香天寶剎."}, {"text": "Có mái cong."}],
                    "candidates": ["Chùa Thiên Trù"],
                    "readability": "limited",
                }
            )
        if name == "EvidenceReview":
            payload = json.loads(kwargs["prompt"])
            assert all("香" not in item["text"] for item in payload["evidence"])
            return json.dumps(
                {
                    "claims": [
                        {
                            "slot_id": "visible",
                            "text": "Có mái cong.",
                            "kind": "visual",
                            "verdict": "supported",
                            "evidence_ids": [payload["evidence"][0]["evidence_id"]],
                        }
                    ]
                }
            )

    result = RunService(FakeLLM(response, cfg)).run(photo, "Mô tả chi tiết nhìn thấy")
    assert result.answer_status == "answered" and result.plan["identity_resolved"]
    assert result.expert_results["visual"]["meta"]["omitted_observations"]
    assert "香" not in result.final_response
    assert not any(call["tool"] == "ocr_read" for call in result.tool_calls)


def test_no_relevant_sources_skip_knowledge_generation_and_keep_diagnostics(monkeypatch):
    from agents.experts import KnowledgeAgent
    from core.config import load_config
    from tests.conftest import FakeLLM

    manager = FakeLLM(config=load_config("config/hanoi-evidence.yaml"))
    agent = KnowledgeAgent(manager)
    monkeypatch.setattr(
        agent.search_engine,
        "search_heritage",
        lambda **kwargs: {
            "status": "empty",
            "sources": [],
            "error": None,
            "rejected_source_count": 4,
            "search_queries": ["test"],
            "entity_filter_applied": True,
        },
    )
    text, meta = agent.retrieve("History?", "Synthetic site")
    assert not manager.calls and meta["rejected_source_count"] == 4
    assert meta["search_queries"] == ["test"] and text


def test_historical_facts_are_conditioned_when_photo_identity_is_not_verified(photo):
    from api.demo import DemoSearch, evidence_demo_response
    from core.config import load_config
    from tests.conftest import FakeLLM
    from workflow.service import RunService

    def response(role, kwargs):
        schema = kwargs.get("response_schema")
        name = getattr(schema, "__name__", "")
        if name == "ExecutionPlan":
            data = evidence_demo_response(schema, kwargs["prompt"])
            data["requested_slots"] = [
                {"slot_id": "identity", "question": "Identity?", "evidence_type": "identity"},
                {"slot_id": "history", "question": "History?", "evidence_type": "historical"},
            ]
            return json.dumps(data)
        if name == "EvidenceReview":
            payload = json.loads(kwargs["prompt"])
            image = next(e for e in payload["evidence"] if e["kind"] == "visual")
            doc = next(e for e in payload["evidence"] if e["kind"] == "source")
            return json.dumps(
                {
                    "claims": [
                        {
                            "slot_id": "identity",
                            "text": "Chưa xác nhận danh tính trong ảnh.",
                            "kind": "identity",
                            "verdict": "insufficient",
                            "evidence_ids": [image["evidence_id"]],
                        },
                        {
                            "slot_id": "history",
                            "text": "Thông tin DEMO theo nguồn thử nghiệm.",
                            "kind": "historical",
                            "verdict": "supported",
                            "evidence_ids": [doc["evidence_id"]],
                            "quotations": [
                                {"evidence_id": doc["evidence_id"], "quote": doc["text"]}
                            ],
                        },
                    ]
                }
            )

    result = RunService(
        FakeLLM(response, load_config("config/hanoi-evidence.yaml")),
        search_engine_factory=DemoSearch,
    ).run(photo, "Identity and history?")
    assert result.answer_status == "partial"
    assert "Nếu công trình là DEMO" in result.final_response
    assert "Thông tin DEMO" in result.final_response


def test_ocr_tool_cannot_register_unsupported_han_readings(photo):
    from core.config import load_config
    from core.tools import ToolExecutor
    from tests.conftest import FakeLLM

    def response(role, kwargs):
        return json.dumps({"readable": True, "lines": [{"text": "香天寶剎"}, {"text": "Văn Miếu"}]})

    tools = ToolExecutor(FakeLLM(response, load_config("config/hanoi-evidence.yaml")), photo)
    region, data = tools.crop({"box": [0, 0, 1, 1]})
    output = tools.ocr(region, data)
    assert output["lines"] == [{"text": "Văn Miếu", "box": None}]
    assert [e["text"] for e in tools.evidence] == ["Văn Miếu"]
    assert tools.calls[-1]["filtered_line_count"] == 1


def test_source_requests_propagate_cancellation_instead_of_hiding_it_as_empty(
    monkeypatch, tmp_path
):
    class Cancelled(RuntimeError):
        pass

    def cancel():
        raise Cancelled("test cancellation")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("No HTTP request may start after cancellation")

    monkeypatch.setattr("core.search.requests.get", unexpected_request)
    engine = HeritageSearchEngine(
        policy=RetrievalPolicy(corpus_path=str(tmp_path / "missing")), cancel_check=cancel
    )
    with pytest.raises(Cancelled):
        engine.search_heritage("Chùa Thiên Trù", "trùng tu")


def test_parallel_tool_calls_cannot_exceed_ocr_budget(photo):
    from concurrent.futures import ThreadPoolExecutor

    from core.config import load_config
    from core.tools import ToolBudgetExceeded, ToolExecutor
    from tests.conftest import FakeLLM

    tools = ToolExecutor(FakeLLM(config=load_config("config/hanoi-evidence.yaml")), photo)

    def invoke(index):
        try:
            tools.execute("ocr_read", {"test_input": index}, lambda: "synthetic")
            return "success"
        except ToolBudgetExceeded:
            return "limited"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(invoke, range(4)))
    assert outcomes.count("success") == 2 and outcomes.count("limited") == 2
    assert len(tools.calls) == 2
