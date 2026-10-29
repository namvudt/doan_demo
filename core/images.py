"""Image validation and stable input identities."""

import hashlib
import json
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from core.config import AppConfig


def validate_image(data: bytes, config: AppConfig) -> bytes:
    if not data or len(data) > config.max_image_bytes:
        raise ValueError("Ảnh trống hoặc vượt giới hạn dung lượng.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Chỉ hỗ trợ JPEG, PNG và WebP.")
            if image.width * image.height > config.max_image_pixels:
                raise ValueError("Ảnh vượt giới hạn số pixel.")
            image.load()
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.info.clear()
            output = BytesIO()
            normalized.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Không đọc được dữ liệu ảnh.") from exc


def image_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def fingerprint(data: bytes, query: str, audience: str, config_hash: str) -> str:
    payload = [hashlib.sha256(data).hexdigest(), query.strip(), audience, config_hash]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
