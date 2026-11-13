"""Bounded application content for LangSmith; credentials/binary state never leave."""

import hashlib
import math
import os
import re
from io import BytesIO

from PIL import Image

# Explicit projection also handles native LangGraph input/output dictionaries.
CONTENT_KEYS = {
    "query",
    "question",
    "prompt",
    "system_instruction",
    "response",
    "final_response",
    "draft_response",
    "content",
    "text",
    "summary",
    "image",
    "image_data",
    "image_info",
    "sha256",
    "size_bytes",
    "width",
    "height",
    "media_type",
    "audience",
    "plan",
    "query_intent",
    "identified_monument",
    "task_categories",
    "selected_agents",
    "focus_directives",
    "visual_focus",
    "knowledge_focus",
    "generation_focus",
    "expert_results",
    "visual",
    "knowledge",
    "generation",
    "judge_report",
    "criteria_evaluation",
    "visual_fidelity",
    "relevance",
    "cultural_tone",
    "passed",
    "score",
    "critique",
    "overall_status",
    "verification_status",
    "hallucination_detected",
    "hallucination_notes",
    "refinement_summary",
    "cited_source_ids",
    "sources",
    "source_id",
    "title",
    "url",
    "type",
    "snippet",
    "retrieved_at",
    "revision_id",
    "errors",
    "node",
    "status",
    "error_type",
    "error_code",
    "duration",
    "call_count",
    "error_count",
    "source_count",
    "usage_metadata",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "finish_reason",
    "block_reason",
    "response_has_text",
    "max_output_tokens",
    "provider_status_code",
    "output_truncated",
}
_CREDENTIAL_KEY = re.compile(
    r"(?:api.?key|authorization|password|secret|access.?token|bootstrap.?token|operations.?token)",
    re.I,
)


def image_info(value):
    if isinstance(value, Image.Image):
        return {
            "width": value.width,
            "height": value.height,
            "media_type": "image/" + (value.format or "png").lower(),
        }
    if not isinstance(value, bytes):
        return {}
    result = {"size_bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    try:
        with Image.open(BytesIO(value)) as image:
            result.update(
                width=image.width,
                height=image.height,
                media_type=Image.MIME.get(image.format, "image/unknown"),
            )
    except Exception:
        result["media_type"] = "application/octet-stream"
    return result


def credential_values():
    return sorted(
        {
            secret
            for name, secret in os.environ.items()
            if _CREDENTIAL_KEY.search(name) and len(secret) >= 8
        },
        key=len,
        reverse=True,
    )


def redact_text(value, limit=12000, secrets=None):
    # Redact before truncating, so a token straddling the limit cannot leak a prefix.
    for secret in credential_values() if secrets is None else secrets:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)\bBearer\s+[a-z0-9_.~+/=-]+", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?i)([?&](?:key|api_key|token|access_token)=)[^&\s\"']+", r"\1[REDACTED]", value
    )
    value = re.sub(r"(?:AIza[\w-]{20,}|lsv2_[\w-]{16,}|sk-[\w-]{16,})", "[REDACTED]", value)
    value = re.sub(
        r"(?i)((?:api_key|access_token|password|secret)\s*[:=]\s*[\"']?)[^\s\"'&,]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", value)
    return value if len(value) <= limit else value[:limit] + "\n[TRUNCATED]"


def sanitize_content(value):
    # A per-payload budget bounds native graph snapshots as well as individual strings.
    remaining = [60000]
    secrets = credential_values()

    def visit(item, depth=0):
        if depth > 10 or remaining[0] <= 0:
            return "[TRUNCATED]"
        if isinstance(item, bytes) or isinstance(item, Image.Image):
            return image_info(item)
        if isinstance(item, str):
            result = redact_text(item, min(12000, remaining[0]), secrets)
            remaining[0] -= len(result)
            return result
        if isinstance(item, dict):
            return {
                key: visit(child, depth + 1)
                for key, child in list(item.items())[:100]
                if key in CONTENT_KEYS and not _CREDENTIAL_KEY.search(key)
            }
        if isinstance(item, (list, tuple)):
            return [visit(child, depth + 1) for child in item[:40]]
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return None  # Never serialize clients, configuration objects or file paths.

    projected = visit(value)
    return projected if isinstance(projected, dict) else {}
