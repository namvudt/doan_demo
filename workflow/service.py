"""One graph for Streamlit, CLI and comparison runs.

State contains serializable image bytes and public config, never clients or keys.
The checkpointer is injectable; default runs have no cross-run persistence.
"""

import operator
import re
import time
from copy import deepcopy
from io import BytesIO
from typing import Annotated, TypedDict
from uuid import uuid4

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from PIL import Image

from agents import (
    AggregatorAgent,
    CoordinatorAgent,
    GenerationAgent,
    JudgeAgent,
    KnowledgeAgent,
    VisualAgent,
)
from core.config import AppConfig
from core.gateway import LLMManager
from core.images import fingerprint, validate_image
from core.model_errors import failure_info
from core.observability import record_node_outcome, trace_operation
from core.preflight import ensure_ready
from core.presentation import STAGES, search_artifact, stage_artifact
from core.runtime_logging import context_fields, log_context, log_event
from core.schemas import RunEvent, RunResult, StageEvent


def merge_maps(left, right):
    return {**left, **right}


class State(TypedDict, total=False):
    image_data: bytes
    query: str
    audience: str
    plan: dict
    expert_results: Annotated[dict, merge_maps]
    errors: Annotated[list, operator.add]
    node_metadata: Annotated[dict, merge_maps]
    draft_response: str
    judge_report: dict
    fatal: bool
    out_of_scope: bool


def image_from(state):
    with Image.open(BytesIO(state["image_data"])) as image:
        return image.copy()


class RunCancelled(RuntimeError):
    """Cooperative stop between nodes and model attempts."""


def build_graph(
    llm,
    config,
    checkpointer=None,
    *,
    cancel_check=None,
    search_engine_factory=None,
    review_only=False,
):
    def wrap(name, function):
        def execute(state):
            if cancel_check:
                cancel_check()
            started = time.monotonic()
            get_stream_writer()({"node": name, "status": "running"})
            try:
                update = function(state)
                if cancel_check:
                    cancel_check()
                metadata = update.pop("_meta", {})
                caught_error = next(iter(update.get("errors", [])), {}).get("error_type")
                record_node_outcome("failed" if caught_error else "completed", caught_error)
                return {
                    **update,
                    "node_metadata": {
                        name: {
                            **metadata,
                            "duration": time.monotonic() - started,
                            "status": "failed" if caught_error else "completed",
                        }
                    },
                }
            except RunCancelled:
                raise
            except Exception as exc:
                record_node_outcome("failed", type(exc).__name__)
                update = {
                    "errors": [{"node": name, **failure_info(exc)}],
                    "node_metadata": {
                        name: {
                            "status": "failed",
                            **failure_info(exc),
                            "duration": time.monotonic() - started,
                        }
                    },
                }
                if name in {"coordinate", "aggregate", "judge"}:
                    update["fatal"] = True
                return update

        return execute

    def scope(state):
        query = state["query"].lower()
        unsupported = re.search(r"(đọc|dịch|phiên âm).*(hán|nôm|hoành phi|câu đối)", query)
        creative = re.search(r"(sáng tác|bài thơ|làm thơ)", query)
        return {"out_of_scope": bool(unsupported or (creative and not config.enable_generation))}

    def coordinate(state):
        plan, meta = CoordinatorAgent(llm).plan(image_from(state), state["query"])
        if not config.enable_generation:
            plan["selected_agents"] = [a for a in plan["selected_agents"] if a != "tool_gen_agent"]
        optional = [
            role
            for agent, role in (("knowledge_agent", "knowledge"), ("tool_gen_agent", "generation"))
            if agent in plan["selected_agents"]
        ]
        if optional:
            ensure_ready(llm, optional)
        return {"plan": plan, "_meta": meta}

    def visual(state):
        text, meta = VisualAgent(llm).analyze(
            image_from(state), state["query"], state["plan"]["focus_directives"]["visual_focus"]
        )
        return {"expert_results": {"visual": {"text": text, "meta": meta}}, "_meta": meta}

    def knowledge(state):
        agent = KnowledgeAgent(llm)
        if search_engine_factory:
            agent.search_engine = search_engine_factory()
        text, meta = agent.retrieve(
            query=state["query"],
            monument_hint=state["plan"]["identified_monument"],
            focus_directive=state["plan"]["focus_directives"]["knowledge_focus"],
            on_sources=lambda search: get_stream_writer()(
                {
                    "node": "knowledge",
                    "status": "running",
                    "payload": search_artifact(search),
                }
            ),
        )
        return {"expert_results": {"knowledge": {"text": text, "meta": meta}}, "_meta": meta}

    def generate(state):
        experts = state["expert_results"]
        text, meta = GenerationAgent(llm).generate(
            query=state["query"],
            monument_hint=state["plan"]["identified_monument"],
            visual_findings=experts["visual"]["text"],
            knowledge_findings=experts.get("knowledge", {}).get("text", ""),
            focus_directive=state["plan"]["focus_directives"]["generation_focus"],
        )
        return {"expert_results": {"generation": {"text": text, "meta": meta}}, "_meta": meta}

    def aggregate(state):
        experts = state["expert_results"]
        text, meta = AggregatorAgent(llm).aggregate(
            state["query"],
            experts["visual"]["text"],
            experts.get("knowledge", {}).get("text"),
            experts.get("generation", {}).get("text"),
            audience=state["audience"],
        )
        return {"draft_response": text, "_meta": meta}

    def judge(state):
        experts = state["expert_results"]
        knowledge_meta = experts.get("knowledge", {}).get("meta", {})
        sources = knowledge_meta.get("live_search_sources", [])
        if knowledge_meta.get("search_status") == "empty":
            return {
                "judge_report": {
                    "overall_status": "INSUFFICIENT_EVIDENCE",
                    "verification_status": "insufficient",
                    "criteria_evaluation": {},
                    "final_response": "Chưa tìm được đoạn nguồn để trả lời dữ kiện lịch sử. Bạn có thể bổ sung tên hoặc ảnh rõ hơn.",
                    "sources": [],
                },
                "_meta": {"skipped": "no_source_evidence"},
            }
        report, meta = JudgeAgent(llm).evaluate_and_refine(
            state["query"],
            state["draft_response"],
            experts["visual"]["text"],
            search_sources=sources,
            image=image_from(state),
            require_sources="knowledge_agent" in state["plan"]["selected_agents"],
        )
        update = {"judge_report": report, "_meta": meta}
        if report["verification_status"] == "unverified":
            update["errors"] = [
                {
                    "node": "judge",
                    **{
                        key: report[key]
                        for key in (
                            "error_type",
                            "error_code",
                            "error_category",
                            "retryable",
                            "role",
                            "provider_reason",
                            "provider_status_code",
                        )
                        if key in report
                    },
                }
            ]
        return update

    def route_experts(state):
        if state.get("fatal"):
            return ["finish"]
        return [
            "visual",
            *(["knowledge"] if "knowledge_agent" in state["plan"]["selected_agents"] else []),
        ]

    def route_after_experts(state):
        if "visual" not in state["expert_results"]:
            return "finish"
        return "generation" if "tool_gen_agent" in state["plan"]["selected_agents"] else "aggregate"

    graph = StateGraph(State)
    for name, function in (
        ("scope", scope),
        ("coordinate", coordinate),
        ("visual", visual),
        ("knowledge", knowledge),
        ("generation", generate),
        ("aggregate", aggregate),
        ("judge", judge),
    ):
        graph.add_node(name, wrap(name, function))
    graph.add_node("experts_done", wrap("experts_done", lambda state: {}))
    graph.add_node("finish", wrap("finish", lambda state: {}))
    graph.add_edge(START, "judge" if review_only else "scope")
    graph.add_conditional_edges(
        "scope", lambda s: "finish" if s["out_of_scope"] else "coordinate", ["finish", "coordinate"]
    )
    graph.add_conditional_edges("coordinate", route_experts, ["visual", "knowledge", "finish"])
    graph.add_edge("visual", "experts_done")
    graph.add_edge("knowledge", "experts_done")
    graph.add_conditional_edges(
        "experts_done", route_after_experts, ["finish", "generation", "aggregate"]
    )
    graph.add_edge("generation", "aggregate")
    graph.add_conditional_edges(
        "aggregate", lambda s: "finish" if s.get("fatal") else "judge", ["finish", "judge"]
    )
    graph.add_edge("judge", "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


class RunService:
    def __init__(
        self,
        llm=None,
        *,
        checkpointer=None,
        benchmark=False,
        search_engine_factory=None,
        attempt_observer=None,
    ):
        self.llm = llm or LLMManager()
        self.config: AppConfig = self.llm.config
        self.checkpointer = checkpointer
        self.benchmark = benchmark
        self.search_engine_factory = search_engine_factory
        self.attempt_observer = attempt_observer

    def stream(
        self,
        image_data: bytes,
        query: str,
        audience="tourist",
        *,
        run_id=None,
        cancel_check=None,
        _previous=None,
    ):
        query = query.strip()
        if not query or len(query) > 4000 or audience not in {"tourist", "student"}:
            raise ValueError("Câu hỏi hoặc nhóm người dùng không hợp lệ.")
        normalized = validate_image(image_data, self.config)
        previous = validate_review_parent(_previous) if _previous is not None else None
        if previous and previous.fingerprint != fingerprint(
            normalized, query, audience, previous.config_snapshot["config_hash"]
        ):
            raise ValueError("Review image does not match the original run")
        run_id = str(run_id or uuid4())
        llm = self.llm.for_run(benchmark=self.benchmark)
        llm.cancel_check = cancel_check
        llm.attempt_observer = self.attempt_observer
        snapshot = llm.config.snapshot()
        started = time.monotonic()
        state = {
            "image_data": normalized,
            "query": query,
            "audience": audience,
            "expert_results": {},
            "errors": [],
            "node_metadata": {},
            "fatal": False,
            "out_of_scope": False,
        }
        if previous:
            state.update(
                plan=deepcopy(previous.plan),
                expert_results=deepcopy(previous.expert_results),
                draft_response=previous.draft_response,
            )
            state["review_lineage"] = {
                "parent_run_id": previous.run_id,
                "run_kind": "review",
                "upstream_config_hash": previous.config_snapshot["config_hash"],
                "reused_nodes": ["scope", "coordinate", *previous.expert_results, "aggregate"],
            }
            state["node_metadata"] = {
                node: {
                    **previous.node_metadata.get(node, {}),
                    "duration": 0,
                    "status": "completed",
                    "reused": True,
                }
                for node in state["review_lineage"]["reused_nodes"]
            }
        graph = build_graph(
            llm,
            llm.config,
            self.checkpointer,
            cancel_check=cancel_check,
            search_engine_factory=self.search_engine_factory,
            review_only=bool(_previous),
        )
        try:
            with (
                log_context(run_id=run_id, trace_id=run_id),
                trace_operation(
                    "heritage-vqa.run",
                    run_id=run_id,
                    inputs={
                        "query": query,
                        "audience": audience,
                        "image_data": normalized,
                        **(
                            {
                                "draft_response": previous.draft_response,
                                "expert_results": previous.expert_results,
                                "plan": previous.plan,
                            }
                            if previous
                            else {}
                        ),
                    },
                    metadata={
                        **context_fields(),
                        "app_run_id": run_id,
                        "workflow_version": self.config.workflow_version,
                        "config_hash": snapshot["config_hash"],
                        "audience": audience,
                        "benchmark": self.benchmark,
                        **{
                            key: value
                            for key, value in state.get("review_lineage", {}).items()
                            if key != "reused_nodes"
                        },
                    },
                ) as span,
            ):
                log_event("run.started")
                if cancel_check:
                    cancel_check()
                ensure_ready(llm, ["judge"] if _previous else None)
                yield from self._stream_graph(graph, state, llm, snapshot, started, run_id, span)
        finally:
            llm.close()

    def _stream_graph(self, graph, state, llm, snapshot, started, run_id, span):
        normalized, query, audience = state["image_data"], state["query"], state["audience"]
        events = []
        lineage = state.pop("review_lineage", {})

        def event(node, status, *, payload=None, duration=None):
            record = StageEvent(
                sequence=len(events) + 1,
                node=node,
                status=status,
                elapsed=time.monotonic() - started,
                duration=duration,
                payload=payload or {},
            )
            events.append(record)
            log_event(
                "stage." + status,
                run_id=run_id,
                trace_id=run_id,
                node=node,
                status=status,
                sequence=record.sequence,
                duration_ms=round(duration * 1000, 3) if duration is not None else None,
                error_type=(payload or {}).get("error_type"),
                **{
                    key: payload[key]
                    for key in (
                        "error_code",
                        "error_category",
                        "retryable",
                        "role",
                        "provider_reason",
                        "provider_status_code",
                    )
                    if payload and key in payload
                },
            )
            return RunEvent(kind="node", run_id=run_id, **record.model_dump())

        for node in lineage.get("reused_nodes", []):
            yield event(
                node,
                "completed",
                duration=0,
                payload={
                    **stage_artifact(node, state),
                    "reused": True,
                    "source_run_id": lineage["parent_run_id"],
                },
            )
        for mode, update in graph.stream(
            state,
            config={
                "configurable": {"thread_id": run_id},
                "max_concurrency": self.config.parallel_workers,
                "recursion_limit": 20,
                "run_name": "heritage-vqa.graph",
                "metadata": {**context_fields(), "app_run_id": run_id},
            },
            stream_mode=["updates", "values", "custom"],
        ):
            if mode == "values":
                state = update
            elif mode == "custom":
                if isinstance(update, dict) and update.get("node") in {
                    *STAGES,
                    "experts_done",
                    "finish",
                }:
                    yield event(update["node"], "running", payload=update.get("payload"))
            else:
                for node, delta in update.items():
                    if node == "__interrupt__":
                        continue
                    delta = delta or {}
                    meta = delta.get("node_metadata", {}).get(node, {})
                    yield event(
                        node,
                        "failed" if meta.get("status") == "failed" else "completed",
                        payload=stage_artifact(node, delta),
                        duration=meta.get("duration"),
                    )
        visited = {item.node for item in events}
        for node in STAGES:
            if node not in visited:
                yield event(
                    node,
                    "skipped",
                    payload={
                        "summary": "Không được chọn trong kế hoạch hoặc luồng đã dừng trước giai đoạn này."
                    },
                )
        report = state.get("judge_report", {})
        status = "unverified"
        if state.get("out_of_scope"):
            status = "out_of_scope"
        elif state.get("fatal") or "visual" not in state["expert_results"]:
            status = "failed"
        elif report.get("overall_status") == "INSUFFICIENT_EVIDENCE":
            status = "insufficient_evidence"
        elif report.get("verification_status") == "reviewed":
            status = "reviewed"
        result = RunResult(
            run_id=run_id,
            **lineage,
            fingerprint=fingerprint(normalized, query, audience, snapshot["config_hash"]),
            query=query,
            audience=audience,
            status=status,
            final_response=report.get("final_response")
            if status in {"reviewed", "insufficient_evidence"}
            else None,
            draft_response=state.get("draft_response"),
            plan=state.get("plan", {}),
            expert_results=state["expert_results"],
            judge_report=report,
            errors=state["errors"],
            node_metadata=state["node_metadata"],
            config_snapshot=snapshot,
            calls=sorted(llm.calls, key=lambda call: call["attempt"]),
            events=events,
            duration=time.monotonic() - started,
        )
        span.metadata = {"result_status": status, "error_count": len(result.errors)}
        span.outputs = {
            "final_response": result.final_response,
            "draft_response": result.draft_response,
            "plan": result.plan,
            "expert_results": result.expert_results,
            "judge_report": result.judge_report,
            "errors": result.errors,
            "status": status,
            "call_count": len(result.calls),
            "error_count": len(result.errors),
            "duration": result.duration,
        }
        if status == "failed":
            span.error = "WorkflowFailed"
        log_event(
            "run.completed",
            status=status,
            duration_ms=round(result.duration * 1000, 3),
            error_type=result.errors[0]["error_type"] if result.errors else None,
        )
        yield RunEvent(
            kind="completed",
            node="finish",
            run_id=run_id,
            sequence=len(events) + 1,
            elapsed=result.duration,
            result=result,
        )

    def run(self, image_data, query, audience="tourist"):
        result = None
        for event in self.stream(image_data, query, audience):
            if event.kind == "completed":
                result = event.result
        if result is None:
            raise RuntimeError("Workflow không trả kết quả.")
        return result

    def review_stream(self, image_data, previous, *, run_id=None, cancel_check=None):
        previous = RunResult.model_validate(previous)
        yield from self.stream(
            image_data,
            previous.query,
            previous.audience,
            run_id=run_id,
            cancel_check=cancel_check,
            _previous=previous.model_dump(),
        )


def validate_review_parent(previous):
    previous = RunResult.model_validate(previous)
    if not previous.draft_response or not previous.expert_results.get("visual", {}).get("text"):
        raise ValueError("A draft and visual evidence are required for review")
    if not previous.config_snapshot.get("config_hash"):
        raise ValueError("Original configuration fingerprint is required")
    if "knowledge_agent" in previous.plan.get("selected_agents", []):
        from core.schemas import SourceRecord

        sources = (
            previous.expert_results.get("knowledge", {})
            .get("meta", {})
            .get("live_search_sources", [])
        )
        if not any(
            source.type != "maps" and source.snippet.strip()
            for source in map(SourceRecord.model_validate, sources)
        ):
            raise ValueError("Retrieve source evidence before reviewing this run")
    return previous
