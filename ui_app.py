"""Streamlit presentation adapter. No orchestration or model transport here."""

import hashlib
import json
from pathlib import Path

import streamlit as st

from core.gateway import LLMManager
from core.images import validate_image
from workflow.comparison import compare
from workflow.service import RunService


def main():
    st.set_page_config(page_title="Di sản Việt Nam", layout="wide")
    st.title("Khám phá di sản Việt Nam qua hình ảnh")
    st.caption("Nhận diện công trình, tìm nguồn và kiểm tra câu trả lời tự động.")
    try:
        manager = LLMManager()
    except Exception as exc:
        st.error(f"Cấu hình chưa hợp lệ ({type(exc).__name__}). Kiểm tra HERITAGE_CONFIG.")
        st.stop()
    config = manager.config
    with st.sidebar:
        st.subheader("Chế độ")
        mode = st.radio("Chọn cách sử dụng", ["Hỏi bằng ảnh", "So sánh thử nghiệm"], key="mode")
        audience = st.selectbox(
            "Cách diễn đạt",
            ["tourist", "student"],
            key="audience",
            format_func=lambda value: "Khách tham quan" if value == "tourist" else "Học sinh",
        )
        with st.expander("Cấu hình nghiên cứu"):
            status = manager.get_status()
            for role, binding in status["roles"].items():
                st.caption(
                    f"{role}: {binding['provider']} / {binding['model']} — "
                    f"{'đã cấu hình' if binding['configured'] else 'thiếu cấu hình'}"
                )
            st.caption(status["description"])
            st.caption(f"Workflow: {config.workflow_version}")
    uploaded = st.file_uploader("Chụp hoặc tải ảnh công trình", type=["jpg", "jpeg", "png", "webp"])
    sample_paths = sorted(
        p
        for p in (Path(__file__).parent / "samples").iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    sample = st.selectbox(
        "Hoặc chọn ảnh mẫu",
        [None, *sample_paths],
        key="sample",
        format_func=lambda value: "Chọn ảnh mẫu" if value is None else value.stem,
    )
    data = uploaded.getvalue() if uploaded else sample.read_bytes() if sample else None
    query = st.text_area(
        "Bạn muốn tìm hiểu điều gì?",
        key="query",
        placeholder="Đây là công trình nào? Có nguồn nào về lịch sử?",
    )
    image_data = None
    if data:
        try:
            image_data = validate_image(data, config)
            st.image(image_data, width=500)
        except ValueError as exc:
            st.error(str(exc))
    key = hashlib.sha256(
        json.dumps(
            [
                hashlib.sha256(image_data or b"").hexdigest(),
                query.strip(),
                audience,
                mode,
                config.snapshot()["config_hash"],
            ]
        ).encode()
    ).hexdigest()
    if st.session_state.get("input_key") != key:
        st.session_state.pop("result", None)
        st.session_state.pop("comparison", None)
        st.session_state.input_key = key
    start = st.button(
        "Tìm câu trả lời" if mode == "Hỏi bằng ảnh" else "Chạy so sánh",
        type="primary",
        key="start",
        disabled=image_data is None or not query.strip(),
    )
    if start:
        st.session_state.pop("result", None)
        st.session_state.pop("comparison", None)
        readiness = manager.get_status()
        if not readiness["ready"]:
            st.error("Thiếu cấu hình cho role: " + ", ".join(readiness["missing_roles"]))
        else:
            try:
                if mode == "So sánh thử nghiệm":
                    with st.spinner("Đang chạy các phương pháp; chưa chấm độ chính xác..."):
                        st.session_state.comparison = compare(image_data, query, manager, audience)
                else:
                    with st.status("Đang xử lý", expanded=True) as progress:
                        labels = {
                            "scope": "Kiểm tra phạm vi",
                            "coordinate": "Lập kế hoạch",
                            "visual": "Quan sát ảnh",
                            "knowledge": "Tìm tư liệu",
                            "experts_done": "Tổng hợp dữ liệu chuyên gia",
                            "generation": "Xử lý tác vụ bổ sung",
                            "aggregate": "Soạn bản nháp",
                            "judge": "Đối chiếu ảnh và nguồn",
                            "finish": "Hoàn tất",
                        }
                        for event in RunService(manager).stream(image_data, query, audience):
                            if event.kind == "node":
                                progress.write(labels[event.node])
                            else:
                                st.session_state.result = event.result.model_dump(mode="json")
                        result = st.session_state.result
                        progress.update(
                            label="Đã kết thúc lượt xử lý",
                            expanded=False,
                            state="error" if result["status"] == "failed" else "complete",
                        )
            except Exception as exc:
                st.error(f"Không hoàn tất lượt xử lý ({type(exc).__name__}). Bạn có thể thử lại.")
    result = st.session_state.get("result")
    if result:
        if result["status"] == "reviewed":
            st.info("Đã có đánh giá tự động. Hãy đối chiếu nguồn; đánh giá có thể sai.")
            st.markdown(result["final_response"])
        elif result["status"] == "insufficient_evidence":
            st.warning("Chưa đủ bằng chứng để trả lời đầy đủ.")
            st.markdown(result["final_response"])
        elif result["status"] == "out_of_scope":
            st.info("Tác vụ này hiện ngoài phạm vi. Hãy hỏi về nhận diện hoặc lịch sử công trình.")
        else:
            st.warning(
                "Chưa hoàn tất kiểm chứng. Câu trả lời chưa được công bố; hãy thử lại hoặc bổ sung ảnh."
            )
        for source in result["judge_report"].get("sources", []):
            with st.expander(source["title"]):
                st.write(source["snippet"])
                st.link_button("Mở nguồn", source["url"])
                st.caption(
                    f"Nguồn: {source['source_id']} · Truy cập: {source.get('retrieved_at') or 'chưa ghi nhận'}"
                )
        navigation = (
            result["expert_results"]
            .get("knowledge", {})
            .get("meta", {})
            .get("navigation_links", [])
        )
        if navigation:
            st.caption("Liên kết điều hướng; chưa xác minh tọa độ hoặc bằng chứng lịch sử.")
            for link in navigation:
                st.link_button(link["title"], link["url"])
        st.download_button(
            "Tải kết quả và metadata",
            json.dumps(result, ensure_ascii=False, indent=2),
            file_name=f"heritage-{result['run_id']}.json",
            mime="application/json",
        )
        with st.expander("Thông tin nghiên cứu của lượt xử lý"):
            st.json({k: v for k, v in result.items() if k != "draft_response"})
    comparison = st.session_state.get("comparison")
    if comparison:
        st.warning("So sánh mô tả; chưa có evaluator độc lập, chưa kết luận phương pháp thắng.")
        for note in comparison["limitations"]:
            st.caption(note)
        st.table(
            [
                {
                    "Phương pháp": row["method"],
                    "Trạng thái": row["status"],
                    "Thời gian (s)": round(row["duration"], 2),
                    "Lượt gọi": len(row["calls"]),
                }
                for row in comparison["rows"]
            ]
        )
        for row in comparison["rows"]:
            with st.expander(row["method"]):
                if row["answer"]:
                    st.caption("Đầu ra thử nghiệm; không phải đáp án chuẩn.")
                    st.markdown(row["answer"])
                else:
                    st.write(row["status"])
        st.download_button(
            "Tải dữ liệu so sánh",
            json.dumps(comparison, ensure_ascii=False, indent=2),
            "comparison.json",
            "application/json",
        )


if __name__ == "__main__":
    main()
