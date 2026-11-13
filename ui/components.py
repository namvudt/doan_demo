"""Result, evidence and stage views, all driven by actual workflow artifacts."""

import html
import json
from urllib.parse import urlsplit

import streamlit as st

from core.observability import token_usage
from core.presentation import (
    STAGE_LABELS,
    STAGES,
    STATUS_LABELS,
    collect_sources,
    export_result,
    linked_citations,
    map_links,
    markdown_report,
    safe_url,
    stage_snapshots,
    usage_summary,
)
from ui.session import save_feedback, set_question

CRITERIA = {
    "visual_fidelity": "Phù hợp với ảnh",
    "relevance": "Đúng trọng tâm",
    "cultural_tone": "Diễn đạt và văn hóa",
}


def render_progress(events):
    snapshots = stage_snapshots(events)
    cards = []
    terminal = 0
    for node, (number, label, _) in STAGES.items():
        item = snapshots.get(node, {})
        status = item.get("status", "waiting")
        terminal += status in {"completed", "failed", "skipped"}
        timing = f" · {item['duration']:.1f}s" if item.get("duration") is not None else ""
        cards.append(
            f'<div class="stage-card {status}"><span class="stage-number">{number}</span>'
            f"<strong>{html.escape(label)}</strong><small>{STAGE_LABELS[status]}{timing}</small></div>"
        )
    st.markdown('<div class="stage-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)
    st.progress(
        terminal / len(STAGES),
        text=f"{terminal}/{len(STAGES)} giai đoạn đã kết thúc hoặc được bỏ qua",
    )
    st.caption(
        "Quan sát ảnh và tra cứu tư liệu có thể chạy song song. Thanh tiến độ đếm bước, không ước lượng thời gian."
    )


def render_criteria(report):
    criteria = report.get("criteria_evaluation", {})
    if not criteria:
        st.caption("Chưa có kết quả đánh giá hợp lệ cho các tiêu chí.")
        return
    st.table(
        [
            {
                "Tiêu chí": CRITERIA.get(name, name),
                "Kết quả": "Đạt" if item.get("passed") else "Cần xem lại",
                "Điểm tự đánh giá / 10": item.get("score"),
                "Nhận xét": item.get("critique", ""),
            }
            for name, item in criteria.items()
        ]
    )


def render_stages(events, *, show_draft=False, sources=None, live=False):
    snapshots = stage_snapshots(events)
    latest = events[-1].get("node") if live and events else None
    for node, (_, title, description) in STAGES.items():
        if node not in snapshots:
            continue
        item = snapshots[node]
        payload = item.get("payload", {})
        reused = " · dùng lại kết quả đã lưu" if payload.get("reused") else ""
        duration = f" · {item['duration']:.2f}s" if item.get("duration") is not None else ""
        with st.expander(
            f"{title} · {STAGE_LABELS[item['status']]}{duration}{reused}",
            expanded=item["status"] in {"running", "failed"} or node == latest,
        ):
            st.caption(description)
            if payload.get("summary"):
                st.write(payload["summary"])
            if payload.get("error_type"):
                st.warning(
                    f"Chưa hoàn tất giai đoạn này ({payload['error_type']}). Có thể thử lại lượt xử lý."
                )
            if plan := payload.get("plan"):
                st.write(
                    "**Gợi ý nhận diện:** " + (plan.get("identified_monument") or "Chưa xác định")
                )
                st.caption("Đây là định danh sơ bộ để tìm tư liệu; cần đối chiếu với ảnh và nguồn.")
                if plan.get("query_intent"):
                    st.write("Mục tiêu: " + plan["query_intent"])
                names = {
                    "visual_agent": "Quan sát ảnh",
                    "knowledge_agent": "Tra cứu tư liệu",
                    "tool_gen_agent": "Phân tích bổ sung",
                }
                st.write(
                    "Chuyên gia: "
                    + " · ".join(names.get(a, a) for a in plan.get("selected_agents", []))
                )
                for key, label in [
                    ("visual_focus", "Trọng tâm hình ảnh"),
                    ("knowledge_focus", "Trọng tâm tư liệu"),
                ]:
                    if focus := plan.get("focus_directives", {}).get(key):
                        st.write(f"{label}: {focus}")
            if payload.get("content"):
                if node == "aggregate" and not show_draft:
                    st.caption(
                        "Bản nháp được giữ riêng. Bật “Xem bản nháp chưa đánh giá” trong thanh bên để quan sát."
                    )
                else:
                    st.warning("Kết quả trung gian chưa được đánh giá; có thể chứa thông tin sai.")
                    st.markdown(linked_citations(payload["content"], sources or []))
            for source in payload.get("sources", []):
                st.write(f"**Nguồn đã lấy: {source['title']}**")
                st.write(source["snippet"])
                if url := safe_url(source["url"]):
                    st.link_button("Đọc nguồn gốc", url)
            if report := payload.get("report"):
                render_criteria(report)
                if report.get("refinement_summary"):
                    st.write("Điều chỉnh sau đánh giá: " + report["refinement_summary"])
            if payload.get("actual_provider"):
                st.caption(f"{payload['actual_provider']} · {payload.get('model_used', '')}")


def render_sources(result):
    sources = collect_sources(result)
    st.subheader("Tư liệu làm căn cứ")
    st.caption(
        "Phân biệt nguồn đã truy xuất với nguồn được câu trả lời cuối trích dẫn. Một đoạn nguồn chưa bảo đảm mọi dữ kiện đều đúng."
    )
    if sources:
        term = st.text_input(
            "Lọc nguồn theo tên hoặc nội dung", key=f"source_filter_{result['run_id']}"
        )
        only_cited = st.checkbox(
            "Chỉ hiện nguồn được trích dẫn", key=f"cited_only_{result['run_id']}"
        )
        filtered = [
            s
            for s in sources
            if (not only_cited or s["cited"])
            and term.casefold() in (s["title"] + s["snippet"]).casefold()
        ]
        if not filtered:
            st.info("Không có nguồn khớp bộ lọc.")
        for source in filtered:
            with st.container(border=True):
                st.markdown(f"**[{source['number']}] {source['title']}**")
                st.caption(
                    "Được trích dẫn trong câu trả lời"
                    if source["cited"]
                    else "Đã truy xuất · chưa được trích dẫn"
                )
                st.write(source["snippet"])
                st.caption(f"{urlsplit(source['url']).hostname} · Mã: {source['source_id']}")
                st.caption(
                    f"Truy cập: {source.get('retrieved_at') or 'Chưa ghi nhận'} · Phiên bản: {source.get('revision_id') or 'Chưa ghi nhận'}"
                )
                st.link_button("Mở tài liệu gốc", safe_url(source["url"]))
    else:
        st.info(
            "Lượt này chưa có đoạn nguồn được truy xuất. Không nên suy dữ kiện lịch sử chỉ từ ảnh."
        )
    searches = [e.get("payload", {}).get("search_status") for e in result.get("events", [])]
    if any(status in {"error", "timeout"} for status in searches):
        st.warning("Bước tìm kiếm từng gặp lỗi hoặc hết thời gian. Nguồn có thể chưa đầy đủ.")
    st.subheader("Khám phá trên bản đồ")
    links = map_links(result)
    if links:
        st.caption(
            "Tìm kiếm theo tên nhận diện sơ bộ; hãy xác nhận đúng địa điểm trên bản đồ. Hệ thống chưa xác minh tọa độ, giờ mở cửa hay giá vé."
        )
        for column, link in zip(st.columns(3), links, strict=True):
            column.link_button(link["title"], link["url"], width="stretch")
    else:
        st.caption("Chưa có tên địa điểm để tạo liên kết bản đồ.")


def render_quality(result):
    st.subheader("Đánh giá tự động")
    st.caption(
        "Các điểm bên dưới do model tự đánh giá, không phải độ chính xác đo trên bộ kiểm thử."
    )
    report = result.get("judge_report", {})
    render_criteria(report)
    if report.get("hallucination_notes"):
        st.write(report["hallucination_notes"])
    if report.get("refinement_summary"):
        st.write("Điều chỉnh: " + report["refinement_summary"])
    st.subheader("Thời gian từng giai đoạn")
    timings = [
        {"Giai đoạn": STAGES[node][1], "Giây": round(item.get("duration") or 0, 3)}
        for node, item in stage_snapshots(result.get("events", [])).items()
        if node in STAGES and item.get("duration") is not None
    ]
    if timings:
        st.bar_chart(timings, x="Giai đoạn", y="Giây", color="#517e5f", horizontal=True)
        st.caption(
            "Các nhánh song song chồng lấp về thời gian; tổng thời gian node có thể lớn hơn thời gian toàn lượt."
        )
    if result.get("errors"):
        st.subheader("Các bước cần xem lại")
        st.table(
            [
                {
                    "Giai đoạn": STAGES.get(e["node"], ("", e["node"], ""))[1],
                    "Loại lỗi": e["error_type"],
                }
                for e in result["errors"]
            ]
        )
    with st.expander("Thông tin kỹ thuật và LangSmith"):
        st.code(result["run_id"], language=None)
        st.caption("Mã trên cũng là root run ID trong LangSmith khi tracing được bật.")
        st.json(
            {
                "workflow_version": result.get("config_snapshot", {}).get("workflow_version"),
                "config_hash": result.get("config_snapshot", {}).get("config_hash"),
            }
        )
        rows = []
        for call in result.get("calls", []):
            usage = token_usage(call.get("usage"), call.get("actual_provider"))
            rows.append(
                {
                    "Lần gọi": call.get("attempt"),
                    "Vai trò": call.get("agent_role"),
                    "Provider": call.get("actual_provider"),
                    "Model": call.get("model_used"),
                    "Trạng thái": call.get("status"),
                    "Giây": call.get("duration"),
                    "Token": usage.get("total_tokens"),
                    "Loại lỗi": call.get("error_type"),
                    "Finish reason": call.get("finish_reason"),
                    "Mã lỗi": call.get("error_code"),
                    "HTTP provider": call.get("provider_status_code"),
                    "Giới hạn output": call.get("max_output_tokens"),
                }
            )
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")


def render_result(result, *, show_stages=True, show_draft=False, history=False):
    sources = collect_sources(result)
    st.subheader("Kết quả khám phá")
    st.caption(result["query"])
    if result.get("run_kind") == "review":
        st.caption(
            f"Đánh giá lại từ lượt {result.get('parent_run_id')} · ảnh, bản nháp và nguồn được giữ nguyên."
        )
    report = result.get("judge_report", {})
    if report.get("error_code"):
        hints = {
            "configuration": "Kiểm tra credential/model của Judge và khởi động lại dịch vụ trước khi đánh giá lại.",
            "technical": "Dịch vụ model gặp lỗi. Có thể đánh giá lại khi dịch vụ phục hồi.",
            "review_format": "Judge trả định dạng chưa hợp lệ. Có thể đánh giá lại mà không chạy lại các bước trước.",
            "evidence": "Kiểm tra nguồn và trích dẫn trong kết quả trung gian; bổ sung bằng chứng nếu cần.",
        }
        st.warning(f"Judge: {report['error_code']}. {hints.get(report.get('error_category'), '')}")
    if history:
        st.info("Đang xem một lượt trong lịch sử phiên. Việc xem lại không gọi model.")
    if result["status"] == "reviewed":
        st.success(STATUS_LABELS[result["status"]] + " · Hãy đối chiếu với nguồn tham khảo.")
    elif result["status"] == "failed":
        st.error(STATUS_LABELS[result["status"]] + " · Bạn có thể thử lại hoặc đổi ảnh.")
    else:
        st.warning(STATUS_LABELS.get(result["status"], result["status"]))
    usage = usage_summary(result.get("calls", []))
    for column, label, value in zip(
        st.columns(4),
        ["Thời gian", "Lượt gọi model", "Nguồn truy xuất", "Token ghi nhận"],
        [
            f"{result['duration']:.1f}s",
            len(result.get("calls", [])),
            len(sources),
            f"{usage['total_tokens']:,}" if usage["total_tokens"] is not None else "Chưa có",
        ],
        strict=True,
    ):
        column.metric(label, value)
    if usage["partial"]:
        st.caption("Token chỉ phản ánh các lượt SDK có trả usage; dữ liệu hiện chưa đầy đủ.")
    overview, stages, evidence, quality = st.tabs(
        [
            "Câu trả lời",
            "Từng giai đoạn",
            "Nguồn & bản đồ",
            "Chất lượng & vận hành",
        ]
    )
    with overview:
        if candidate := result.get("plan", {}).get("identified_monument"):
            st.markdown(f"**Gợi ý nhận diện:** {candidate}")
            st.caption(
                "Tên công trình là giả thuyết nhận diện; hãy đối chiếu ảnh và tư liệu bên dưới."
            )
        if result.get("final_response") and result["status"] in {
            "reviewed",
            "insufficient_evidence",
        }:
            st.markdown(linked_citations(result["final_response"], sources))
        elif result["status"] == "out_of_scope":
            st.info(
                "Hiện hỗ trợ nhận diện, quan sát kiến trúc và lịch sử có nguồn. Hãy thử một câu hỏi trong các nhóm này."
            )
        else:
            st.info(
                "Chưa có câu trả lời được đánh giá hợp lệ. Bạn vẫn có thể xem các báo cáo trung gian và nguồn đã lấy."
            )
        if sources:
            st.markdown("**Nguồn liên quan**")
            for source in sources:
                if source["cited"]:
                    st.markdown(
                        f"[{source['number']} · {source['title']}]({safe_url(source['url'])})"
                    )
        st.markdown("**Tiếp tục khám phá với cùng ảnh**")
        for index, question in enumerate(
            [
                "Những chi tiết kiến trúc nào nhìn thấy rõ trong ảnh?",
                "Các nguồn ghi nhận lịch sử công trình này như thế nào?",
                "Điểm nào có thể quan sát trực tiếp và điểm nào cần thêm tư liệu?",
            ]
        ):
            st.button(
                question,
                key=f"followup_{result['run_id']}_{index}",
                on_click=set_question,
                args=(st.session_state, question),
            )
    with stages:
        render_progress(result.get("events", []))
        if show_stages:
            render_stages(result.get("events", []), show_draft=show_draft, sources=sources)
        else:
            st.caption("Bật “Hiển thị kết quả từng bước” trong thanh bên để xem báo cáo chi tiết.")
    with evidence:
        render_sources(result)
    with quality:
        render_quality(result)
    with st.expander("Lưu báo cáo và phản hồi"):
        run_id = result["run_id"]
        prior = st.session_state.get("feedback_store", {}).get(run_id, {})
        st.session_state.setdefault(
            f"feedback_widget_{run_id}", prior.get("rating", "Chưa đánh giá")
        )
        st.session_state.setdefault(f"note_widget_{run_id}", prior.get("note", ""))
        feedback = st.radio(
            "Kết quả có hữu ích không?",
            ["Chưa đánh giá", "Hữu ích", "Cần kiểm tra lại"],
            key=f"feedback_widget_{run_id}",
            on_change=save_feedback,
            args=(st.session_state, run_id),
            horizontal=True,
        )
        note = st.text_area(
            "Ghi chú của bạn",
            key=f"note_widget_{run_id}",
            max_chars=1500,
            on_change=save_feedback,
            args=(st.session_state, run_id),
        )
        st.caption(
            "Phản hồi chỉ lưu trong phiên này và file tải xuống; chưa gửi đến dịch vụ bên ngoài."
        )
        include = st.checkbox(
            "Xuất kèm kết quả trung gian chưa đánh giá", key=f"export_full_{result['run_id']}"
        )
        if include:
            st.warning("Báo cáo đầy đủ có cả bản nháp và nội dung chưa được đánh giá.")
        first, second = st.columns(2)
        output = export_result(result, include_intermediate=include)
        output["user_feedback"] = {"rating": feedback, "note": note}
        first.download_button(
            "Tải dữ liệu JSON",
            json.dumps(output, ensure_ascii=False, indent=2),
            file_name=f"heritage-{result['run_id']}.json",
            mime="application/json",
            key=f"json_{result['run_id']}",
            on_click="ignore",
            width="stretch",
        )
        report = markdown_report(result, include_intermediate=include)
        report += f"\n\n## Phản hồi cá nhân\n\n{feedback}\n\n{note}\n"
        second.download_button(
            "Tải báo cáo Markdown",
            report,
            file_name=f"heritage-{result['run_id']}.md",
            mime="text/markdown",
            key=f"md_{result['run_id']}",
            on_click="ignore",
            width="stretch",
        )


def render_comparison(comparison):
    st.subheader("So sánh phương pháp")
    st.warning("So sánh mô tả; chưa có bộ đánh giá độc lập để kết luận phương pháp tốt hơn.")
    st.table(
        [
            {
                "Phương pháp": row["method"],
                "Trạng thái": row["status"],
                "Giây": round(row["duration"], 2),
                "Lượt gọi": len(row["calls"]),
            }
            for row in comparison["rows"]
        ]
    )
    for row in comparison["rows"]:
        with st.expander(row["method"]):
            st.caption("Đầu ra thử nghiệm; không phải đáp án chuẩn.")
            run = row.get("run", {})
            sources = collect_sources(run)
            st.markdown(linked_citations(row.get("answer") or "Chưa có câu trả lời.", sources))
            if run.get("events"):
                render_progress(run["events"])
                render_stages(run["events"], sources=sources)
    st.download_button(
        "Tải dữ liệu so sánh",
        json.dumps(comparison, ensure_ascii=False, indent=2),
        "comparison.json",
        "application/json",
        on_click="ignore",
    )
