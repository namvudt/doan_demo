import re
import urllib.parse
from typing import Dict, Any, List, Optional
import requests

class HeritageSearchEngine:
    """
    Công cụ tìm kiếm trực tiếp (Live Direct Search & Grounding Engine) 
    dành riêng cho Di tích, Sử liệu và Văn hóa Việt Nam.
    Tự động truy xuất từ Wikipedia tiếng Việt, tạo liên kết Google Maps và Cổng Di sản.
    """
    def __init__(self, timeout: int = 6):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "HeritageVQABot/2.0 (Cultural Heritage Research Assistant; contact@heritage-vqa.edu.vn)"
        }

    def search_wikipedia(self, query: str, limit: int = 2) -> List[Dict[str, str]]:
        """Tìm kiếm bài viết chính thức trên Wikipedia tiếng Việt."""
        results = []
        try:
            api_url = "https://vi.wikipedia.org/w/api.php"
            
            # Làm sạch từ khóa để tìm kiếm chính xác
            clean_query = re.sub(r'(ở đâu|năm nào|ai xây|cho biết|hãy|phân tích|như thế nào|\?|\!|\.)', '', query, flags=re.IGNORECASE).strip()
            if not clean_query:
                clean_query = query.strip()

            # 1. Tìm danh sách bài viết
            params = {
                "action": "query",
                "list": "search",
                "srsearch": clean_query,
                "utf8": 1,
                "format": "json",
                "srlimit": limit
            }
            resp = requests.get(api_url, params=params, headers=self.headers, timeout=self.timeout)
            if resp.status_code != 200:
                return results

            search_items = resp.json().get("query", {}).get("search", [])
            if not search_items:
                return results

            # 2. Lấy chi tiết tóm tắt nội dung (extract) và URL chính thức
            titles = "|".join([item["title"] for item in search_items])
            detail_params = {
                "action": "query",
                "prop": "extracts|info",
                "inprop": "url",
                "exintro": 1,
                "explaintext": 1,
                "titles": titles,
                "format": "json"
            }
            detail_resp = requests.get(api_url, params=detail_params, headers=self.headers, timeout=self.timeout)
            if detail_resp.status_code == 200:
                pages = detail_resp.json().get("query", {}).get("pages", {})
                for page_id, pdata in pages.items():
                    if page_id != "-1":
                        title = pdata.get("title", "")
                        url = pdata.get("fullurl", f"https://vi.wikipedia.org/wiki/{urllib.parse.quote(title)}")
                        extract = pdata.get("extract", "").strip()
                        if extract:
                            # Cắt ngắn khoảng 500 ký tự đầu tiên
                            short_extract = extract[:600] + ("..." if len(extract) > 600 else "")
                            results.append({
                                "title": f"🏛️ {title} (Wikipedia)",
                                "url": url,
                                "snippet": short_extract,
                                "type": "wiki"
                            })
        except Exception:
            pass

        return results

    def generate_maps_link(self, monument_name: str) -> Dict[str, str]:
        """Tạo liên kết định vị tọa độ vệ tinh Google Maps cho di tích."""
        clean_name = re.sub(r'[\(\)\[\]]', '', monument_name).strip()
        encoded = urllib.parse.quote_plus(clean_name)
        return {
            "title": f"📍 Định vị vệ tinh: {clean_name}",
            "url": f"https://www.google.com/maps/search/?api=1&query={encoded}",
            "snippet": f"Bản đồ số định vị tọa độ và dẫn đường tham quan thực tế di tích {clean_name}.",
            "type": "maps"
        }

    def search_heritage(self, monument_hint: str, query: str) -> Dict[str, Any]:
        """
        Tìm kiếm trực tiếp toàn diện:
        Hợp nhất kết quả từ Wikipedia, bản đồ và cổng thông tin di sản.
        """
        # Xác định từ khóa tìm kiếm ưu tiên
        search_kw = monument_hint.strip() if monument_hint else query.strip()
        # Loại bỏ các từ thừa
        search_kw = re.sub(r'(Đây là|Ảnh này|Cho tôi biết|Hãy cho biết|Công trình|Di tích)', '', search_kw, flags=re.IGNORECASE).strip()
        if not search_kw:
            search_kw = "Di tích lịch sử Việt Nam"

        wiki_results = self.search_wikipedia(search_kw, limit=2)
        maps_item = self.generate_maps_link(search_kw)

        all_sources = []
        all_sources.append(maps_item)
        all_sources.extend(wiki_results)

        # Xây dựng văn bản tóm tắt làm ngữ cảnh cho KnowledgeAgent
        snippets_text = []
        for src in all_sources:
            if src.get("snippet"):
                snippets_text.append(f"• **{src['title']}** ({src['url']}):\n  {src['snippet']}")

        context_text = "\n\n".join(snippets_text) if snippets_text else "Không tìm thấy dữ liệu trực tuyến bổ sung."

        return {
            "keyword_used": search_kw,
            "sources": all_sources,
            "context_text": context_text
        }
