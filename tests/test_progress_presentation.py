import json
import threading
from io import BytesIO

import pytest
from PIL import Image

from core.presentation import (
    STAGES,
    collect_sources,
    export_result,
    linked_citations,
    markdown_report,
    safe_url,
    stage_snapshots,
    usage_summary,
)
from tests.conftest import FakeLLM
from ui.session import HISTORY_LIMIT, clear_history, remember_run
from workflow.service import RunService


def test_event_lifecycle_has_real_artifacts_and_skips_unused_stage(photo, fake_search):
    events = list(RunService(FakeLLM()).stream(photo, "question"))
    result = events[-1].result
    assert events[-1].kind == "completed"
    assert result.events
    for node in set(STAGES) - {"generation"}:
        node_events = [e for e in result.events if e.node == node]
        assert node_events[0].status == "running"
        assert node_events[-1].status == "completed"
        assert node_events[-1].duration >= 0
    assert stage_snapshots(result.events)["generation"]["status"] == "skipped"
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert all(event.run_id == result.run_id for event in events)
    payload = json.dumps([e.model_dump() for e in result.events])
    assert "image_data" not in payload
    assert "system_instruction" not in payload
    assert "plan_reasoning" not in payload
    assert "mock visual findings" in payload


def test_sources_arrive_before_knowledge_finishes_and_survive_its_failure(photo, fake_search):
    release = threading.Event()

    def behavior(role, kwargs):
        if role == "knowledge":
            assert release.wait(5), "Source progress was not delivered while the model was running"
            raise TimeoutError("private provider request")

    stream = RunService(FakeLLM(behavior)).stream(photo, "question")
    events = []
    try:
        for event in stream:
            events.append(event)
            if (
                event.node == "knowledge"
                and event.status == "running"
                and event.payload.get("sources")
            ):
                release.set()
    finally:
        release.set()
        stream.close()
    result = events[-1].result.model_dump(mode="json")
    assert result["status"] == "unverified"
    assert collect_sources(result)[0]["source_id"] == "wiki_a"
    assert not collect_sources(result)[0]["cited"]
    snapshot = stage_snapshots(result["events"])["knowledge"]
    assert snapshot["status"] == "failed"
    assert snapshot["payload"]["sources"]
    assert "private provider request" not in json.dumps(result)


def test_failure_and_scope_skip_the_remaining_stages(photo):
    failed = RunService(FakeLLM(lambda *args: "null")).run(photo, "question")
    snapshots = stage_snapshots(failed.events)
    assert snapshots["coordinate"]["status"] == "failed"
    assert snapshots["visual"]["status"] == "skipped"
    outside = RunService(FakeLLM()).run(photo, "Hãy sáng tác bài thơ")
    snapshots = stage_snapshots(outside.events)
    assert snapshots["scope"]["status"] == "completed"
    assert all(snapshots[node]["status"] == "skipped" for node in set(STAGES) - {"scope"})


def test_all_retrieved_sources_are_deduplicated_and_citations_link_to_registry(photo, fake_search):
    result = RunService(FakeLLM()).run(photo, "question").model_dump(mode="json")
    sources = collect_sources(result)
    assert len(sources) == 1
    assert sources[0]["number"] == 1 and sources[0]["cited"]
    rendered = linked_citations("Evidence [wiki_a]; unknown [wiki_fake].", sources)
    assert "[1](https://vi.wikipedia.org/wiki/Test)" in rendered
    assert "[wiki_fake]" in rendered
    assert "![" not in linked_citations("![external](https://example.org/tracker)", sources)


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,hi", "//example.org", "https://user:pass@example.org"],
)
def test_source_navigation_rejects_non_http_and_embedded_credentials(url):
    assert safe_url(url) is None


def test_exports_hide_draft_by_default_but_keep_sources_when_review_fails(photo, fake_search):
    fake = FakeLLM(lambda role, _: "invalid" if role == "judge" else None)
    result = RunService(fake).run(photo, "question").model_dump(mode="json")
    output = export_result(result)
    assert "draft_response" not in output
    assert "expert_results" not in output
    assert "events" not in output
    assert output["retrieved_sources"][0]["source_id"] == "wiki_a"
    assert "mock aggregator findings" not in markdown_report(result)
    assert "mock aggregator findings" in markdown_report(result, include_intermediate=True)
    assert "Test monument" in markdown_report(result, include_intermediate=True)
    assert export_result(result, include_intermediate=True)["draft_response"]
    assert result["draft_response"]  # exporting must not mutate the active result


def test_token_totals_mark_partial_usage_without_fabricating_unknown():
    assert usage_summary([{"usage": None}])["total_tokens"] is None
    usage = usage_summary(
        [
            {"actual_provider": "openai", "usage": {"total_tokens": 20}},
            {"usage": None},
        ]
    )
    assert usage["total_tokens"] == 20 and usage["partial"]


def test_history_is_bounded_with_small_thumbnails_and_clears_feedback(photo):
    history = []
    for index in range(HISTORY_LIMIT + 3):
        history = remember_run(history, {"run_id": str(index)}, photo)
    assert len(history) == HISTORY_LIMIT
    assert history[0]["result"]["run_id"] == str(HISTORY_LIMIT + 2)
    with Image.open(BytesIO(history[0]["thumbnail"])) as thumbnail:
        assert thumbnail.width <= 480 and thumbnail.height <= 360
    state = {"history": history, "saved_runs": {"1": True}, "feedback_store": {"1": "note"}}
    clear_history(state)
    assert state["history"] == [] and state["saved_runs"] == {} and state["feedback_store"] == {}
