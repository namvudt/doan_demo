"""Explicit presentation projections; never expose clients, prompts or raw graph state."""

import re
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus, urlsplit

from pydantic import ValidationError

from core.observability import token_usage
from core.schemas import SourceRecord

STAGES = {
    "scope": ("01", "Kiểm tra đầu vào", "Xác định phạm vi câu hỏi"),
    "coordinate": ("02", "Lập kế hoạch", "Gợi ý nhận diện và chọn chuyên gia"),
    "visual": ("03", "Quan sát ảnh", "Các chi tiết nhìn thấy trong ảnh"),
    "knowledge": ("04", "Tra cứu tư liệu", "Truy xuất nguồn và đối chiếu dữ kiện"),
    "generation": ("05", "Phân tích bổ sung", "Xử lý yêu cầu chuyên biệt nếu được bật"),
    "aggregate": ("06", "Tổng hợp bản nháp", "Kết hợp báo cáo của các chuyên gia"),
    "judge": ("07", "Đánh giá câu trả lời", "Đối chiếu với ảnh và các đoạn nguồn"),
}
STATUS_LABELS = {
    "reviewed": "Đã được đánh giá tự động",
    "unverified": "Chưa hoàn tất đánh giá",
    "insufficient_evidence": "Chưa đủ bằng chứng",
    "out_of_scope": "Ngoài phạm vi hỗ trợ",
    "failed": "Lượt xử lý gặp lỗi",
}
STAGE_LABELS = {
    "running": "Đang thực hiện",
    "completed": "Hoàn tất",
    "failed": "Gặp lỗi",
    "skipped": "Bỏ qua",
    "waiting": "Đang chờ",
}


def safe_url(value):
    try:
        parsed = urlsplit(str(value))
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
            return quote(str(value), safe=":/?&=%#-._~+@")
    except ValueError:
        pass
    return None


def validated_sources(items):
    result = {}
    for item in items or []:
        try:
            source = SourceRecord.model_validate(item).model_dump(mode="json")
        except (ValidationError, TypeError):
            continue
        if source["type"] != "maps" and source["snippet"] and safe_url(source["url"]):
            result.setdefault(source["source_id"], source)
    return list(result.values())


def search_artifact(search):
    sources = validated_sources(search.get("sources"))
    summary = (
        "Đã truy xuất nguồn; đang đối chiếu tư liệu."
        if sources
        else "Chưa có đoạn nguồn để đối chiếu."
    )
    return {
        "summary": summary,
        "sources": sources,
        "search_status": search.get("status"),
        "error_type": search.get("error"),
        "navigation_links": [
            {"title": item.get("title", "Mở bản đồ"), "url": safe_url(item.get("url"))}
            for item in search.get("navigation_links", [])
            if safe_url(item.get("url"))
        ],
    }


def stage_artifact(node, update):
    """Project only user-facing artifacts; never copy arbitrary node metadata."""
    meta = update.get("node_metadata", {}).get(node, {})
    artifact = {
        key: meta[key]
        for key in (
            "actual_provider",
            "model_used",
            "error_type",
            "fallback_used",
            "search_status",
        )
        if key in meta
    }
    if node == "scope":
        artifact["summary"] = (
            "Câu hỏi nằm ngoài phạm vi hiện hỗ trợ."
            if update.get("out_of_scope")
            else "Đầu vào hợp lệ; chuyển sang nhận diện và phân tích."
        )
    elif node == "coordinate":
        plan = update.get("plan", {})
        artifact.update(
            summary="Đã lập kế hoạch phân tích.",
            plan={
                key: plan[key]
                for key in (
                    "query_intent",
                    "identified_monument",
                    "task_categories",
                    "selected_agents",
                    "focus_directives",
                )
                if key in plan
            },
        )
    elif node in {"visual", "knowledge", "generation"}:
        expert = update.get("expert_results", {}).get(node, {})
        artifact.update(
            content=expert.get("text"), summary="Báo cáo trung gian, chưa được đánh giá."
        )
        if node == "knowledge":
            expert_meta = expert.get("meta", {})
            artifact.update(
                search_artifact(
                    {
                        "sources": expert_meta.get("live_search_sources", []),
                        "status": expert_meta.get("search_status"),
                        "error": expert_meta.get("search_error"),
                        "navigation_links": expert_meta.get("navigation_links", []),
                    }
                )
            )
            if artifact.get("sources"):
                artifact["summary"] = "Đã tổng hợp tư liệu từ các nguồn truy xuất."
    elif node == "aggregate":
        artifact.update(
            content=update.get("draft_response"),
            summary="Bản nháp chưa được đánh giá; chưa phải câu trả lời cuối.",
        )
    elif node == "judge":
        report = update.get("judge_report", {})
        artifact.update(
            summary="Đã thực hiện bước đánh giá tự động.",
            report={
                key: report[key]
                for key in (
                    "overall_status",
                    "verification_status",
                    "criteria_evaluation",
                    "hallucination_detected",
                    "hallucination_notes",
                    "refinement_summary",
                    "cited_source_ids",
                    "error_type",
                )
                if key in report
            },
        )
        artifact["sources"] = validated_sources(report.get("sources"))
        if meta.get("skipped"):
            artifact["summary"] = "Chưa có đoạn nguồn để đối chiếu; không gọi model đánh giá."
    if meta.get("status") == "failed":
        artifact["summary"] = "Giai đoạn chưa hoàn tất. Các kết quả trước đó vẫn được giữ lại."
    return artifact


def stage_snapshots(events):
    snapshots = {}
    for event in events:
        item = event.model_dump() if hasattr(event, "model_dump") else event
        node = item["node"]
        previous = snapshots.get(node, {})
        snapshots[node] = {
            **previous,
            **item,
            "payload": {
                **previous.get("payload", {}),
                **{
                    key: value
                    for key, value in item.get("payload", {}).items()
                    if value is not None
                },
            },
        }
        sources = [
            *previous.get("payload", {}).get("sources", []),
            *item.get("payload", {}).get("sources", []),
        ]
        if sources:
            snapshots[node]["payload"]["sources"] = validated_sources(sources)
    return snapshots


def collect_sources(result):
    candidates = []
    for event in result.get("events", []):
        candidates.extend(event.get("payload", {}).get("sources", []))
    candidates.extend(
        result.get("expert_results", {})
        .get("knowledge", {})
        .get("meta", {})
        .get("live_search_sources", [])
    )
    report = result.get("judge_report", {})
    candidates.extend(report.get("sources", []))
    cited = set(report.get("cited_source_ids", []))
    return [
        {**item, "number": index, "cited": item["source_id"] in cited}
        for index, item in enumerate(validated_sources(candidates), 1)
    ]


def linked_citations(text, sources):
    lookup = {item["source_id"]: item for item in sources}

    def replace(match):
        source = lookup.get(match.group(1))
        if source and (url := safe_url(source["url"])):
            return f"[{source['number']}]({url})"
        return match.group(0)

    # Remote images in model/source text are not part of the evidence viewer.
    text = re.sub(r"!\[[^\]]*\]\([^\n]*\)", "[Ảnh ngoài đã được ẩn]", text or "")
    return re.sub(r"\[([A-Za-z0-9_-]+)\](?!\()", replace, text)


def usage_summary(calls):
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    known = {key: 0 for key in totals}
    for call in calls:
        usage = token_usage(call.get("usage"), call.get("actual_provider"))
        for key, count in usage.items():
            totals[key] += count
            known[key] += 1
    return {
        **{key: totals[key] if known[key] else None for key in totals},
        "partial": any(0 < count < len(calls) for count in known.values()),
    }


def map_links(result):
    # A search destination is explicitly provisional, never invented coordinates.
    name = result.get("plan", {}).get("identified_monument", "").strip()
    if not name:
        return []
    query = quote_plus(name)
    return [
        {
            "title": "Tìm trên Google Maps",
            "url": f"https://www.google.com/maps/search/?api=1&query={query}",
        },
        {
            "title": "Tìm đường đến địa điểm",
            "url": f"https://www.google.com/maps/dir/?api=1&destination={query}",
        },
        {
            "title": "Tìm trên OpenStreetMap",
            "url": f"https://www.openstreetmap.org/search?query={query}",
        },
    ]


def export_result(result, *, include_intermediate=False):
    """A compact export defaults to evaluated content; full artifacts are opt-in."""
    output = deepcopy(result)
    output["retrieved_sources"] = collect_sources(result)
    if not include_intermediate:
        output.pop("draft_response", None)
        output.pop("expert_results", None)
        output.pop("events", None)
        output.pop("plan", None)
    return output


def markdown_report(result, *, include_intermediate=False):
    sources = collect_sources(result)
    lines = [
        "# Báo cáo khám phá di sản",
        "",
        f"**Câu hỏi:** {result['query']}",
        "",
        f"**Trạng thái:** {STATUS_LABELS.get(result['status'], result['status'])}",
        "",
        "Đánh giá tự động có thể sai; cần đối chiếu nguồn.",
        "",
        linked_citations(result.get("final_response"), sources)
        or "Chưa có câu trả lời được đánh giá hợp lệ.",
        "",
        "## Nguồn đã truy xuất",
        "",
    ]
    for source in sources:
        lines.extend(
            [
                f"### [{source['number']}] {source['title']}",
                source["url"],
                f"Mã: {source['source_id']} · Được trích dẫn: {'Có' if source['cited'] else 'Không'}",
                f"Truy cập: {source.get('retrieved_at') or 'Chưa ghi nhận'}",
                "",
                source["snippet"],
                "",
            ]
        )
    if include_intermediate:
        lines.extend(["## Kết quả trung gian — chưa được đánh giá", ""])
        for node, event in stage_snapshots(result.get("events", [])).items():
            if node in STAGES:
                payload = event.get("payload", {})
                lines.extend(
                    [
                        f"### {STAGES[node][1]}",
                        payload.get("summary", ""),
                        payload.get("content") or "",
                        "",
                    ]
                )
                if plan := payload.get("plan"):
                    lines.extend(
                        [
                            f"Nhận diện sơ bộ: {plan.get('identified_monument') or 'Chưa xác định'}",
                            f"Mục tiêu: {plan.get('query_intent', '')}",
                            "",
                        ]
                    )
                    for key, label in [
                        ("visual_focus", "Trọng tâm ảnh"),
                        ("knowledge_focus", "Trọng tâm tư liệu"),
                    ]:
                        if focus := plan.get("focus_directives", {}).get(key):
                            lines.extend([f"{label}: {focus}", ""])
                if report := payload.get("report"):
                    for name, criterion in report.get("criteria_evaluation", {}).items():
                        lines.extend(
                            [
                                f"- {name}: {criterion.get('score')}/10 — {criterion.get('critique', '')}"
                            ]
                        )
                    if report.get("refinement_summary"):
                        lines.extend(["", report["refinement_summary"], ""])
    lines.extend(
        [
            "## Thông tin lượt xử lý",
            "",
            f"Run ID: {result['run_id']}",
            f"Thời gian: {result['duration']:.2f} giây",
            f"Số lượt gọi model: {len(result.get('calls', []))}",
            f"Xuất lúc (UTC): {datetime.now(timezone.utc).isoformat()}",
        ]
    )
    return "\n".join(lines)
