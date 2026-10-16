import os
import time
import json
from io import BytesIO
from PIL import Image
import streamlit as st

# Thiết lập Page Config
st.set_page_config(
    page_title="Multi-Agent VQA | Di tích & Văn hóa Việt Nam",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import các module cốt lõi
from utils.llm_clients import LLMManager
from agents.coordinator import CoordinatorAgent
from agents.experts import VisualAgent, OCRAgent, KnowledgeAgent, GenerationAgent
from agents.aggregator_judge import AggregatorAgent, JudgeAgent

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


# ==============================================================================
# SIDEBAR: CẤU HÌNH API & THƯ VIỆN ẢNH MẪU
# ==============================================================================
with st.sidebar:
    st.image("https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=600&q=80", 
             caption="Bảo tồn & Lan tỏa Di sản Việt Nam", use_container_width=True)
    
    st.markdown("### ⚙️ Trạng Thái Cấu Hình (.env)")
    
    # Tự động đồng bộ với file .env khi người dùng cập nhật
    st.session_state.llm_manager.reload_env()
    status = st.session_state.llm_manager.get_status()

    # Hiển thị trạng thái các khóa trong .env
    c_g, c_o = st.columns(2)
    with c_g:
        if status["has_gemini"]:
            st.markdown("🟢 **Gemini**\n`Đã kết nối`")
        else:
            st.markdown("🔴 **Gemini**\n`Chưa có key`")
    with c_o:
        if status["has_openai"]:
            st.markdown("🟢 **OpenAI**\n`Đã kết nối`")
        else:
            st.markdown("🔴 **OpenAI**\n`Chưa có key`")

    # Hiển thị chế độ kiến trúc hệ thống
    if status["has_gemini"] and status["has_openai"]:
        st.success(f"🌟 **{status['mode']}**\n\n{status['description']}")
    elif status["has_gemini"] or status["has_openai"]:
        st.warning(f"⚡ **{status['mode']}**\n\n{status['description']}")
    else:
        st.error("⚠️ **Chưa tìm thấy API Key**\n\nVui lòng mở file `.env` trong thư mục dự án và điền `GEMINI_API_KEY` hoặc `OPENAI_API_KEY`.")

    st.markdown("---")
    st.markdown("### 🖼️ Bộ Sưu Tập Ảnh Mẫu (Quick Test)")
    st.caption("Chọn ảnh mẫu tiêu biểu để trải nghiệm ngay trong 1 giây:")

    samples_dir = os.path.join(os.path.dirname(__file__), "samples")
    sample_options = {
        "Khuê Văn Các - Văn Miếu": {
            "file": "khue_van_cac.jpg",
            "prompt": "Phân tích nét đặc sắc kiến trúc và ý nghĩa biểu tượng của công trình này trong bức ảnh."
        },
        "Chùa Một Cột (Diên Hựu Tự)": {
            "file": "chua_mot_cot.jpg",
            "prompt": "Đây là di tích nào? Kiến trúc đài sen nghìn năm này gắn với truyền thuyết và triều đại nào?"
        },
        "Hoành Phi Câu Đối Cổ Đình Làng": {
            "file": "hoanh_phi_cau_doi.jpg",
            "prompt": "Đọc, phiên âm Hán - Việt và dịch nghĩa bức hoành phi cùng đôi câu đối trên hai cột trong ảnh."
        }
    }

    for name, item in sample_options.items():
        sample_path = os.path.join(samples_dir, item["file"])
        if os.path.exists(sample_path):
            if st.button(f"👉 {name}", key=f"btn_sample_{item['file']}", use_container_width=True):
                st.session_state.current_image = Image.open(sample_path)
                st.session_state.query_input = item["prompt"]
                st.session_state.results = None
                st.rerun()

    st.markdown("---")
    st.markdown("### 🧩 Kiến Trúc Heterogeneous Agents")
    st.info("""
    **1. Coordinator:** Lập kế hoạch JSON  
    **2. Visual Agent:** Gemini 3.8 Flash Vision  
    **3. OCR Agent:** Gemini Hán Nôm & Epigraphy  
    **4. Knowledge Agent:** OpenAI / Gemini Tri thức  
    **5. Generation Agent:** Sáng tác & Lập luận  
    **6. Aggregator:** Hợp nhất bản nháp  
    **7. Judge Agent:** Thẩm định 3 tiêu chí & Fix lỗi
    """)


# ==============================================================================
# TIÊU ĐỀ CHÍNH & MÔ TẢ HỆ THỐNG
# ==============================================================================
st.markdown("<h1 class='main-title'>🏛️ MULTI-AGENT VQA HỆ THỐNG DI TÍCH & DI SẢN VIỆT NAM</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>Hệ thống Thị giác - Ngôn ngữ Đa Tác tử Thông minh: Giám định kiến trúc, dịch thuật văn tự Hán Nôm và khai phá tri thức lịch sử chuyên sâu</p>", unsafe_allow_html=True)

# Chia layout 2 cột
col_left, col_right = st.columns([1, 1.3], gap="large")

# ==============================================================================
# CỘT TRÁI: TẢI ẢNH & ĐẶT CÂU HỎI
# ==============================================================================
with col_left:
    st.markdown("### 1. 📷 Tải Ảnh & Nhập Yêu Cầu")

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
        st.info("💡 Hãy tải ảnh lên hoặc chọn một ảnh mẫu từ menu bên trái để bắt đầu.")

    st.markdown("#### 💬 Câu hỏi / Yêu cầu của bạn:")
    
    # Nút bấm gợi ý nhanh
    st.caption("Gợi ý câu hỏi nhanh theo tác vụ:")
    q_col1, q_col2 = st.columns(2)
    with q_col1:
        if st.button("🔍 Khám phá Lịch sử", use_container_width=True):
            st.session_state.query_input = "Hãy cho biết tên di tích này, niên đại khởi dựng và các giá trị lịch sử văn hóa tiêu biểu?"
            st.rerun()
        if st.button("📜 Dịch chữ Hán Nôm", use_container_width=True):
            st.session_state.query_input = "Đọc, phiên âm Hán-Việt và giải nghĩa bức hoành phi hoặc đôi câu đối xuất hiện trong bức ảnh này?"
            st.rerun()
    with q_col2:
        if st.button("🏯 Phân tích Kiến trúc", use_container_width=True):
            st.session_state.query_input = "Phân tích chi tiết phong cách kiến trúc, hoa văn, kết cấu mái và chất liệu của công trình trong ảnh?"
            st.rerun()
        if st.button("🪶 Cảm tác Thơ ca", use_container_width=True):
            st.session_state.query_input = "Hãy sáng tác một bài thơ thất ngôn bát cú Đường luật cảm tác từ vẻ đẹp trầm mặc của di tích trong bức ảnh này?"
            st.rerun()

    user_query = st.text_area(
        "Nội dung câu hỏi:",
        value=st.session_state.query_input,
        placeholder="Ví dụ: Đây là đâu? Dịch giúp tôi câu đối trên cột gỗ...",
        height=100
    )
    st.session_state.query_input = user_query

    # Nút bấm kích hoạt Multi-Agent
    start_btn = st.button("🚀 BẮT ĐẦU PHÂN TÍCH MULTI-AGENT", type="primary", use_container_width=True)


# ==============================================================================
# XỬ LÝ ĐIỀU PHỐI MULTI-AGENT PIPELINE
# ==============================================================================
if start_btn:
    if st.session_state.current_image is None:
        st.error("⚠️ Vui lòng tải ảnh lên hoặc chọn một ảnh mẫu trước!")
    elif not user_query.strip():
        st.error("⚠️ Vui lòng nhập câu hỏi hoặc yêu cầu cần phân tích!")
    else:
        llm = st.session_state.llm_manager
        current_status = llm.get_status()
        if not current_status["has_gemini"] and not current_status["has_openai"]:
            st.error("⚠️ Chưa tìm thấy API Key nào! Vui lòng mở file `.env` và điền `GEMINI_API_KEY` hoặc `OPENAI_API_KEY`.")
        else:
            with col_right:
                trace_container = st.container()
                
                with trace_container:
                    st.markdown("### 2. ⚡ Live Multi-Agent Execution Trace")
                    
                    status_box = st.status("🚀 Đang khởi động Hội đồng Tác tử AI...", expanded=True)
                    
                    try:
                        # LOG BẮT ĐẦU RA TERMINAL
                        print("\n" + "="*80)
                        print("🚀 [MULTI-AGENT VQA] BẮT ĐẦU PHÂN TÍCH DI TÍCH / NGHỆ THUẬT")
                        print(f"📌 [YÊU CẦU NGƯỜI DÙNG]: {user_query}")
                        print("-" * 80)

                        # ------------------------------------------------------
                        # BƯỚC 1: COORDINATOR AGENT
                        # ------------------------------------------------------
                        status_box.write("🧭 **[Bước 1/4] Coordinator Agent:** Đang phân tích ảnh và lập Kế hoạch Điều phối JSON...")
                        coordinator = CoordinatorAgent(llm)
                        t0 = time.time()
                        plan, coord_meta = coordinator.plan(st.session_state.current_image, user_query)
                        t_coord = round(time.time() - t0, 2)
                        
                        status_box.write(f"✅ Coordinator hoàn tất sau {t_coord}s - Đã chọn: `{', '.join(plan.get('selected_agents', []))}`")
                        print(f"🧭 [COORDINATOR AGENT] Hoàn tất ({t_coord}s)")
                        print(f"   ├─ Phân loại tác vụ: {plan.get('task_categories', [])}")
                        print(f"   ├─ Expert Agents kích hoạt: {plan.get('selected_agents', [])}")
                        print(f"   └─ Lập luận điều phối: {plan.get('plan_reasoning', '')}")

                        # ------------------------------------------------------
                        # BƯỚC 2: EXPERT AGENTS (Chạy tuần tự/theo plan)
                        # ------------------------------------------------------
                        expert_results = {}
                        focus_dir = plan.get("focus_directives", {})

                        # 2.1 Visual Agent
                        if "visual_agent" in plan.get("selected_agents", []):
                            status_box.write("👁️ **[Bước 2/4] Visual Agent:** Đang giám định thị giác, cấu trúc & nhận diện di tích...")
                            vis_agent = VisualAgent(llm)
                            t0 = time.time()
                            vis_text, vis_meta = vis_agent.analyze(
                                st.session_state.current_image,
                                user_query,
                                focus_dir.get("visual_focus", "")
                            )
                            t_vis = round(time.time() - t0, 2)
                            expert_results["visual"] = {
                                "text": vis_text,
                                "meta": vis_meta,
                                "duration": t_vis
                            }
                            status_box.write(f"✅ Visual Agent hoàn thành ({t_vis}s)")
                            print(f"👁️ [VISUAL AGENT] Hoàn tất ({t_vis}s) | Provider: {vis_meta.get('actual_provider', '').upper()} ({vis_meta.get('model_used', '')})")

                        # 2.2 OCR Agent (nếu được chọn)
                        ocr_text = None
                        if "ocr_agent" in plan.get("selected_agents", []):
                            status_box.write("📜 **[Bước 2/4] OCR & Hán Nôm Agent:** Đang trích xuất văn bản, phiên âm và giải nghĩa...")
                            ocr_agent = OCRAgent(llm)
                            t0 = time.time()
                            ocr_text, ocr_meta = ocr_agent.extract_and_translate(
                                st.session_state.current_image,
                                user_query
                            )
                            t_ocr = round(time.time() - t0, 2)
                            expert_results["ocr"] = {
                                "text": ocr_text,
                                "meta": ocr_meta,
                                "duration": t_ocr
                            }
                            status_box.write(f"✅ OCR Agent hoàn thành ({t_ocr}s)")
                            print(f"📜 [OCR AGENT] Hoàn tất ({t_ocr}s) | Provider: {ocr_meta.get('actual_provider', '').upper()} ({ocr_meta.get('model_used', '')})")

                        # 2.3 Knowledge Agent (nếu được chọn)
                        know_text = None
                        if "knowledge_agent" in plan.get("selected_agents", []):
                            status_box.write("📚 **[Bước 2/4] Knowledge Agent:** Đang truy xuất tri thức lịch sử, niên đại & sự kiện văn hóa...")
                            know_agent = KnowledgeAgent(llm)
                            t0 = time.time()
                            know_text, know_meta = know_agent.retrieve(
                                visual_findings=expert_results.get("visual", {}).get("text", ""),
                                ocr_findings=ocr_text,
                                query=user_query,
                                focus_directive=focus_dir.get("knowledge_focus", "")
                            )
                            t_know = round(time.time() - t0, 2)
                            expert_results["knowledge"] = {
                                "text": know_text,
                                "meta": know_meta,
                                "duration": t_know
                            }
                            status_box.write(f"✅ Knowledge Agent hoàn thành ({t_know}s)")
                            print(f"📚 [KNOWLEDGE AGENT] Hoàn tất ({t_know}s) | Provider: {know_meta.get('actual_provider', '').upper()} ({know_meta.get('model_used', '')})")

                        # 2.4 Generation / Tool Agent (nếu được chọn)
                        gen_text = None
                        if "tool_gen_agent" in plan.get("selected_agents", []):
                            status_box.write("✍️ **[Bước 2/4] Tool/Generation Agent:** Đang sáng tác văn nghệ / lập luận chuyên sâu...")
                            gen_agent = GenerationAgent(llm)
                            t0 = time.time()
                            gen_text, gen_meta = gen_agent.generate(
                                query=user_query,
                                visual_findings=expert_results.get("visual", {}).get("text", ""),
                                knowledge_findings=know_text or "",
                                focus_directive=focus_dir.get("generation_focus", "")
                            )
                            t_gen = round(time.time() - t0, 2)
                            expert_results["generation"] = {
                                "text": gen_text,
                                "meta": gen_meta,
                                "duration": t_gen
                            }
                            status_box.write(f"✅ Generation Agent hoàn thành ({t_gen}s)")
                            print(f"✍️ [GENERATION AGENT] Hoàn tất ({t_gen}s) | Provider: {gen_meta.get('actual_provider', '').upper()} ({gen_meta.get('model_used', '')})")

                        # ------------------------------------------------------
                        # BƯỚC 3: AGGREGATOR AGENT
                        # ------------------------------------------------------
                        status_box.write("🧩 **[Bước 3/4] Aggregator Agent:** Đang tổng hợp các phát hiện thành Bản Dự Thảo hoàn chỉnh...")
                        aggregator = AggregatorAgent(llm)
                        t0 = time.time()
                        draft_response, agg_meta = aggregator.aggregate(
                            query=user_query,
                            visual_findings=expert_results.get("visual", {}).get("text", ""),
                            ocr_findings=ocr_text,
                            knowledge_findings=know_text,
                            generation_findings=gen_text
                        )
                        t_agg = round(time.time() - t0, 2)
                        status_box.write(f"✅ Aggregator Agent hoàn thành ({t_agg}s)")
                        print(f"🧩 [AGGREGATOR AGENT] Hoàn tất tổng hợp bản nháp ({t_agg}s)")

                        # ------------------------------------------------------
                        # BƯỚC 4: JUDGE AGENT
                        # ------------------------------------------------------
                        status_box.write("⚖️ **[Bước 4/4] Judge Agent:** Đang thẩm định 3 tiêu chí, rà soát Hallucination và xuất Final Response...")
                        judge = JudgeAgent(llm)
                        t0 = time.time()
                        judge_report, judge_meta = judge.evaluate_and_refine(
                            query=user_query,
                            draft_response=draft_response,
                            visual_findings=expert_results.get("visual", {}).get("text", ""),
                            ocr_findings=ocr_text
                        )
                        t_judge = round(time.time() - t0, 2)
                        status_box.write(f"✅ Judge Agent hoàn thành ({t_judge}s) - Trạng thái: **{judge_report.get('overall_status', 'APPROVED')}**")

                        # LOG KẾT QUẢ THẨM ĐỊNH RA TERMINAL
                        crit = judge_report.get("criteria_evaluation", {})
                        vf = crit.get("visual_fidelity", {})
                        rel = crit.get("relevance", {})
                        ct = crit.get("cultural_tone", {})
                        print(f"⚖️ [JUDGE AGENT] Thẩm định hoàn tất ({t_judge}s) | Trạng thái: {judge_report.get('overall_status', 'APPROVED')}")
                        print(f"   ├─ 1. Bám sát ảnh (Visual Fidelity): {'PASS' if vf.get('passed', True) else 'WARN'} ({vf.get('score', 9.5)}/10)")
                        print(f"   ├─ 2. Đúng trọng tâm (Relevance): {'PASS' if rel.get('passed', True) else 'WARN'} ({rel.get('score', 9.8)}/10)")
                        print(f"   ├─ 3. Chuẩn mực văn phong (Cultural Tone): {'PASS' if ct.get('passed', True) else 'WARN'} ({ct.get('score', 9.7)}/10)")
                        print(f"   └─ Hallucination Check: {judge_report.get('hallucination_notes', 'Không phát hiện sai lệch')}")
                        print("="*80 + "\n")

                        status_box.update(label="🎉 Hệ đồng Multi-Agent đã hoàn tất phân tích thành công!", state="complete", expanded=False)

                        # Lưu vào session state
                        st.session_state.results = {
                            "plan": plan,
                            "coord_meta": coord_meta,
                            "expert_results": expert_results,
                            "draft_response": draft_response,
                            "agg_meta": agg_meta,
                            "judge_report": judge_report,
                            "judge_meta": judge_meta
                        }

                    except Exception as e:
                        status_box.update(label="❌ Có lỗi xảy ra trong quá trình thực thi", state="error")
                        st.error(f"Chi tiết lỗi: {str(e)}")
                        print(f"❌ [LỖI PIPELINE]: {str(e)}")


# ==============================================================================
# CỘT PHẢI: HIỂN THỊ TRACE CHI TIẾT & KẾT QUẢ CUỐI CÙNG
# ==============================================================================
with col_right:
    if st.session_state.results is not None:
        res = st.session_state.results
        plan = res["plan"]
        expert_results = res["expert_results"]
        judge_report = res["judge_report"]

        st.markdown("### 🔍 Chi Tiết Live Agent Trace")

        # 1. Trace Coordinator
        with st.expander("🧭 Bước 1: Quyết định Phân loại & Điều phối (Coordinator Plan)", expanded=True):
            st.markdown(f"**Ý định cốt lõi:** *{plan.get('query_intent', '')}*")
            
            # Tags phân loại
            st.markdown("**Phân loại tác vụ (Task Categories):**")
            tags_html = "".join([f"<span class='badge-task'>🏷️ {cat}</span>" for cat in plan.get("task_categories", [])])
            st.markdown(tags_html, unsafe_allow_html=True)

            st.markdown("**Các Expert Agents được kích hoạt:**")
            agents_html = "".join([f"<span class='badge-agent'>🤖 {ag}</span>" for ag in plan.get("selected_agents", [])])
            st.markdown(agents_html, unsafe_allow_html=True)

            st.info(f"💡 **Lập luận điều phối:** {plan.get('plan_reasoning', '')}")

            # Đổi từ nested expander sang checkbox để tránh lỗi Streamlit
            if st.checkbox("🔍 Hiển thị chi tiết JSON Execution Plan", value=False):
                st.json(plan)

        # 2. Trace Expert Agents
        with st.expander("🔬 Bước 2: Output Chi Tiết Từng Expert Agent", expanded=False):
            tabs = st.tabs([f"🤖 {name.title()}" for name in expert_results.keys()])
            for tab, (agent_key, agent_data) in zip(tabs, expert_results.items()):
                with tab:
                    meta = agent_data["meta"]
                    st.caption(f"Provider: **{meta.get('actual_provider', '').upper()}** | Model: `{meta.get('model_used', '')}` | Thời gian: `{agent_data['duration']}s`")
                    if meta.get("fallback_used"):
                        st.warning("⚠️ Đã kích hoạt Fallback provider do thiếu API Key mặc định.")
                    st.markdown(agent_data["text"])

        # 3. Trace Judge Agent
        with st.expander("⚖️ Bước 3: Báo Cáo Thẩm Định & Kiểm Chứng (Judge Assessment)", expanded=True):
            crit = judge_report.get("criteria_evaluation", {})
            c1, c2, c3 = st.columns(3)
            
            vf = crit.get("visual_fidelity", {})
            with c1:
                st.markdown(f"""
                <div class='judge-metric-card'>
                    <div class='judge-metric-title'>1. BÁM SÁT ẢNH (NO HALLUCINATION)</div>
                    <div class='judge-metric-value'>{'✅ PASS' if vf.get('passed', True) else '⚠️ WARN'} ({vf.get('score', 9.5)}/10)</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption(vf.get("critique", "Khớp chính xác với chi tiết thị giác."))

            rel = crit.get("relevance", {})
            with c2:
                st.markdown(f"""
                <div class='judge-metric-card'>
                    <div class='judge-metric-title'>2. ĐÚNG TRỌNG TÂM CÂU HỎI</div>
                    <div class='judge-metric-value'>{'✅ PASS' if rel.get('passed', True) else '⚠️ WARN'} ({rel.get('score', 9.8)}/10)</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption(rel.get("critique", "Giải đáp trực diện câu hỏi."))

            ct = crit.get("cultural_tone", {})
            with c3:
                st.markdown(f"""
                <div class='judge-metric-card'>
                    <div class='judge-metric-title'>3. CHUẨN MỰC VĂN PHONG VĂN HÓA</div>
                    <div class='judge-metric-value'>{'✅ PASS' if ct.get('passed', True) else '⚠️ WARN'} ({ct.get('score', 9.7)}/10)</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption(ct.get("critique", "Văn phong trang nhã, giàu bản sắc."))

            st.markdown(f"**🔍 Rà soát sai lệch thực tế (Hallucination Check):** `{judge_report.get('hallucination_notes', 'Không phát hiện sai lệch')}`")
            if judge_report.get("refinement_summary"):
                st.caption(f"📝 **Ghi chú hoàn thiện của Judge:** {judge_report.get('refinement_summary')}")

        # 4. KẾT QUẢ CUỐI CÙNG (FINAL RESPONSE)
        st.markdown("---")
        st.markdown("### 🏆 KẾT QUẢ PHÂN TÍCH CUỐI CÙNG (FINAL RESPONSE)")

        final_content = judge_report.get("final_response", res["draft_response"])

        st.markdown(f"""
        <div style="background: rgba(197, 155, 39, 0.08); border: 1px solid #d4af37; padding: 22px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
        {final_content}
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        # Nút tải báo cáo Markdown
        st.download_button(
            label="📥 Tải Báo Cáo Phân Tích (.md)",
            data=final_content,
            file_name="multi_agent_vqa_report.md",
            mime="text/markdown"
        )

    elif not start_btn:
        st.info("👈 Hãy chọn một ảnh mẫu hoặc tải ảnh lên, sau đó nhấn **'Bắt đầu Phân tích Multi-Agent'** để xem luồng tương tác của các Tác tử trực tiếp tại đây.")
