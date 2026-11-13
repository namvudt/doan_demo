import json
import threading

from langgraph.checkpoint.memory import InMemorySaver

from core.config import AppConfig
from tests.conftest import FakeLLM, valid_review
from workflow.comparison import compare
from workflow.service import RunService, build_graph


def test_graph_runs_experts_concurrently_and_aggregates_once(photo, fake_search):
    barrier = threading.Barrier(2)

    def behavior(role, kwargs):
        if role in {"visual", "knowledge"}:
            barrier.wait(timeout=5)

    llm = FakeLLM(behavior)
    result = RunService(llm).run(photo, "history question")
    roles = [call.get("agent_role") for call in llm.history]
    assert result.status == "reviewed"
    assert set(result.expert_results) == {"visual", "knowledge"}
    assert roles.count("aggregator") == 1
    assert roles.count("judge") == 1
    assert result.node_metadata["aggregate"]["model_used"] == "mock"


def test_bad_plan_fails_without_losing_error(photo):
    result = RunService(FakeLLM(lambda role, kwargs: "null")).run(photo, "q")
    assert result.status == "failed"
    assert result.errors[0]["node"] == "coordinate"
    assert result.final_response is None


def test_judge_failure_has_no_public_draft(photo, fake_search):
    result = RunService(FakeLLM(lambda role, kwargs: "invalid" if role == "judge" else None)).run(
        photo, "q"
    )
    assert result.status == "unverified"
    assert result.final_response is None
    assert result.draft_response


def test_partial_expert_failure_preserves_visual(photo, fake_search):
    def behavior(role, kwargs):
        if role == "knowledge":
            raise TimeoutError()

    result = RunService(FakeLLM(behavior)).run(photo, "q")
    assert result.status == "unverified"
    assert "visual" in result.expert_results
    assert any(error["node"] == "knowledge" for error in result.errors)


def test_no_sources_never_becomes_historical_approval(photo, fake_search):
    fake_search.update(status="empty", sources=[], context_text="")
    result = RunService(FakeLLM()).run(photo, "history")
    assert result.status == "insufficient_evidence"


def test_generation_consumes_expert_outputs(photo, fake_search):
    def behavior(role, kwargs):
        if role == "coordinator":
            return json.dumps(
                {"selected_agents": ["visual_agent", "knowledge_agent", "tool_gen_agent"]}
            )

    llm = FakeLLM(behavior, config=AppConfig(enable_generation=True))
    result = RunService(llm).run(photo, "question")
    generation = next(call for call in llm.history if call.get("agent_role") == "generation")
    assert "mock visual findings" in generation["prompt"]
    assert "mock knowledge findings" in generation["prompt"]
    assert result.status == "reviewed"


def test_scope_does_not_call_models(photo):
    llm = FakeLLM()
    result = RunService(llm).run(photo, "Hãy sáng tác bài thơ")
    assert result.status == "out_of_scope"
    assert not llm.history


def test_benchmark_snapshot_matches_effective_config(photo, fake_search):
    llm = FakeLLM(config=AppConfig(fallback_providers=["openai"]))
    result = RunService(llm, benchmark=True).run(photo, "q")
    assert result.config_snapshot["fallback_providers"] == []


def test_optional_checkpoint_is_serializable_and_scoped_to_run(photo, fake_search):
    saver = InMemorySaver()
    result = RunService(FakeLLM(), checkpointer=saver).run(photo, "q")
    checkpoint = saver.get_tuple({"configurable": {"thread_id": result.run_id}})
    assert checkpoint
    assert checkpoint.checkpoint["channel_values"]["image_data"]
    assert "credentials" not in str(checkpoint.checkpoint.keys())


def test_comparison_has_no_fixed_verdict_and_uses_same_graph(photo, fake_search):
    result = compare(photo, "q", FakeLLM())
    assert result["verdict"] is None
    assert result["evaluation_status"] == "not_evaluated"
    assert len(result["rows"]) == 3
    assert result["rows"][1]["metadata"]["has_tools"] is False
    assert result["rows"][2]["run"]["status"] == "reviewed"


def test_graph_topology_is_langgraph():
    graph = build_graph(FakeLLM(), AppConfig())
    assert {"coordinate", "visual", "knowledge", "aggregate", "judge"} <= set(
        graph.get_graph().nodes
    )


def test_visual_only_branch_does_not_wait_for_unselected_expert(photo):
    def behavior(role, kwargs):
        if role == "coordinator":
            return json.dumps({"selected_agents": ["visual_agent"]})
        if role == "judge":
            review = valid_review()
            review.update(cited_source_ids=[], final_response="Visual observations only.")
            return json.dumps(review)

    llm = FakeLLM(behavior)
    result = RunService(llm).run(photo, "Describe visible architecture")
    assert result.status == "reviewed"
    assert set(result.expert_results) == {"visual"}
    assert len(llm.history) == 4
