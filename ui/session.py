"""Bounded session-only history; no database or cross-user global cache."""

from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

HISTORY_LIMIT = 8
HISTORY_IMAGE_BYTES = 40_000_000


def remember_run(history, result, image_data):
    with Image.open(BytesIO(image_data)) as image:
        image.thumbnail((480, 360))
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=80)
    item = {
        "result": deepcopy(result),
        "thumbnail": buffer.getvalue(),
        "image_data": image_data,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    items = [item, *[old for old in history if old["result"]["run_id"] != result["run_id"]]][
        :HISTORY_LIMIT
    ]
    remaining = HISTORY_IMAGE_BYTES
    for index, entry in enumerate(items):
        data = entry.get("image_data") or b""
        if len(data) > remaining:
            items[index] = {**entry, "image_data": None}
        else:
            remaining -= len(data)
    return items


def clear_active(state):
    for key in ("result", "comparison", "live_events", "run_error"):
        state.pop(key, None)


def set_question(state, question):
    state["query"] = question
    state["mode"] = "Hỏi bằng ảnh"
    state["history_view"] = "current"
    clear_active(state)


def clear_history(state):
    state["history"] = []
    state["history_view"] = "current"
    state["saved_runs"] = {}
    state["feedback_store"] = {}
    for key in list(state):
        if key.startswith(("feedback_widget_", "note_widget_", "saved_widget_")):
            state.pop(key, None)


def save_bookmark(state, run_id):
    state.setdefault("saved_runs", {})[run_id] = state.get(f"saved_widget_{run_id}", False)


def save_feedback(state, run_id):
    state.setdefault("feedback_store", {})[run_id] = {
        "rating": state.get(f"feedback_widget_{run_id}", "Chưa đánh giá"),
        "note": state.get(f"note_widget_{run_id}", ""),
    }


def prune_session(state):
    kept = {item["result"]["run_id"] for item in state.get("history", [])}
    for name in ("saved_runs", "feedback_store"):
        state[name] = {key: value for key, value in state.get(name, {}).items() if key in kept}
