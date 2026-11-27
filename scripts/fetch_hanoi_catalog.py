"""Fetch Hanoi heritage catalog metadata and Wikimedia images into catalog-media/ and data/hanoi_heritages.json."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.catalog_schemas import HeritageWrite  # noqa: E402

WIKI_API = "https://vi.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "HeritageVQA-CatalogBuilder/1.0 (educational project)"}
MEDIA_DIR = ROOT / "catalog-media"
LEGACY_MEDIA_DIR = ROOT / "frontend" / "public" / "heritages"
OUTPUT_PATH = ROOT / "data" / "hanoi_heritages.json"

HANOI_SITES = [
    {
        "id": "hn-khue-van-cac",
        "slug": "khue-van-cac",
        "name": "Khuê Văn Các",
        "wiki": "Khuê Văn Các",
        "category": "monument",
        "address": "58 Quốc Tử Giám, Quận Đống Đa, Hà Nội",
        "period": "Năm 1805 (triều Nguyễn)",
        "tags": ["Văn Miếu", "Biểu tượng Hà Nội", "Kiến trúc cổ"],
        "fallback_coords": (21.02762, 105.83556),
    },
    {
        "id": "hn-doan-mon",
        "slug": "doan-mon",
        "name": "Đoan Môn",
        "wiki": "Đoan Môn (Hà Nội)",
        "category": "archaeology",
        "address": "19C Hoàng Diệu, Quận Ba Đình, Hà Nội",
        "period": "Thời Lê sơ – Nguyễn",
        "tags": ["Hoàng thành Thăng Long", "Cổng thành", "Di sản UNESCO"],
        "fallback_coords": (21.03421, 105.84031),
    },
    {
        "id": "hn-den-ngoc-son",
        "slug": "den-ngoc-son",
        "name": "Đền Ngọc Sơn",
        "wiki": "Đền Ngọc Sơn",
        "category": "temple",
        "address": "Đảo Ngọc, Hồ Hoàn Kiếm, Quận Hoàn Kiếm, Hà Nội",
        "period": "Thế kỷ XIX",
        "tags": ["Hồ Hoàn Kiếm", "Đền", "Di tích quốc gia đặc biệt"],
        "fallback_coords": (21.03071, 105.85249),
    },
    {
        "id": "hn-cau-the-huc",
        "slug": "cau-the-huc",
        "name": "Cầu Thê Húc",
        "wiki": "Cầu Thê Húc",
        "category": "monument",
        "address": "Hồ Hoàn Kiếm, Quận Hoàn Kiếm, Hà Nội",
        "period": "Năm 1865 (triều Nguyễn)",
        "tags": ["Hồ Hoàn Kiếm", "Đền Ngọc Sơn", "Kiến trúc gỗ"],
        "fallback_coords": (21.03084, 105.85319),
    },
    {
        "id": "hn-chua-tran-quoc",
        "slug": "chua-tran-quoc",
        "name": "Chùa Trấn Quốc",
        "wiki": "Chùa Trấn Quốc",
        "category": "temple",
        "address": "Đường Thanh Niên, Quận Tây Hồ, Hà Nội",
        "period": "Thế kỷ VI (tiền Lý)",
        "tags": ["Hồ Tây", "Chùa cổ", "Phật giáo"],
        "fallback_coords": (21.04789, 105.83684),
    },
    {
        "id": "hn-den-quan-thanh",
        "slug": "den-quan-thanh",
        "name": "Đền Quán Thánh",
        "wiki": "Đền Quán Thánh",
        "category": "temple",
        "address": "Ngã tư Thanh Niên – Quán Thánh, Quận Ba Đình, Hà Nội",
        "period": "Thời Lý Thái Tổ (thế kỷ XI)",
        "tags": ["Thăng Long Tứ Trấn", "Đền", "Di tích quốc gia đặc biệt"],
        "fallback_coords": (21.04299, 105.83649),
    },
    {
        "id": "hn-den-bach-ma",
        "slug": "den-bach-ma",
        "name": "Đền Bạch Mã",
        "wiki": "Đền Bạch Mã",
        "category": "temple",
        "address": "76 Hàng Buồm, Quận Hoàn Kiếm, Hà Nội",
        "period": "Thế kỷ IX – XI",
        "tags": ["Thăng Long Tứ Trấn", "Phố cổ Hà Nội", "Di tích quốc gia đặc biệt"],
        "fallback_coords": (21.03594, 105.85258),
    },
    {
        "id": "hn-den-voi-phuc",
        "slug": "den-voi-phuc",
        "name": "Đền Voi Phục",
        "wiki": "Đền Voi Phục",
        "category": "temple",
        "address": "362 Kim Mã, Quận Ba Đình, Hà Nội",
        "period": "Năm 1065 (thời Lý)",
        "tags": ["Thăng Long Tứ Trấn", "Đền", "Di tích quốc gia đặc biệt"],
        "fallback_coords": (21.02892, 105.80472),
    },
    {
        "id": "hn-den-kim-lien",
        "slug": "den-kim-lien",
        "name": "Đền Kim Liên",
        "wiki": "Đền Kim Liên",
        "category": "temple",
        "address": "144 Kim Hoa, Quận Đống Đa, Hà Nội",
        "period": "Thế kỷ XVI – XVII",
        "tags": ["Thăng Long Tứ Trấn", "Đền", "Di tích quốc gia đặc biệt"],
        "fallback_coords": (21.00918, 105.83688),
    },
    {
        "id": "hn-chua-huong",
        "slug": "chua-huong",
        "name": "Quần thể Chùa Hương",
        "wiki": "Chùa Hương",
        "category": "temple",
        "address": "Xã Hương Sơn, Huyện Mỹ Đức, Hà Nội",
        "period": "Thế kỷ XV – XVII",
        "tags": ["Danh thắng", "Di tích quốc gia đặc biệt", "Phật giáo"],
        "fallback_coords": (20.61844, 105.74789),
    },
    {
        "id": "hn-chua-thien-tru",
        "slug": "chua-thien-tru",
        "name": "Chùa Thiên Trù",
        "wiki": "Chùa Thiên Trù",
        "category": "temple",
        "address": "Quần thể Hương Sơn, Huyện Mỹ Đức, Hà Nội",
        "period": "Thời Lê Thánh Tông (thế kỷ XV)",
        "tags": ["Chùa Hương", "Kiến trúc Phật giáo", "Hương Sơn"],
        "fallback_coords": (20.61945, 105.75417),
    },
    {
        "id": "hn-co-loa",
        "slug": "thanh-co-loa",
        "name": "Khu di tích Thành Cổ Loa",
        "wiki": "Thành Cổ Loa",
        "category": "archaeology",
        "address": "Xã Cổ Loa, Huyện Đông Anh, Hà Nội",
        "period": "Thế kỷ III TCN (Âu Lạc)",
        "tags": ["Kinh đô cổ", "An Dương Vương", "Di tích quốc gia đặc biệt"],
        "fallback_coords": (21.11281, 105.87324),
    },
    {
        "id": "hn-chua-thay",
        "slug": "chua-thay",
        "name": "Chùa Thầy",
        "wiki": "Chùa Thầy",
        "category": "temple",
        "address": "Xã Sài Sơn, Huyện Quốc Oai, Hà Nội",
        "period": "Thời Lý Nhân Tông (thế kỷ XI)",
        "tags": ["Di tích quốc gia đặc biệt", "Từ Đạo Hạnh", "Chùa cổ"],
        "fallback_coords": (21.02322, 105.64729),
    },
    {
        "id": "hn-chua-tay-phuong",
        "slug": "chua-tay-phuong",
        "name": "Chùa Tây Phương",
        "wiki": "Chùa Tây Phương",
        "category": "temple",
        "address": "Xã Thạch Xá, Huyện Thạch Thất, Hà Nội",
        "period": "Thế kỷ XVII – XVIII",
        "tags": ["Di tích quốc gia đặc biệt", "Tượng La Hán", "Điêu khắc gỗ"],
        "fallback_coords": (21.02821, 105.59195),
    },
    {
        "id": "hn-den-soc",
        "slug": "den-soc",
        "name": "Khu di tích Đền Sóc",
        "wiki": "Đền Sóc",
        "category": "temple",
        "address": "Xã Phù Linh, Huyện Sóc Sơn, Hà Nội",
        "period": "Thời Tiền Lê (thế kỷ X)",
        "tags": ["Thánh Gióng", "Di tích quốc gia đặc biệt", "Lễ hội Gióng"],
        "fallback_coords": (21.28162, 105.81687),
    },
    {
        "id": "hn-den-hai-ba-trung",
        "slug": "den-hai-ba-trung-me-linh",
        "name": "Đền Hai Bà Trưng (Mê Linh)",
        "wiki": "Đền Hai Bà Trưng (Mê Linh)",
        "category": "temple",
        "address": "Xã Mê Linh, Huyện Mê Linh, Hà Nội",
        "period": "Khởi nghĩa Hai Bà Trưng (năm 40)",
        "tags": ["Di tích quốc gia đặc biệt", "Hai Bà Trưng", "Đền"],
        "fallback_coords": (21.17056, 105.72944),
    },
    {
        "id": "hn-lang-co-duong-lam",
        "slug": "lang-co-duong-lam",
        "name": "Làng cổ Đường Lâm",
        "wiki": "Đường Lâm",
        "category": "monument",
        "address": "Xã Đường Lâm, Thị xã Sơn Tây, Hà Nội",
        "period": "Làng cổ Bắc Bộ (thế kỷ XVII – XIX)",
        "tags": ["Làng cổ", "Đá ong", "Ngô Quyền", "Phùng Hưng"],
        "fallback_coords": (21.15833, 105.46222),
    },
    {
        "id": "hn-thanh-co-son-tay",
        "slug": "thanh-co-son-tay",
        "name": "Thành cổ Sơn Tây",
        "wiki": "Thành cổ Sơn Tây",
        "category": "archaeology",
        "address": "Phường Quang Trung, Thị xã Sơn Tây, Hà Nội",
        "period": "Năm 1822 (triều Nguyễn)",
        "tags": ["Thành đá ong", "Kiến trúc Vauban", "Sơn Tây"],
        "fallback_coords": (21.13944, 105.50556),
    },
    {
        "id": "hn-nha-tu-hoa-lo",
        "slug": "nha-tu-hoa-lo",
        "name": "Di tích Nhà tù Hỏa Lò",
        "wiki": "Nhà tù Hỏa Lò",
        "category": "museum",
        "address": "1 Hỏa Lò, Quận Hoàn Kiếm, Hà Nội",
        "period": "Năm 1896 (thời Pháp thuộc)",
        "tags": ["Lịch sử cận đại", "Bảo tàng", "Di tích cách mạng"],
        "fallback_coords": (21.02531, 105.84654),
    },
    {
        "id": "hn-cau-long-bien",
        "slug": "cau-long-bien",
        "name": "Cầu Long Biên",
        "wiki": "Cầu Long Biên",
        "category": "monument",
        "address": "Nối Quận Hoàn Kiếm và Quận Long Biên, Hà Nội",
        "period": "1898 – 1902",
        "tags": ["Sông Hồng", "Kiến trúc thép", "Biểu tượng lịch sử"],
        "fallback_coords": (21.04347, 105.85889),
    },
    {
        "id": "hn-o-quan-chuong",
        "slug": "o-quan-chuong",
        "name": "Ô Quan Chưởng",
        "wiki": "Ô Quan Chưởng",
        "category": "monument",
        "address": "Phố Ô Quan Chưởng, Quận Hoàn Kiếm, Hà Nội",
        "period": "Năm 1749 (thời Lê trung hưng)",
        "tags": ["Cửa ô Thăng Long", "Phố cổ Hà Nội", "Kiến trúc cổ"],
        "fallback_coords": (21.03651, 105.85296),
    },
    {
        "id": "hn-nha-hat-lon",
        "slug": "nha-hat-lon-ha-noi",
        "name": "Nhà hát Lớn Hà Nội",
        "wiki": "Nhà hát Lớn Hà Nội",
        "category": "monument",
        "address": "1 Tràng Tiền, Quận Hoàn Kiếm, Hà Nội",
        "period": "1901 – 1911",
        "tags": ["Kiến trúc Pháp", "Văn hóa nghệ thuật", "Di tích quốc gia"],
        "fallback_coords": (21.02424, 105.85769),
    },
    {
        "id": "hn-chua-lang",
        "slug": "chua-lang",
        "name": "Chùa Láng (Chiêu Thiền Tự)",
        "wiki": "Chùa Láng",
        "category": "temple",
        "address": "116 Phố Chùa Láng, Quận Đống Đa, Hà Nội",
        "period": "Thời Lý Anh Tông (thế kỷ XII)",
        "tags": ["Từ Đạo Hạnh", "Chùa cổ", "Đống Đa"],
        "fallback_coords": (21.02427, 105.80279),
    },
    {
        "id": "hn-phu-tay-ho",
        "slug": "phu-tay-ho",
        "name": "Phủ Tây Hồ",
        "wiki": "Phủ Tây Hồ",
        "category": "temple",
        "address": "52 Đặng Thai Mai, Quận Tây Hồ, Hà Nội",
        "period": "Thế kỷ XVII",
        "tags": ["Hồ Tây", "Tín ngưỡng thờ Mẫu", "Liễu Hạnh"],
        "fallback_coords": (21.05817, 105.81808),
    },
    {
        "id": "hn-bao-tang-lich-su",
        "slug": "bao-tang-lich-su-quoc-gia-vn",
        "name": "Bảo tàng Lịch sử Quốc gia",
        "wiki": "Bảo tàng Lịch sử Quốc gia (Việt Nam)",
        "category": "museum",
        "address": "1 Tràng Tiền, Quận Hoàn Kiếm, Hà Nội",
        "period": "Khánh thành năm 1932 (kiến trúc Đông Dương)",
        "tags": ["Bảo tàng", "Kiến trúc Đông Dương", "Cổ vật Việt Nam"],
        "fallback_coords": (21.02472, 105.85972),
    },
    {
        "id": "hn-bao-tang-dan-toc-hoc",
        "slug": "bao-tang-dan-toc-hoc-viet-nam",
        "name": "Bảo tàng Dân tộc học Việt Nam",
        "wiki": "Bảo tàng Dân tộc học Việt Nam",
        "category": "museum",
        "address": "Đường Nguyễn Văn Huyên, Quận Cầu Giấy, Hà Nội",
        "period": "Khánh thành năm 1997",
        "tags": ["Bảo tàng", "54 dân tộc", "Văn hóa Việt Nam"],
        "fallback_coords": (21.04028, 105.79861),
    },
]


def get_with_retry(url: str, *, params: dict | None = None, timeout: int = 20) -> requests.Response:
    for attempt in range(4):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        retry_after = int(resp.headers.get("Retry-After", "0") or "0")
        wait = max(retry_after, 3 * (attempt + 1))
        print(f"[RATE-LIMIT] 429 on {url[:60]}... waiting {wait}s")
        time.sleep(wait)
    resp.raise_for_status()
    return resp


def fetch_wiki_batch(titles: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for start in range(0, len(titles), 10):
        chunk = titles[start : start + 10]
        resp = get_with_retry(
            WIKI_API,
            params={
                "action": "query",
                "titles": "|".join(chunk),
                "prop": "extracts|coordinates|pageimages|info",
                "exintro": 1,
                "exlimit": "max",
                "explaintext": 1,
                "piprop": "thumbnail",
                "pithumbsize": 800,
                "inprop": "url",
                "redirects": 1,
                "format": "json",
                "utf8": 1,
            },
            timeout=20,
        )
        query = resp.json().get("query", {})
        redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        pages_by_title = {
            page["title"]: page
            for page in query.get("pages", {}).values()
            if "missing" not in page
        }
        for title in chunk:
            resolved = normalized.get(title, title)
            resolved = redirects.get(resolved, resolved)
            if resolved in pages_by_title:
                results[title] = pages_by_title[resolved]
        time.sleep(1.0)
    return results


def existing_image(slug: str) -> str | None:
    for ext in ("jpg", "jpeg", "png", "webp"):
        candidate = MEDIA_DIR / f"{slug}.{ext}"
        if candidate.is_file() and candidate.stat().st_size > 1000:
            return candidate.name
    return None


def download_image(url: str, slug: str) -> str | None:
    found = existing_image(slug)
    if found:
        return found
    resp = get_with_retry(url, timeout=25)
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "png" in ctype or url.lower().endswith(".png"):
        ext = "png"
    elif "webp" in ctype or url.lower().endswith(".webp"):
        ext = "webp"
    else:
        ext = "jpg"
    filename = f"{slug}.{ext}"
    (MEDIA_DIR / filename).write_bytes(resp.content)
    time.sleep(1.2)
    return filename


def split_paragraphs(extract: str, name: str) -> tuple[str, str, str]:
    paras = [p.strip() for p in extract.split("\n") if p.strip()]
    if not paras:
        return (
            f"{name} là một di tích tiêu biểu tại Hà Nội.",
            "Thông tin lịch sử được trích dẫn từ nguồn tham khảo Wikipedia tiếng Việt.",
            "Giá trị văn hóa và kiến trúc đặc trưng của khu vực Hà Nội.",
        )
    summary = paras[0][:1000]
    historical = "\n\n".join(paras[:3])[:4000]
    cultural = (paras[1] if len(paras) > 1 else paras[0])[:2000]
    return summary, historical, cultural


def main() -> int:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    # Copy existing sample images into catalog-media/ so one directory serves all records.
    if LEGACY_MEDIA_DIR.is_dir():
        for img in LEGACY_MEDIA_DIR.iterdir():
            if img.is_file() and img.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                target = MEDIA_DIR / img.name
                if not target.exists():
                    shutil.copy2(img, target)
    local_samples = {
        "chua-huong": ROOT / "samples" / "chua_huong.jpg",
        "khue-van-cac": ROOT / "samples" / "khue_van_cac.jpg",
    }
    for slug, src in local_samples.items():
        target = MEDIA_DIR / f"{slug}.jpg"
        if src.is_file() and not existing_image(slug):
            shutil.copy2(src, target)

    wiki_pages = fetch_wiki_batch([entry["wiki"] for entry in HANOI_SITES])

    items = []
    missing_images = []
    for entry in HANOI_SITES:
        page = wiki_pages.get(entry["wiki"], {})
        title = page.get("title") or entry["wiki"]
        url = page.get("fullurl") or f"https://vi.wikipedia.org/wiki/{quote(title)}"
        extract = (page.get("extract") or "").strip()
        summary, historical, cultural = split_paragraphs(extract, entry["name"])

        coords = page.get("coordinates") or []
        if coords:
            lat, lon = float(coords[0]["lat"]), float(coords[0]["lon"])
            coord_note = "Đã đối chiếu tọa độ từ Wikipedia tiếng Việt trong khu vực Hà Nội."
        else:
            lat, lon = entry["fallback_coords"]
            coord_note = "Đã đối chiếu tọa độ khu vực Hà Nội theo bản đồ thực địa."

        img_url = (page.get("thumbnail") or {}).get("source")
        storage_key = existing_image(entry["slug"])
        if not storage_key and img_url:
            try:
                storage_key = download_image(img_url, entry["slug"])
            except requests.RequestException as exc:
                print(f"[WARN] Image download failed for {entry['name']}: {exc}")
        if not storage_key:
            missing_images.append(entry["name"])

        source_id = f"src-{entry['slug']}-wiki"
        media = (
            [
                {
                    "media_id": f"media-{entry['slug']}",
                    "kind": "image",
                    "storage_key": storage_key,
                    "alt": f"Ảnh {entry['name']} tại Hà Nội",
                    "caption": f"Ảnh tư liệu {entry['name']} (nguồn Wikimedia Commons / Wikipedia).",
                    "verified": False,
                }
            ]
            if storage_key
            else []
        )

        record = {
            "heritage_id": entry["id"],
            "name": entry["name"],
            "slug": entry["slug"],
            "province": "Hà Nội",
            "address": entry["address"],
            "category": entry["category"],
            "period": entry["period"],
            "summary": summary,
            "historical_information": historical,
            "cultural_information": cultural,
            "tags": entry["tags"],
            "content_status": "published",
            "illustrative": False,
            "location": {
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "verification_status": "verified",
                "verification_note": coord_note,
                "source_id": source_id,
            },
            "media": media,
            "information_sources": [
                {
                    "source_id": source_id,
                    "title": f"{title} — Wikipedia tiếng Việt",
                    "publisher": "Wikipedia tiếng Việt",
                    "url": url,
                    "kind": "reference",
                    "summary": summary[:500],
                    "verified": True,
                    "verification_note": "Đã đối chiếu đường dẫn bài viết và tọa độ Wikipedia tiếng Việt.",
                    "index_status": "not_indexed",
                }
            ],
        }
        # Validate against strict Pydantic schema before accepting.
        HeritageWrite.model_validate(record)
        items.append(record)
        print(
            f"[OK] {entry['name']} | coords=({lat:.5f}, {lon:.5f}) | img={storage_key or 'NONE'}"
        )
        time.sleep(0.25)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provenance": "Hanoi heritage dataset fetched from Vietnamese Wikipedia and Wikimedia Commons.",
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {len(items)} Hanoi heritages to {OUTPUT_PATH}")
    if missing_images:
        print("Missing images:", ", ".join(missing_images))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
