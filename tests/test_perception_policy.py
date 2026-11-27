import json

import pytest
from PIL import Image

from core.config import load_config
from core.perception import asks_text_reading
from tests.conftest import FakeLLM
from tests.test_recognition import NoSources, recognition_response
from workflow.accuracy import AccuracyContext
from workflow.service import RunService


@pytest.mark.parametrize(
    "scene,legacy,expected",
    [("adequate", "unreadable", "probable"), ("unreadable", "adequate", "unrecognized")],
)
def test_scene_visibility_controls_identity_separately_from_text(photo, scene, legacy, expected):
    base = recognition_response(history=True)

    def response(role, kwargs):
        raw = base(role, kwargs)
        if getattr(kwargs.get("response_schema"), "__name__", "") == "VisualFindings":
            data = json.loads(raw)
            data.update(scene_visibility=scene, readability=legacy, text_readability="unreadable")
            return json.dumps(data)
        return raw

    manager = FakeLLM(response, load_config("config/evaluation/viettravel-adapted.yaml"))
    result = RunService(manager, search_engine_factory=NoSources).run(
        photo, "Đây có thể là công trình nào và có lịch sử gì?"
    )
    assert result.recognition.status == expected
    if scene == "adequate":
        assert result.clarification is None
        assert result.answer_status == "partial"  # Missing historical source stays missing.
    else:
        assert result.clarification["reason"] == "image_unreadable"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Có bao nhiêu cánh cửa?", False),
        ("Công trình có màu gì?", False),
        ("Đọc dòng chữ trên biển", True),
        ("Tên được viết bằng ngôn ngữ nào?", True),
        ("Có bao nhiêu chữ số 0?", True),
    ],
)
def test_ocr_intent_routes_only_relevant_questions(query, expected):
    assert asks_text_reading(query) is expected


def test_unused_planned_ocr_is_skipped(photo, monkeypatch):
    config = load_config("config/evaluation/viettravel-adapted.yaml")
    manager = FakeLLM(recognition_response(), config)
    context = AccuracyContext(manager, photo)
    monkeypatch.setattr(
        context.tools, "crop", lambda *_: pytest.fail("Counting does not need OCR crop")
    )
    context.visual(
        Image.new("RGB", (64, 64)),
        "Có bao nhiêu cửa?",
        [{"box": [0, 0, 1, 1], "purpose": "Đọc biển chữ"}],
    )
    assert not any(e["kind"] == "ocr" for e in context.evidence)


def test_legacy_profile_keeps_conservative_existing_behavior(photo):
    config = load_config("config/hanoi-evidence.yaml")
    assert not config.accuracy.perception.separate_readability
    result = RunService(
        FakeLLM(recognition_response(unreadable=True), config), search_engine_factory=NoSources
    ).run(photo, "Đây có thể là công trình nào?")
    assert result.recognition.status == "unrecognized"
