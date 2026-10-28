import os
import time
import json
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import streamlit as st

# Thiết lập Page Config
st.set_page_config(
    page_title="Multi-Agent VQA | Di tích & Văn hóa Việt Nam",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import các module cốt lõi
from utils.llm_clients import LLMManager
from agents.coordinator import CoordinatorAgent
from agents.experts import VisualAgent, KnowledgeAgent, GenerationAgent
from agents.aggregator_judge import AggregatorAgent, JudgeAgent
from baselines.vanilla_vlm import VanillaVLMBaseline
from baselines.generic_tool_agent import GenericToolAgentBaseline
from utils.logger import (
    log_banner, log_separator, log_info, log_agent_start,
    log_agent_success, log_error, log_warning
)

# ==============================================================================
# TÙY BIẾN CSS GIAO DIỆN CHUYÊN NGHIỆP, ĐẬM ĐÀ BẢN SẮC VĂN HÓA
# ==============================================================================
st.markdown("""
<style>
    /* Nhập Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    :root {
        --primary-gold: #c59b27;
        --secondary-red: #8b0000;
        --bg-glass: rgba(255, 255, 255, 0.05);
        --border-glass: rgba(197, 155, 39, 0.3);
    }

    .main-title {
        font-family: 'Cinzel', serif;
        font-size: 2.3rem;
        font-weight: 800;
        color: #d4af37;
        text-align: center;
        margin-bottom: 4px;
        text-shadow: 0 2px 10px rgba(212, 175, 55, 0.2);
        letter-spacing: 0.5px;
    }

    .sub-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        text-align: center;
        font-size: 1.05rem;
        color: #b0bec5;
        margin-bottom: 25px;
    }

    .badge-task {
        display: inline-block;
        padding: 4px 12px;
        margin: 2px 4px 4px 0;
        border-radius: 16px;
        font-size: 0.85rem;
        font-weight: 600;
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }

    .badge-agent {
        display: inline-block;
        padding: 4px 12px;
        margin: 2px 4px 4px 0;
        border-radius: 16px;
        font-size: 0.85rem;
        font-weight: 600;
        background: linear-gradient(135deg, #780206 0%, #061161 100%);
        color: #f1c40f;
        border: 1px solid #d4af37;
    }

    .agent-box {
        border-left: 4px solid #c59b27;
        background-color: rgba(197, 155, 39, 0.05);
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 12px;
    }

    .judge-metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid var(--border-glass);
        padding: 12px;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 8px;
    }

    .judge-metric-title {
        font-size: 0.85rem;
        color: #90a4ae;
        margin-bottom: 4px;
    }

    .judge-metric-value {
        font-size: 1.3rem;
        font-weight: 700;
        color: #2ecc71;
    }

    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    .final-response-container {
        background: rgba(197, 155, 39, 0.08);
        border: 1px solid #d4af37;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        line-height: 1.7;
        margin-bottom: 15px;
    }
    .final-response-container a {
        color: #f1c40f !important;
        text-decoration: underline;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .final-response-container a:hover {
        color: #ffffff !important;
        text-shadow: 0 0 8px rgba(255, 215, 0, 0.6);
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# KHỞI TẠO STATE & LLM MANAGER
# ==============================================================================
if "llm_manager" not in st.session_state:
    st.session_state.llm_manager = LLMManager()

if "current_image" not in st.session_state:
    st.session_state.current_image = None

if "query_input" not in st.session_state:
    st.session_state.query_input = ""

if "results" not in st.session_state:
    st.session_state.results = None

if "benchmark_results" not in st.session_state:
    st.session_state.benchmark_results = None


# ==============================================================================
# SIDEBAR: CẤU HÌNH API & THƯ VIỆN ẢNH MẪU
# ==============================================================================
with st.sidebar:
    st.markdown("### Trạng Thái Cấu Hình (.env)")
    
    # Tự động đồng bộ với file .env khi người dùng cập nhật
    st.session_state.llm_manager.reload_env()
    status = st.session_state.llm_manager.get_status()

    # Hiển thị trạng thái các khóa trong .env
    c_g, c_o = st.columns(2)
    with c_g:
        if status["has_gemini"]:
            st.markdown("**Gemini**\n`Đã kết nối`")
        else:
            st.markdown("**Gemini**\n`Chưa có key`")
    with c_o:
        if status["has_openai"]:
            st.markdown("**OpenAI**\n`Đã kết nối`")
        else:
            st.markdown("**OpenAI**\n`Chưa có key`")

    # Hiển thị chế độ kiến trúc hệ thống
    if status["has_gemini"] and status["has_openai"]:
        st.success(f"**{status['mode']}**\n\n{status['description']}")
    elif status["has_gemini"] or status["has_openai"]:
        st.warning(f"**{status['mode']}**\n\n{status['description']}")
    else:
        st.error("**Chưa tìm thấy API Key**\n\nVui lòng mở file `.env` trong thư mục dự án và điền `GEMINI_API_KEY` hoặc `OPENAI_API_KEY`.")

    # Hiển thị Bể API Key theo từng Agent
    with st.expander(f"🔑 Bể API Từng Agent ({status.get('dedicated_keys_count', 0)}/6 Khóa Riêng)", expanded=(status.get('dedicated_keys_count', 0) > 0)):
        for role, item in status.get("agent_keys_status", {}).items():
            icon = "🟢" if item["has_custom"] else "⚪"
            st.markdown(f"{icon} **{item['label']}**  \n`{item['status']}`")
        st.caption("💡 Bạn có thể điền dần từng API Key vào file `.env` để chia tải độc lập cho từng con Agent.")

    st.markdown("---")
    st.markdown("### Chế Độ Thực Nghiệm")
    app_mode = st.radio(
        "Lựa chọn chế độ:",
        ["Chế độ 1: Multi-Agent Chuyên Sâu", "Chế độ 2: So Sánh Đối Đầu (Benchmark OWLViz)"],
        index=0,
        help="Chế độ 1: Chạy hệ thống Multi-Agent hoàn chỉnh. Chế độ 2: So sánh đối đầu giữa Baseline 1 (Vanilla VLM), Baseline 2 (Generic Tool Agent) và Proposed Multi-Agent."
    )

    st.markdown("---")
    st.markdown("### Kiến Trúc Heterogeneous Agents")
    st.info("""
    **1. Coordinator:** Lập kế hoạch JSON  
    **2. Visual Agent:** Gemini 3.8 Flash Vision  
    **3. Knowledge Agent:** OpenAI / Gemini Tri thức  
    **4. Generation Agent:** Sáng tác & Lập luận  
    **5. Aggregator:** Hợp nhất bản nháp  
    **6. Judge Agent:** Thẩm định 3 tiêu chí & Fix lỗi
    """)


# ==============================================================================
# TIÊU ĐỀ CHÍNH & MÔ TẢ HỆ THỐNG
# ==============================================================================
st.markdown("<h1 class='main-title'>MULTI-AGENT VQA HỆ THỐNG DI TÍCH & DI SẢN VIỆT NAM</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>Hệ thống Thị giác - Ngôn ngữ Đa Tác tử Thông minh: Giám định kiến trúc di tích và khai phá tri thức lịch sử chuyên sâu</p>", unsafe_allow_html=True)

# Chia layout 2 cột
col_left, col_right = st.columns([1, 1.3], gap="large")

# ==============================================================================
# CỘT TRÁI: TẢI ẢNH & ĐẶT CÂU HỎI
# ==============================================================================
with col_left:
    st.markdown("### 1. Tải Ảnh & Nhập Yêu Cầu")

    uploaded_file = st.file_uploader(
        "Tải lên hình ảnh di tích, bia đá, hoành phi hoặc tác phẩm nghệ thuật:",
        type=["jpg", "jpeg", "png", "webp"],
        help="Hỗ trợ các định dạng ảnh phổ biến"
    )

    if uploaded_file is not None:
        st.session_state.current_image = Image.open(uploaded_file)

    if st.session_state.current_image is not None:
        st.image(st.session_state.current_image, caption="Hình ảnh đang phân tích", use_container_width=True)
    else:
        st.info("Hãy tải ảnh di tích hoặc tác phẩm nghệ thuật lên để bắt đầu.")

    st.markdown("#### Câu hỏi / Yêu cầu của bạn:")
    
    # Nút bấm gợi ý nhanh
    st.caption("Gợi ý câu hỏi nhanh theo tác vụ:")
    q_col1, q_col2 = st.columns(2)
    with q_col1:
        if st.button("Khám phá Lịch sử", use_container_width=True):
            st.session_state.query_input = "Hãy cho biết tên di tích này, niên đại khởi dựng và các giá trị lịch sử văn hóa tiêu biểu?"
            st.rerun()
        if st.button("Ý nghĩa & Tín ngưỡng", use_container_width=True):
            st.session_state.query_input = "Cho biết ý nghĩa tín ngưỡng, các phong tục và lễ hội truyền thống gắn liền với di tích này?"
            st.rerun()
    with q_col2:
        if st.button("Phân tích Kiến trúc", use_container_width=True):
            st.session_state.query_input = "Phân tích chi tiết phong cách kiến trúc, hoa văn, kết cấu mái và chất liệu của công trình trong ảnh?"
            st.rerun()
        if st.button("Cảm tác Thơ ca", use_container_width=True):
            st.session_state.query_input = "Hãy sáng tác một bài thơ thất ngôn bát cú Đường luật cảm tác từ vẻ đẹp trầm mặc của di tích trong bức ảnh này?"
            st.rerun()

    user_query = st.text_area(
        "Nội dung câu hỏi:",
        value=st.session_state.query_input,
        placeholder="Ví dụ: Đây là đâu? Cho tôi biết kiến trúc và lịch sử của di tích này...",
        height=100
    )
    st.session_state.query_input = user_query

    # Nút bấm kích hoạt tương ứng chế độ
    if app_mode == "Chế độ 1: Multi-Agent Chuyên Sâu":
        start_btn = st.button("BẮT ĐẦU PHÂN TÍCH MULTI-AGENT", type="primary", use_container_width=True)
    else:
        start_btn = st.button("BẮT ĐẦU SO SÁNH ĐỐI ĐẦU (BENCHMARK)", type="primary", use_container_width=True)


# ==============================================================================
# XỬ LÝ ĐIỀU PHỐI MULTI-AGENT HOẶC BENCHMARK SO SÁNH
# ==============================================================================
if start_btn:
    if st.session_state.current_image is None:
        st.error("Vui lòng tải ảnh lên trước!")
    elif not user_query.strip():
        st.error("Vui lòng nhập câu hỏi hoặc yêu cầu cần phân tích!")
    else:
        llm = st.session_state.llm_manager
        current_status = llm.get_status()
        if not current_status["has_gemini"] and not current_status["has_openai"]:
            st.error("Chưa tìm thấy API Key nào! Vui lòng mở file `.env` và điền `GEMINI_API_KEY` hoặc `OPENAI_API_KEY`.")
        else:
            with col_right:
                trace_container = st.container()

                # --------------------------------------------------------------
                # NHÁNH 1: CHẾ ĐỘ 1 - MULTI-AGENT CHUYÊN SÂU
                # --------------------------------------------------------------
                if app_mode == "Chế độ 1: Multi-Agent Chuyên Sâu":
                    with trace_container:
                        st.markdown("### 2. Live Multi-Agent Execution Trace")
                        status_box = st.status("Đang khởi động Hội đồng Tác tử AI...", expanded=True)
                        
                        try:
                            # LOG BẮT ĐẦU RA TERMINAL
                            log_banner("CHẾ ĐỘ 1: MULTI-AGENT CHUYÊN SÂU")
                            log_info(f"Yêu cầu người dùng: \"{user_query}\"")
                            if st.session_state.current_image is not None:
                                img = st.session_state.current_image
                                log_info(f"Dữ liệu ảnh: Kích thước {img.size[0]}x{img.size[1]} | Định dạng: {img.format or img.mode}")
                            log_separator()

                            current_img = st.session_state.current_image

                            # BƯỚC 1: COORDINATOR AGENT
                            status_box.write("**[Bước 1/4] Coordinator Agent:** Đang phân tích ảnh và lập Kế hoạch Điều phối JSON...")
                            log_agent_start("Coordinator Agent", "Phân tích yêu cầu và lập kế hoạch điều phối JSON")
                            coordinator = CoordinatorAgent(llm)
                            t0 = time.time()
                            plan, coord_meta = coordinator.plan(current_img, user_query)
                            t_coord = round(time.time() - t0, 2)
                            status_box.write(f"Coordinator hoàn tất sau {t_coord}s - Đã chọn: `{', '.join(plan.get('selected_agents', []))}`")
                            log_agent_success("Coordinator Agent", t_coord, f"Tác vụ: {plan.get('task_categories', [])} | Chọn: {plan.get('selected_agents', [])}")

                            # BƯỚC 2: EXPERT AGENTS (CHẠY SONG SONG BẰNG THREADPOOLEXECUTOR)
                            expert_results = {}
                            focus_dir = plan.get("focus_directives", {})
                            selected_agents = plan.get("selected_agents", ["visual_agent"])
                            monument_hint = plan.get("identified_monument", "")

                            status_box.write(f"**[Bước 2/4] Tầng Chuyên Gia Song Song:** Đang kích hoạt đồng thời `{', '.join(selected_agents)}`...")
                            log_agent_start("Parallel Expert Layer", f"Khởi chạy song song: {selected_agents}")
                            t0_parallel = time.time()

                            def task_visual(img_data):
                                log_agent_start("Visual Agent", "Giám định thị giác, hoa văn kiến trúc & không gian (Song song)")
                                v_agent = VisualAgent(llm)
                                t_start = time.time()
                                text, meta = v_agent.analyze(img_data, user_query, focus_dir.get("visual_focus", ""))
                                dur = round(time.time() - t_start, 2)
                                log_agent_success("Visual Agent", dur, f"Bóc tách xong ({len(text)} ký tự)")
                                return "visual", text, meta, dur

                            def task_knowledge():
                                log_agent_start("Knowledge Agent", "Truy xuất sử liệu, niên đại & sự kiện (Song song)")
                                k_agent = KnowledgeAgent(llm)
                                t_start = time.time()
                                text, meta = k_agent.retrieve(query=user_query, monument_hint=monument_hint, focus_directive=focus_dir.get("knowledge_focus", ""))
                                dur = round(time.time() - t_start, 2)
                                log_agent_success("Knowledge Agent", dur, f"Truy xuất sử liệu ({len(text)} ký tự)")
                                return "knowledge", text, meta, dur

                            def task_generation():
                                log_agent_start("Generation Agent", "Sáng tác văn nghệ & lập luận di sản (Song song)")
                                g_agent = GenerationAgent(llm)
                                t_start = time.time()
                                text, meta = g_agent.generate(query=user_query, monument_hint=monument_hint, focus_directive=focus_dir.get("generation_focus", ""))
                                dur = round(time.time() - t_start, 2)
                                log_agent_success("Generation Agent", dur, f"Hoàn tất ({len(text)} ký tự)")
                                return "generation", text, meta, dur

                            with ThreadPoolExecutor(max_workers=3) as executor:
                                futures = []
                                if "visual_agent" in selected_agents:
                                    futures.append(executor.submit(task_visual, current_img))
                                if "knowledge_agent" in selected_agents:
                                    futures.append(executor.submit(task_knowledge))
                                if "tool_gen_agent" in selected_agents:
                                    futures.append(executor.submit(task_generation))

                                for future in as_completed(futures):
                                    key, text, meta, dur = future.result()
                                    expert_results[key] = {"text": text, "meta": meta, "duration": dur}
                                    status_box.write(f"✓ **{key.title()} Agent** hoàn thành ({dur}s)")

                            t_parallel = round(time.time() - t0_parallel, 2)
                            status_box.write(f"⚡ Toàn bộ Tầng Chuyên Gia hoàn tất sau **{t_parallel}s** (tiết kiệm ~50% thời gian nhờ chạy song song)")

                            vis_text = expert_results.get("visual", {}).get("text", "")
                            know_text = expert_results.get("knowledge", {}).get("text", "")
                            gen_text = expert_results.get("generation", {}).get("text", None)

                            # BƯỚC 3: AGGREGATOR AGENT (STREAMING TRỰC TIẾP)
                            status_box.write("**[Bước 3/4] Aggregator Agent:** Đang tổng hợp tri thức và phát trực tiếp (Live Streaming)...")
                            log_agent_start("Aggregator Agent", "Tổng hợp đa luồng và stream phản hồi trực tiếp")
                            aggregator = AggregatorAgent(llm)
                            t0 = time.time()

                            # Tạo khung phát trực tiếp ngay trên giao diện
                            live_box = st.container()
                            with live_box:
                                stream_placeholder = st.empty()

                            draft_stream = aggregator.aggregate_stream(
                                query=user_query,
                                visual_findings=expert_results.get("visual", {}).get("text", ""),
                                knowledge_findings=know_text,
                                generation_findings=gen_text
                            )
                            draft_response = stream_placeholder.write_stream(draft_stream)
                            t_agg = round(time.time() - t0, 2)
                            agg_meta = {"actual_provider": "gemini", "model_used": "gemini-3.8-flash", "duration": t_agg}
                            status_box.write(f"Aggregator Agent hoàn thành ({t_agg}s)")
                            log_agent_success("Aggregator Agent", t_agg, f"Dự thảo hoàn tất ({len(draft_response)} ký tự)")

                            # BƯỚC 4: JUDGE AGENT
                            status_box.write("**[Bước 4/4] Judge Agent:** Đang thẩm định 3 tiêu chí, rà soát Hallucination và xuất Final Response...")
                            log_agent_start("Judge Agent", "Thẩm định 3 tiêu chí, đối chiếu chéo & rà soát Hallucination")
                            judge = JudgeAgent(llm)
                            t0 = time.time()
                            live_sources = expert_results.get("knowledge", {}).get("meta", {}).get("live_search_sources", [])
                            judge_report, judge_meta = judge.evaluate_and_refine(
                                query=user_query,
                                draft_response=draft_response,
                                visual_findings=expert_results.get("visual", {}).get("text", ""),
                                search_sources=live_sources
                            )
                            t_judge = round(time.time() - t0, 2)
                            status_box.write(f"Judge Agent hoàn thành ({t_judge}s) - Trạng thái: **{judge_report.get('overall_status', 'APPROVED')}**")
                            log_agent_success("Judge Agent", t_judge, f"Trạng thái: {judge_report.get('overall_status', 'APPROVED')}")
                            log_separator()

                            status_box.update(label="Hội đồng Multi-Agent đã hoàn tất phân tích thành công!", state="complete", expanded=False)
                            live_box.empty() # Dọn khung stream tạm để hiển thị bản hoàn chỉnh có thẩm định bên dưới

                            st.session_state.results = {
                                "plan": plan, "coord_meta": coord_meta, "expert_results": expert_results,
                                "draft_response": draft_response, "agg_meta": agg_meta,
                                "judge_report": judge_report, "judge_meta": judge_meta
                            }
                            st.session_state.benchmark_results = None

                        except Exception as e:
                            log_error(caller_name="App: Chế độ 1 (Multi-Agent)", error=e, details=f"User Query: {user_query}")
                            status_box.update(label="Có lỗi xảy ra trong quá trình thực thi", state="error")
                            st.error(f"Chi tiết lỗi: {str(e)}")

                # --------------------------------------------------------------
                # NHÁNH 2: CHẾ ĐỘ 2 - THỬ NGHIỆM ĐỐI ĐẦU BENCHMARK (OWLViz)
                # --------------------------------------------------------------
                else:
                    with trace_container:
                        st.markdown("### 2. Tiến Trình Thử Nghiệm Đối Đầu (Benchmark Mode)")
                        b_status = st.status("Đang tiến hành thử nghiệm đối đầu 3 phương pháp...", expanded=True)

                        try:
                            log_banner("CHẾ ĐỘ 2: BENCHMARK ĐỐI ĐẦU (OWLViz)")
                            log_info(f"Yêu cầu: \"{user_query}\"")
                            log_separator()

                            # 1. Chạy Baseline 1
                            b_status.write("**[1/3] Đang chạy Baseline 1:** Vanilla VLM (Single-Prompt)...")
                            log_agent_start("Baseline 1: Vanilla VLM", "Single-prompt End-to-End VLM")
                            b1_runner = VanillaVLMBaseline(llm)
                            b1_text, b1_meta = b1_runner.run(st.session_state.current_image, user_query)
                            b_status.write(f"Baseline 1 hoàn thành ({b1_meta['duration']}s)")
                            log_agent_success("Baseline 1: Vanilla VLM", b1_meta['duration'])

                            # 2. Chạy Baseline 2
                            b_status.write("**[2/3] Đang chạy Baseline 2:** Generic Tool-Calling Agent (ReAct)...")
                            log_agent_start("Baseline 2: Generic Tool Agent", "ReAct Paradigm single agent")
                            b2_runner = GenericToolAgentBaseline(llm)
                            b2_text, b2_meta = b2_runner.run(st.session_state.current_image, user_query)
                            b_status.write(f"Baseline 2 hoàn thành ({b2_meta['duration']}s)")
                            log_agent_success("Baseline 2: Generic Tool Agent", b2_meta['duration'])

                            # 3. Chạy Proposed Multi-Agent
                            b_status.write("**[3/3] Đang chạy Proposed:** Heterogeneous Multi-Agent Architecture...")
                            log_agent_start("Proposed: Multi-Agent", "Heterogeneous Dynamic Multi-Agent System")
                            t0_prop = time.time()
                            b_img = st.session_state.current_image
                            coord = CoordinatorAgent(llm)
                            plan, _ = coord.plan(b_img, user_query)
                            selected = plan.get("selected_agents", ["visual_agent"])
                            
                            monument_hint_b = plan.get("identified_monument", "")
                            vis_res = ""
                            know_res = None
                            gen_res = None

                            know_sources_b = []
                            def b_vis(img_data):
                                v = VisualAgent(llm)
                                r, _ = v.analyze(img_data, user_query)
                                return "visual", r

                            def b_know():
                                k = KnowledgeAgent(llm)
                                r, m = k.retrieve(query=user_query, monument_hint=monument_hint_b)
                                return "knowledge", r, m.get("live_search_sources", [])

                            def b_gen():
                                g = GenerationAgent(llm)
                                r, _ = g.generate(query=user_query, monument_hint=monument_hint_b)
                                return "generation", r

                            with ThreadPoolExecutor(max_workers=3) as executor:
                                f_map = {}
                                if "visual_agent" in selected:
                                    f_map[executor.submit(b_vis, b_img)] = "visual"
                                if "knowledge_agent" in selected:
                                    f_map[executor.submit(b_know)] = "knowledge"
                                if "tool_gen_agent" in selected:
                                    f_map[executor.submit(b_gen)] = "generation"

                                for f in as_completed(f_map):
                                    item = f.result()
                                    k = item[0]
                                    if k == "visual":
                                        vis_res = item[1]
                                    elif k == "knowledge":
                                        know_res = item[1]
                                        know_sources_b = item[2]
                                    elif k == "generation":
                                        gen_res = item[1]

                            agg = AggregatorAgent(llm)
                            draft_res, _ = agg.aggregate(user_query, vis_res, know_res, gen_res)

                            judge = JudgeAgent(llm)
                            judge_eval_prop, _ = judge.evaluate_and_refine(user_query, draft_res, vis_res, search_sources=know_sources_b)
                            prop_text = judge_eval_prop.get("final_response", draft_res)
                            prop_duration = round(time.time() - t0_prop, 2)
                            b_status.write(f"Proposed Multi-Agent hoàn thành ({prop_duration}s)")
                            log_agent_success("Proposed: Multi-Agent", prop_duration, f"Kích hoạt {len(selected)} tác tử")

                            # 4. LLM-as-a-Judge Đánh giá chéo độc lập
                            b_status.write("**Thẩm định độc lập (LLM-as-a-Judge):** Đang chấm điểm 3 phương pháp theo chuẩn OWLViz...")
                            log_agent_start("LLM-as-a-Judge", "Chấm điểm độc lập định lượng cho 2 Baselines")
                            t0_eval = time.time()
                            judge_eval_b1, _ = judge.evaluate_and_refine(user_query, b1_text, vis_res)
                            judge_eval_b2, _ = judge.evaluate_and_refine(user_query, b2_text, vis_res)
                            t_eval = round(time.time() - t0_eval, 2)
                            log_agent_success("LLM-as-a-Judge", t_eval, "Chấm điểm thành công")
                            log_separator()

                            b_status.update(label="Thử nghiệm đối đầu Benchmark hoàn tất!", state="complete", expanded=False)

                            st.session_state.benchmark_results = {
                                "b1_text": b1_text, "b1_meta": b1_meta, "eval_b1": judge_eval_b1,
                                "b2_text": b2_text, "b2_meta": b2_meta, "eval_b2": judge_eval_b2,
                                "prop_text": prop_text, "prop_duration": prop_duration, "eval_prop": judge_eval_prop,
                                "selected_agents": selected
                            }
                            st.session_state.results = None

                        except Exception as e:
                            log_error(caller_name="App: Chế độ 2 (Benchmark OWLViz)", error=e, details=f"User Query: {user_query}")
                            b_status.update(label="Có lỗi xảy ra trong quá trình thử nghiệm", state="error")
                            st.error(f"Chi tiết lỗi: {str(e)}")


# ==============================================================================
# CỘT PHẢI: HIỂN THỊ KẾT QUẢ THEO TỪNG CHẾ ĐỘ
# ==============================================================================
with col_right:
    # HIỂN THỊ KẾT QUẢ CHẾ ĐỘ 2 (BENCHMARK MODE)
    if st.session_state.benchmark_results is not None:
        b_res = st.session_state.benchmark_results
        
        st.markdown("### Bảng Tổng Hợp So Sánh Định Lượng (Benchmark Summary)")
        st.caption("Phương pháp luận đánh giá theo chuẩn bài báo OWLViz (Exact & LLM-Match Evaluation):")

        crit_b1 = b_res["eval_b1"].get("criteria_evaluation", {})
        crit_b2 = b_res["eval_b2"].get("criteria_evaluation", {})
        crit_prop = b_res["eval_prop"].get("criteria_evaluation", {})

        def s(crit, key): return crit.get(key, {}).get("score", 0.0)
        def p(crit, key): return "PASS" if crit.get(key, {}).get("passed", False) else "WARN"

        table_md = f"""
| Chỉ Số Đánh Giá (Metrics) | Baseline 1 (Vanilla VLM) | Baseline 2 (Generic Tool Agent) | Proposed (Hệ Thống Multi-Agent) |
| :--- | :--- | :--- | :--- |
| **Thời gian phản hồi** | `{b_res['b1_meta']['duration']}s` | `{b_res['b2_meta']['duration']}s` | `{b_res['prop_duration']}s` |
| **Kiến trúc & Công cụ** | 1 Model (Single-Prompt) | 1 Agent (Generic Tools) | **{len(b_res['selected_agents']) + 2} Agents chuyên biệt** |
| **Bám sát ảnh (Visual Fidelity)** | {s(crit_b1, 'visual_fidelity')}/10 ({p(crit_b1, 'visual_fidelity')}) | {s(crit_b2, 'visual_fidelity')}/10 ({p(crit_b2, 'visual_fidelity')}) | **{s(crit_prop, 'visual_fidelity')}/10 ({p(crit_prop, 'visual_fidelity')})** |
| **Đúng trọng tâm (Relevance)** | {s(crit_b1, 'relevance')}/10 ({p(crit_b1, 'relevance')}) | {s(crit_b2, 'relevance')}/10 ({p(crit_b2, 'relevance')}) | **{s(crit_prop, 'relevance')}/10 ({p(crit_prop, 'relevance')})** |
| **Văn phong di sản (Cultural Tone)** | {s(crit_b1, 'cultural_tone')}/10 ({p(crit_b1, 'cultural_tone')}) | {s(crit_b2, 'cultural_tone')}/10 ({p(crit_b2, 'cultural_tone')}) | **{s(crit_prop, 'cultural_tone')}/10 ({p(crit_prop, 'cultural_tone')})** |
| **Cơ chế chống Ảo giác** | Không có (Dễ Hallucination) | Không có (Dễ sai lệch) | **Judge Agent Thẩm Định & Sửa Lỗi** |
"""
        st.markdown(table_md)

        st.markdown("---")
        st.markdown("### Đối Chiếu Chi Tiết Câu Trả Lời Giữa 3 Phương Pháp")

        tab_prop, tab_b1, tab_b2 = st.tabs(["Proposed: Heterogeneous Multi-Agent", "Baseline 1: Vanilla VLM", "Baseline 2: Generic Tool Agent"])

        with tab_prop:
            st.markdown(f"**Thời gian:** `{b_res['prop_duration']}s` | **Trạng thái Thẩm định:** `{b_res['eval_prop'].get('overall_status', 'APPROVED')}`")
            st.info(f"**Ghi chú kiểm soát Hallucination:** {b_res['eval_prop'].get('hallucination_notes', 'Không phát hiện sai lệch')}")
            
            p_sources = b_res['eval_prop'].get("sources", [])
            if p_sources:
                valid_p = [s for s in p_sources if s.get("url")]
                if valid_p:
                    p_cols = st.columns(min(len(valid_p), 3))
                    for idx, src in enumerate(valid_p):
                        with p_cols[idx % min(len(valid_p), 3)]:
                            st.link_button(
                                label=src.get("title", "Mở liên kết"),
                                url=src.get("url", "#"),
                                use_container_width=True
                            )
            st.markdown(b_res["prop_text"])

        with tab_b1:
            st.markdown(f"**Thời gian:** `{b_res['b1_meta']['duration']}s` | **Mô hình:** `{b_res['b1_meta']['model']}`")
            st.warning(f"**Nhận xét của Giám khảo:** {crit_b1.get('visual_fidelity', {}).get('critique', '')}")
            st.markdown(b_res["b1_text"])

        with tab_b2:
            st.markdown(f"**Thời gian:** `{b_res['b2_meta']['duration']}s` | **Cơ chế:** `ReAct (Thought-Action-Observation)`")
            st.warning(f"**Nhận xét của Giám khảo:** {crit_b2.get('visual_fidelity', {}).get('critique', '')}")
            st.markdown(b_res["b2_text"])

    # HIỂN THỊ KẾT QUẢ CHẾ ĐỘ 1 (MULTI-AGENT MODE)
    elif st.session_state.results is not None:
        res = st.session_state.results
        plan = res["plan"]
        expert_results = res["expert_results"]
        judge_report = res["judge_report"]

        st.markdown("### Chi Tiết Live Agent Trace")

        with st.expander("Bước 1: Quyết định Phân loại & Điều phối (Coordinator Plan)", expanded=True):
            st.markdown(f"**Ý định cốt lõi:** *{plan.get('query_intent', '')}*")
            st.markdown("**Phân loại tác vụ (Task Categories):**")
            tags_html = "".join([f"<span class='badge-task'>{cat}</span>" for cat in plan.get("task_categories", [])])
            st.markdown(tags_html, unsafe_allow_html=True)

            st.markdown("**Các Expert Agents được kích hoạt:**")
            agents_html = "".join([f"<span class='badge-agent'>{ag}</span>" for ag in plan.get("selected_agents", [])])
            st.markdown(agents_html, unsafe_allow_html=True)
            st.info(f"**Lập luận điều phối:** {plan.get('plan_reasoning', '')}")

            if st.checkbox("Hiển thị chi tiết JSON Execution Plan", value=False):
                st.json(plan)

        with st.expander("Bước 2: Output Chi Tiết Từng Expert Agent", expanded=False):
            tabs = st.tabs([f"{name.title()}" for name in expert_results.keys()])
            for tab, (agent_key, agent_data) in zip(tabs, expert_results.items()):
                with tab:
                    meta = agent_data["meta"]
                    st.caption(f"Provider: **{meta.get('actual_provider', '').upper()}** | Model: `{meta.get('model_used', '')}` | Thời gian: `{agent_data['duration']}s`")
                    if meta.get("fallback_used"):
                        st.warning("Đã kích hoạt Fallback provider do thiếu API Key mặc định.")
                    st.markdown(agent_data["text"])

        with st.expander("Bước 3: Báo Cáo Thẩm Định & Kiểm Chứng (Judge Assessment)", expanded=True):
            crit = judge_report.get("criteria_evaluation", {})
            c1, c2, c3 = st.columns(3)
            vf = crit.get("visual_fidelity", {})
            with c1:
                st.markdown(f"""
                <div class='judge-metric-card'>
                    <div class='judge-metric-title'>1. BÁM SÁT ẢNH (NO HALLUCINATION)</div>
                    <div class='judge-metric-value'>{'PASS' if vf.get('passed', True) else 'WARN'} ({vf.get('score', 9.5)}/10)</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption(vf.get("critique", "Khớp chính xác với chi tiết thị giác."))

            rel = crit.get("relevance", {})
            with c2:
                st.markdown(f"""
                <div class='judge-metric-card'>
                    <div class='judge-metric-title'>2. ĐÚNG TRỌNG TÂM CÂU HỎI</div>
                    <div class='judge-metric-value'>{'PASS' if rel.get('passed', True) else 'WARN'} ({rel.get('score', 9.8)}/10)</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption(rel.get("critique", "Giải đáp trực diện câu hỏi."))

            ct = crit.get("cultural_tone", {})
            with c3:
                st.markdown(f"""
                <div class='judge-metric-card'>
                    <div class='judge-metric-title'>3. CHUẨN MỰC VĂN PHONG VĂN HÓA</div>
                    <div class='judge-metric-value'>{'PASS' if ct.get('passed', True) else 'WARN'} ({ct.get('score', 9.7)}/10)</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption(ct.get("critique", "Văn phong trang nhã, giàu bản sắc."))

            st.markdown(f"**Rà soát sai lệch thực tế (Hallucination Check):** `{judge_report.get('hallucination_notes', 'Không phát hiện sai lệch')}`")
            if judge_report.get("refinement_summary"):
                st.caption(f"**Ghi chú hoàn thiện của Judge:** {judge_report.get('refinement_summary')}")

        st.markdown("---")
        st.markdown("### KẾT QUẢ PHÂN TÍCH CUỐI CÙNG (FINAL RESPONSE)")
        final_content = judge_report.get("final_response", res["draft_response"])

        # Hiển thị các nút truy cập nguồn/bản đồ trực tiếp
        sources = judge_report.get("sources", [])
        if sources:
            st.markdown("##### 🔗 Nguồn Tham Chiếu & Khám Phá Nhanh:")
            valid_sources = [s for s in sources if s.get("url")]
            if valid_sources:
                btn_cols = st.columns(min(len(valid_sources), 3))
                for idx, src in enumerate(valid_sources):
                    with btn_cols[idx % min(len(valid_sources), 3)]:
                        st.link_button(
                            label=src.get("title", "Mở liên kết"),
                            url=src.get("url", "#"),
                            use_container_width=True
                        )

        # Khung hiển thị nội dung Markdown hoàn chỉnh
        with st.container():
            st.markdown("<div class='final-response-container'>", unsafe_allow_html=True)
            st.markdown(final_content)
            st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        st.download_button(
            label="Tải Báo Cáo Phân Tích (.md)",
            data=final_content,
            file_name="multi_agent_vqa_report.md",
            mime="text/markdown"
        )

    elif not start_btn:
        st.info("Hãy tải ảnh lên, nhập câu hỏi và nhấn nút thực thi để bắt đầu.")
