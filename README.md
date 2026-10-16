# 🏛️ HỆ THỐNG MULTI-AGENT VQA DI TÍCH LỊCH SỬ & VĂN HÓA NGHỆ THUẬT VIỆT NAM

Hệ thống Hỏi - Đáp thị giác (Visual Question Answering - VQA) chuyên sâu về **Di tích lịch sử, Cổ vật và Tác phẩm nghệ thuật Việt Nam**, được xây dựng trên nền tảng **Kiến trúc Đa Tác tử (Heterogeneous Multi-Agent)** phối hợp linh hoạt giữa Google Gemini và OpenAI.

---

## 🌟 TÍNH NĂNG NỔI BẬT

1. **Điều phối Tác tử Thông minh (Coordinator Agent / Planner & Router):**
   - Phân loại đa tác vụ: `QA_Fact`, `Visual_Description`, `OCR_Translation`, `Creative`, `Knowledge_Search`.
   - Sinh kế hoạch thực thi dạng JSON (Execution Plan), chỉ kích hoạt các Expert Agent cần thiết để tối ưu chi phí và độ trễ.

2. **Chuyên gia Giám định Thị giác (Visual Expert Agent - Gemini Multimodal):**
   - Bóc tách kiến trúc cổ: Mái đao, ngói âm dương, bờ nóc rồng chầu, hệ vì kèo, cột gỗ lim, nền đá cổ.
   - Cung cấp bằng chứng thị giác trực tiếp (Visual Evidence) từ ảnh.

3. **Chuyên gia Văn tự & Hán Nôm (OCR & Epigraphy Agent - Gemini Multimodal):**
   - Nhận diện và đọc chữ Hán Nôm trên hoành phi, câu đối, bia đá, biển chỉ dẫn.
   - Phiên âm Hán-Việt chuẩn xác, dịch nghĩa tiếng Việt hiện đại và giải mã triết lý văn hóa ẩn chứa.

4. **Chuyên gia Tri thức Lịch sử & Di sản (Knowledge Agent - OpenAI / Gemini):**
   - Truy xuất niên đại khởi dựng, triều đại (Lý, Trần, Lê, Nguyễn...), các danh nhân và sự tích gắn liền.
   - Cung cấp thông tin về các lễ hội truyền thống, sự kiện văn hóa và hoạt động thực tế tại di tích.

5. **Tác tử Sáng tạo & Lập luận (Creative / Generation Agent - OpenAI / Gemini):**
   - Sáng tác thơ thất ngôn bát cú / lục bát cổ phong cảm tác từ di tích.
   - So sánh đối chiếu phong cách mỹ thuật qua các thời kỳ lịch sử.

6. **Tác tử Tổng hợp (Aggregator Agent):**
   - Hợp nhất đa nguồn thành Bản dự thảo hoàn chỉnh (Draft Response).

7. **Hội đồng Thẩm định & Kiểm chứng (Judge Agent):**
   - Thẩm định 3 tiêu chí cốt lõi:
     - 🛡️ **Visual Fidelity:** Bám sát thực tế ảnh, kiểm soát và loại trừ hiện tượng Hallucination.
     - 🎯 **Relevance:** Trả lời đúng trọng tâm câu hỏi của người dùng.
     - 📜 **Cultural Tone:** Chuẩn mực văn phong văn hóa - lịch sử Việt Nam.
   - Tự động hiệu chỉnh bản nháp và xuất ra **Final Response**.

8. **Cơ chế Fallback Đa API An toàn (Robust Single / Dual API Fallback):**
   - Nếu có cả 2 key (`GEMINI_API_KEY` & `OPENAI_API_KEY`): Chạy kiến trúc Heterogeneous hoàn hảo.
   - Nếu chỉ có 1 trong 2 key: Tự động chuyển toàn bộ hệ thống sang key có sẵn để buổi thuyết trình không bao giờ bị gián đoạn.

---

## 📁 CẤU TRÚC THƯ MỤC DỰ ÁN

```
demo_new/
│
├── .env.example              # File cấu hình API keys mẫu
├── requirements.txt          # Danh sách thư viện Python
├── README.md                 # Hướng dẫn chi tiết & Kịch bản thuyết trình
├── app.py                    # Giao diện chính Streamlit với Live Agent Trace
│
├── utils/
│   ├── __init__.py
│   └── llm_clients.py        # Wrapper gọi Gemini & OpenAI, xử lý multimodal & JSON
│
├── agents/
│   ├── __init__.py
│   ├── coordinator.py        # Coordinator Agent (Planner/Router)
│   ├── experts.py            # Visual, OCR, Knowledge, Generation Agents
│   └── aggregator_judge.py   # Aggregator Agent & Judge Agent (Verifier)
│
└── samples/                  # Thư viện ảnh mẫu di tích Việt Nam có sẵn
    ├── khue_van_cac.jpg      # Khuê Văn Các - Văn Miếu Quốc Tử Giám
    ├── chua_mot_cot.jpg      # Chùa Một Cột (Diên Hựu Tự)
    └── hoanh_phi_cau_doi.jpg # Hoành phi câu đối cổ đình làng ("Quốc Thái Dân An")
```

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & CHẠY ỨNG DỤNG

### 1. Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### 2. Cấu hình API Key
Bạn có thể cấu hình file `.env` (tạo từ `.env.example`):
```env
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```
*Hoặc có thể nhập trực tiếp API Key trên thanh Sidebar của ứng dụng Web.*

### 3. Khởi chạy Ứng dụng Web Streamlit
```bash
streamlit run app.py
```
Ứng dụng sẽ tự động mở trên trình duyệt tại địa chỉ: `http://localhost:8501`.

---

## 🎤 KỊCH BẢN THUYẾT TRÌNH DEMO (DEMO SCRIPT CHO NGÀY MAI)

Để thuyết trình gây ấn tượng mạnh với Hội đồng đánh giá, hãy thực hiện theo 3 kịch bản mẫu sau:

### Kịch bản 1: Thử thách Đọc chữ Hán Nôm & Hoành phi câu đối (OCR & Translation)
1. Ở Sidebar, bấm chọn **"👉 Hoành Phi Câu Đối Cổ Đình Làng"**.
2. Câu hỏi sẽ tự điền: *"Đọc, phiên âm Hán - Việt và dịch nghĩa bức hoành phi cùng đôi câu đối trên hai cột trong ảnh."*
3. Bấm **"Bắt đầu Phân tích Multi-Agent"**:
   - **Chỉ ra cho Hội đồng thấy Live Trace:** Coordinator nhận diện có chữ viết nên **kích hoạt OCR Agent** và **Visual Agent**.
   - **Kết quả:** OCR Agent đọc chính xác 4 chữ hoành phi *"Quốc Thái Dân An"* (國泰民安) cùng đôi câu đối *"Thần công vạn cổ trường tồn"* / *"Thánh đạo thiên thu vĩnh chấn"*, dịch nghĩa và giải thích ý nghĩa tâm linh.
   - **Judge Agent** chấm điểm tích xanh và khẳng định không có hallucination.

### Kịch bản 2: Nhận diện Kiến trúc & Sự tích Lịch sử
1. Bấm chọn **"👉 Chùa Một Cột (Diên Hựu Tự)"**.
2. Nhấn nút nhanh **"🔍 Khám phá Lịch sử"**.
3. **Quan sát Live Trace:** Coordinator chỉ kích hoạt Visual Agent + Knowledge Agent (không kích hoạt OCR Agent vì không có văn tự cần dịch, giúp tối ưu tốc độ và chi phí!).
4. **Kết quả:** Trả về câu chuyện vua Lý Thái Tông nằm mộng Phật Bà Quan Âm dắt lên tòa sen năm 1049, kiến trúc cột đá độc nhất vô nhị.

### Kịch bản 3: Sáng tác Thơ Cổ Phong Cảm Tác (Creative Agent)
1. Bấm chọn **"👉 Khuê Văn Các - Văn Miếu"**.
2. Nhấn nút nhanh **"🪶 Cảm tác Thơ ca"**.
3. **Quan sát Live Trace:** Coordinator kích hoạt thêm **Tool / Generation Agent**.
4. **Kết quả:** Xuất hiện một bài thơ thất ngôn Đường luật ca ngợi biểu tượng ngàn năm văn hiến Thăng Long, chuẩn niêm luật và mang đậm khí chất văn hóa dân tộc.
