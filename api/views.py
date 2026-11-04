from datetime import datetime, timezone

from api.schemas import AssetView, EventView, ResultView, RunView
from core.presentation import collect_sources, stage_snapshots, usage_summary


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc) if value is not None else None


def asset_view(record):
    return AssetView(
        asset_id=record.id,
        sha256=record.sha256,
        size_bytes=record.size_bytes,
        width=record.width,
        height=record.height,
        created_at=timestamp(record.created_at),
        content_url=f"/api/v1/assets/{record.id}/content",
    )


def run_view(record):
    return RunView(
        run_id=record.id,
        asset_id=record.asset_id,
        parent_run_id=record.parent_run_id,
        question=record.question,
        audience=record.audience,
        model_mode=record.model_mode,
        execution_status=record.execution_status,
        result_status=record.result_status,
        bookmarked=record.bookmarked,
        event_count=record.event_count,
        error_type=record.error_type,
        created_at=timestamp(record.created_at),
        started_at=timestamp(record.started_at),
        finished_at=timestamp(record.finished_at),
        events_url=f"/api/v1/runs/{record.id}/events",
        result_url=f"/api/v1/runs/{record.id}/result",
    )


def public_event(record, include_draft=False):
    data = {**record.payload, "sequence": record.sequence}
    if not include_draft and data.get("node") == "aggregate":
        data["payload"] = {k: v for k, v in data.get("payload", {}).items() if k != "content"}
    return EventView(
        sequence=record.sequence,
        event=record.event,
        data=data,
        created_at=timestamp(record.created_at),
    )


def result_view(run, include_intermediate=False):
    result = run.result
    review = result.get("judge_report", {})
    review = {
        key: review[key]
        for key in (
            "overall_status",
            "verification_status",
            "criteria_evaluation",
            "hallucination_detected",
            "hallucination_notes",
            "refinement_summary",
            "cited_source_ids",
        )
        if key in review
    }
    plan = result.get("plan", {})
    plan = {
        key: plan[key]
        for key in ("identified_monument", "selected_agents", "query_intent", "task_categories")
        if key in plan
    }
    intermediate = None
    if include_intermediate:
        intermediate = {
            "draft_response": result.get("draft_response"),
            "stages": stage_snapshots(result.get("events", [])),
        }
    return ResultView(
        run_id=run.id,
        model_mode=run.model_mode,
        status=result["status"],
        question=result["query"],
        audience=result["audience"],
        final_response=result.get("final_response"),
        sources=collect_sources(result),
        plan=plan,
        review=review,
        errors=result.get("errors", []),
        duration=result["duration"],
        usage=usage_summary(result.get("calls", [])),
        intermediate=intermediate,
    )
