"""Streamlit adapter for the shared workflow; session state never stores SDK clients."""

import hashlib
import json
import logging
import os
from io import BytesIO
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from core.gateway import LLMManager
from core.images import image_bytes, validate_image
from core.observability import TraceSettings
from core.presentation import STAGES, collect_sources
from core.runtime_logging import configure_local_logging, log_event
from ui.api_client import RemoteManager
from ui.components import render_comparison, render_progress, render_result, render_stages
from ui.session import (
    clear_active,
    clear_history,
    prune_session,
    remember_run,
    save_bookmark,
    set_question,
)
from ui.theme import apply_theme
from workflow.comparison import compare
from workflow.service import RunService

SAMPLE_NAMES = {
    "chua_mot_cot": "Chùa Một Cột",
    "khue_van_cac": "Khuê Văn Các",
    "ho_guom": "Hồ Gươm",
    "chua_huong": "Chùa Hương",
}
PROMPTS = [
    (
        "Nhận diện công trình",
        "Đây có thể là công trình nào? Những chi tiết nào trong ảnh giúp nhận diện?",
    ),
    ("Khám phá kiến trúc", "Hãy mô tả các chi tiết kiến trúc nhìn thấy rõ trong ảnh."),
    ("Tìm hiểu lịch sử", "Công trình này có lịch sử như thế nào? Hãy đối chiếu và trích nguồn."),
    ("Phân biệt bằng chứng", "Điểm nào có thể quan sát trực tiếp và điểm nào cần thêm tư liệu?"),
]


def current_view():
    st.session_state["history_view"] = "current"


def start_run():
    current_view()
    clear_active(st.session_state)


def rotate_image():
    st.session_state["rotation"] = (st.session_state.get("rotation", 0) + 90) % 360
    current_view()


def sidebar(manager):
    with st.sidebar:
        st.subheader("Không gian khám phá")
        choices = (
            ["Hỏi bằng ảnh"]
            if isinstance(manager, RemoteManager)
            else ["Hỏi bằng ảnh", "So sánh thử nghiệm"]
        )
        if st.session_state.get("mode") not in choices:
            st.session_state["mode"] = choices[0]
        mode = st.radio(
            "Chọn cách sử dụng",
            choices,
            key="mode",
            on_change=current_view,
        )
        audience = st.selectbox(
            "Cách diễn đạt",
            ["tourist", "student"],
            key="audience",
            format_func=lambda v: "Khách tham quan" if v == "tourist" else "Học sinh",
            on_change=current_view,
        )
        show_stages = st.toggle("Hiển thị kết quả từng bước", value=True, key="show_stages")
        show_draft = st.toggle("Xem bản nháp chưa đánh giá", value=False, key="show_draft")
        if show_draft:
            st.caption("Bản nháp chỉ để quan sát quá trình; chưa phải nội dung đã được đánh giá.")
        st.divider()
        st.subheader("Lịch sử phiên")
        history = st.session_state.get("history", [])
        only_saved = st.checkbox("Chỉ lượt đã đánh dấu", key="only_saved")
        available = [
            item
            for item in history
            if not only_saved
            or st.session_state.get("saved_runs", {}).get(item["result"]["run_id"], False)
        ]
        lookup = {item["result"]["run_id"]: item for item in available}
        options = ["current", *lookup]
        if st.session_state.get("history_view", "current") not in options:
            st.session_state["history_view"] = "current"
        selected = st.selectbox(
            "Xem lại lượt xử lý",
            options,
            key="history_view",
            format_func=lambda v: (
                "Lượt hiện tại"
                if v == "current"
                else f"{lookup[v]['result']['query'][:42]} · {v[:6]}"
            ),
        )
        st.caption(
            "Giữ tối đa 8 lượt trong phiên trình duyệt này; không lưu sau khi kết thúc phiên."
        )
        st.button(
            "Xóa lịch sử phiên",
            key="clear_history",
            disabled=not history,
            on_click=clear_history,
            args=(st.session_state,),
        )
        with st.expander("Cấu hình nghiên cứu"):
            status = manager.get_status()
            for role, binding in status["roles"].items():
                st.caption(
                    f"{role}: {binding['provider']} / {binding['model']} · "
                    f"{'Đã cấu hình' if binding['configured'] else 'Thiếu cấu hình'}"
                )
            st.caption(status["description"])
            st.caption(f"Workflow: {manager.config.workflow_version}")
            tracing = TraceSettings.from_env()
            st.caption(f"LangSmith: {'bật' if tracing.enabled else 'tắt'} · {tracing.project}")
    return mode, audience, show_stages, show_draft, lookup.get(selected)


def prepare_image(data, config):
    if not data:
        return None
    raw_hash = hashlib.sha256(data).hexdigest()
    if st.session_state.get("raw_image_hash") != raw_hash:
        st.session_state["raw_image_hash"] = raw_hash
        st.session_state["rotation"] = 0
    rotation = st.session_state.get("rotation", 0)
    cache_key = (raw_hash, rotation, config.max_image_bytes, config.max_image_pixels)
    if st.session_state.get("normalized_key") != cache_key:
        normalized = validate_image(data, config)
        if rotation:
            with Image.open(BytesIO(normalized)) as image:
                normalized = image_bytes(image.rotate(rotation, expand=True))
        st.session_state["normalized_key"] = cache_key
        st.session_state["normalized_image"] = normalized
    return st.session_state["normalized_image"]


def image_input(config):
    st.markdown("### 1. Chọn một góc nhìn")
    source = st.radio(
        "Nguồn ảnh",
        ["Ảnh mẫu", "Tải ảnh", "Camera"],
        key="image_source",
        horizontal=True,
        on_change=current_view,
    )
    data = None
    if source == "Ảnh mẫu":
        paths = sorted(
            p
            for p in (Path(__file__).parent / "samples").glob("*")
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        sample = st.selectbox(
            "Chọn ảnh mẫu",
            [None, *paths],
            key="sample",
            on_change=current_view,
            format_func=lambda p: (
                "Chọn ảnh để bắt đầu"
                if p is None
                else SAMPLE_NAMES.get(p.stem, p.stem.replace("_", " "))
            ),
        )
        if sample:
            data = sample.read_bytes()
    elif source == "Tải ảnh":
        upload = st.file_uploader(
            "Tải ảnh công trình",
            type=["jpg", "jpeg", "png", "webp"],
            key="upload",
            on_change=current_view,
            help=f"Giới hạn {config.max_image_bytes / 1_000_000:g} MB; không lưu ảnh ngoài phiên.",
        )
        data = upload.getvalue() if upload else None
    else:
        photo = st.camera_input("Chụp ảnh công trình", key="camera", on_change=current_view)
        data = photo.getvalue() if photo else None
        st.caption("Camera cần quyền trình duyệt và kết nối HTTPS hoặc localhost.")
    try:
        normalized = prepare_image(data, config)
    except ValueError as exc:
        st.error(str(exc))
        return None
    if normalized:
        st.image(normalized, width="stretch")
        with Image.open(BytesIO(normalized)) as image:
            width, height = image.size
        st.caption(f"{width} × {height} px · Ảnh đã được chuẩn hóa và bỏ thông tin EXIF.")
        st.button("Xoay ảnh 90°", key="rotate", on_click=rotate_image)
        if min(width, height) < 320:
            st.warning(
                "Ảnh có độ phân giải thấp. Chọn ảnh rõ và đủ sáng để quan sát chi tiết tốt hơn."
            )
    else:
        st.info("Chọn ảnh mẫu, tải ảnh hoặc dùng camera để bắt đầu khám phá.")
    with st.expander("Mẹo để có kết quả tốt hơn"):
        st.write(
            "Chụp toàn cảnh công trình, giữ ảnh thẳng và đủ sáng. Nếu hỏi chi tiết, hãy dùng thêm ảnh cận cảnh trong lượt tiếp theo."
        )
        st.write(
            "Hệ thống có thể nhận diện nhầm khi nhiều công trình có kiến trúc giống nhau. Tên sơ bộ cần được đối chiếu với tư liệu."
        )
    return normalized


def execute(manager, image_data, query, audience, mode, show_stages, show_draft, *, review_of=None):
    st.session_state.pop("run_error", None)
    placeholder = st.empty()
    st.session_state["live_events"] = []
    try:
        if mode == "So sánh thử nghiệm":
            with st.spinner("Đang chạy các phương pháp; chưa chấm độ chính xác..."):
                st.session_state["comparison"] = compare(image_data, query, manager, audience)
        else:
            stream = (
                (
                    manager.remote_review_stream(image_data, review_of)
                    if isinstance(manager, RemoteManager)
                    else RunService(manager).review_stream(image_data, review_of)
                )
                if review_of
                else (
                    manager.remote_stream(image_data, query, audience)
                    if isinstance(manager, RemoteManager)
                    else RunService(manager).stream(image_data, query, audience)
                )
            )
            for event in stream:
                if event.kind == "completed":
                    result = event.result.model_dump(mode="json")
                    st.session_state["result"] = result
                    st.session_state["history"] = remember_run(
                        st.session_state.get("history", []),
                        result,
                        image_data,
                    )
                    prune_session(st.session_state)
                else:
                    st.session_state["live_events"].append(event.model_dump(exclude={"result"}))
                    if event.node not in STAGES:
                        continue
                    with placeholder.container():
                        st.subheader("Đang khám phá · cập nhật từ workflow")
                        events = st.session_state["live_events"]
                        render_progress(events)
                        if show_stages:
                            render_stages(
                                events,
                                show_draft=show_draft,
                                sources=collect_sources({"events": events}),
                                live=True,
                            )
        placeholder.empty()
    except Exception as exc:
        placeholder.empty()
        log_event("ui.run_failed", level=logging.ERROR, error=exc)
        st.session_state["run_error"] = type(exc).__name__
        from core.preflight import PreflightFailed

        if isinstance(exc, PreflightFailed):
            st.session_state["run_error"] = "; ".join(
                f"{r['role']}: {r['error_code']}" for r in exc.failures
            )
        elif getattr(exc, "error_code", None):
            failures = [
                r for r in getattr(exc, "details", {}).get("roles", []) if not r.get("ready")
            ]
            st.session_state["run_error"] = (
                "; ".join(f"{r['role']}: {r.get('error_code')}" for r in failures) or exc.error_code
            )
    finally:
        manager.close()


def main():
    st.set_page_config(
        page_title="Di sản Việt Nam · Khám phá qua ảnh", page_icon="🏛️", layout="wide"
    )
    apply_theme()
    try:
        load_dotenv()
        configure_local_logging()
        if base_url := os.getenv("HERITAGE_API_URL"):
            prior = st.session_state.get("_api_connection", {})
            token = os.getenv("HERITAGE_API_TOKEN") or (
                prior.get("token") if prior.get("url") == base_url else None
            )
            manager = RemoteManager(
                base_url, token=token, bootstrap_token=os.getenv("API_BOOTSTRAP_TOKEN")
            )
            st.session_state["_api_connection"] = {"url": base_url, "token": manager.token}
        else:
            manager = LLMManager()
    except Exception as exc:
        log_event("ui.initialization_failed", level=logging.ERROR, error=exc)
        st.error(f"Cấu hình chưa hợp lệ ({type(exc).__name__}). Kiểm tra HERITAGE_CONFIG.")
        st.stop()
    if st.session_state.pop("_review_finished", False):
        current_view()
    mode, audience, show_stages, show_draft, historical = sidebar(manager)
    image_column, question_column = st.columns([1, 1.35], gap="large")
    with image_column, st.container(border=True):
        image_data = image_input(manager.config)
    with question_column, st.container(border=True):
        st.markdown("### 2. Bạn muốn khám phá điều gì?")
        st.caption("Chọn gợi ý hoặc đặt câu hỏi riêng; các gợi ý chỉ điền câu hỏi, chưa gọi model.")
        for index, (label, question) in enumerate(PROMPTS):
            st.button(
                label,
                key=f"prompt_{index}",
                on_click=set_question,
                args=(st.session_state, question),
                width="stretch",
            )
        query = st.text_area(
            "Câu hỏi của bạn",
            key="query",
            height=145,
            max_chars=4000,
            on_change=current_view,
            placeholder="Ví dụ: Những chi tiết nào trong ảnh giúp nhận diện công trình?",
        )
        st.caption(
            f"{len(query.strip())}/4.000 ký tự · "
            + (
                "Diễn đạt cho khách tham quan"
                if audience == "tourist"
                else "Diễn đạt dễ học, dễ nhớ"
            )
        )
        start = st.button(
            "Khám phá bức ảnh" if mode == "Hỏi bằng ảnh" else "Chạy so sánh",
            type="primary",
            key="start",
            on_click=start_run,
            disabled=image_data is None or not query.strip(),
            width="stretch",
        )
        st.caption(
            "Câu trả lời được hình thành từ ảnh và nguồn truy xuất. Đánh giá tự động vẫn có thể sai."
        )
    input_key = hashlib.sha256(
        json.dumps(
            [
                hashlib.sha256(image_data or b"").hexdigest(),
                query.strip(),
                audience,
                mode,
                manager.capabilities["config_hash"]
                if isinstance(manager, RemoteManager)
                else manager.config.snapshot()["config_hash"],
            ]
        ).encode()
    ).hexdigest()
    if st.session_state.get("input_key") != input_key:
        clear_active(st.session_state)
        st.session_state["input_key"] = input_key
    if start:
        historical = None
        execute(manager, image_data, query, audience, mode, show_stages, show_draft)
        if st.session_state.get("result") or st.session_state.get("comparison"):
            st.rerun()
    if error := st.session_state.get("run_error"):
        st.error(
            f"Lượt xử lý bị gián đoạn ({error}). Có thể thử lại; kết quả từng bước đã nhận vẫn được giữ bên dưới."
        )
        events = st.session_state.get("live_events", [])
        render_progress(events)
        if show_stages:
            render_stages(
                events, show_draft=show_draft, sources=collect_sources({"events": events})
            )
    result = historical["result"] if historical else st.session_state.get("result")
    if result:
        st.divider()
        from workflow.service import validate_review_parent

        try:
            validate_review_parent(result)
            review_ready = True
        except (ValueError, TypeError):
            review_ready = False
        stored = next(
            (
                item
                for item in st.session_state.get("history", [])
                if item["result"]["run_id"] == result["run_id"]
            ),
            None,
        )
        review_image = stored.get("image_data") if stored else None
        if st.button(
            "Đánh giá lại",
            key="review_again",
            disabled=not review_ready or review_image is None,
            help="Chỉ gọi Judge với bản nháp, ảnh và nguồn đã lưu. Giữ nguyên lượt gốc.",
        ):
            execute(
                manager,
                review_image,
                result["query"],
                result["audience"],
                "review",
                show_stages,
                show_draft,
                review_of=result,
            )
            st.session_state["_review_finished"] = True
            st.rerun()
        if historical:
            st.image(historical["thumbnail"], width=240)
        run_id = result["run_id"]
        st.session_state.setdefault(
            f"saved_widget_{run_id}", st.session_state.get("saved_runs", {}).get(run_id, False)
        )
        st.checkbox(
            "Đánh dấu lượt khám phá này",
            key=f"saved_widget_{run_id}",
            on_change=save_bookmark,
            args=(st.session_state, run_id),
        )
        render_result(
            result, show_stages=show_stages, show_draft=show_draft, history=bool(historical)
        )
    elif st.session_state.get("comparison"):
        st.divider()
        render_comparison(st.session_state["comparison"])
    elif not st.session_state.get("run_error"):
        st.markdown("### Từ một bức ảnh đến câu trả lời có căn cứ")
        for column, title, description in zip(
            st.columns(3),
            ["Quan sát", "Đối chiếu", "Khám phá"],
            [
                "Tách chi tiết nhìn thấy và giả thuyết nhận diện.",
                "Xem đoạn nguồn, bản gốc và kết quả đánh giá.",
                "Đặt câu hỏi tiếp theo, xem bản đồ và lưu báo cáo.",
            ],
            strict=True,
        ):
            with column, st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(description)


if __name__ == "__main__":
    main()
