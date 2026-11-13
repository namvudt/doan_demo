import json

import pytest
from PIL import Image
from pydantic import ValidationError

from agents import CoordinatorAgent, JudgeAgent
from core.config import AppConfig, load_config
from core.gateway import safe_extract_json
from core.images import validate_image
from core.schemas import ExecutionPlan
from tests.conftest import FakeLLM, valid_review


@pytest.mark.parametrize("raw", ["null", "[]", "3", '"text"', "", "invalid"])
def test_json_must_be_object(raw):
    with pytest.raises(ValueError):
        safe_extract_json(raw)


def test_markdown_json_object():
    assert safe_extract_json('```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize(
    "plan",
    [
        {"selected_agents": ["alien"]},
        {"selected_agents": ["visual_agent"], "focus_directives": None},
    ],
)
def test_plan_invalid_shapes(plan):
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(plan)


def test_agents_deduplicated_and_visual_required():
    plan = ExecutionPlan(selected_agents=["knowledge_agent", "knowledge_agent"])
    assert plan.selected_agents == ["visual_agent", "knowledge_agent"]


def test_coordinator_null_is_controlled_error():
    with pytest.raises(ValueError):
        CoordinatorAgent(FakeLLM(lambda *args: "null")).plan(Image.new("RGB", (10, 10)), "q")


@pytest.mark.parametrize(
    "raw", ["invalid", "null", '{"final_response": "answer"}', '{"sources": ["bad"]}']
)
def test_review_never_fabricates_approval(raw, source):
    report, _ = JudgeAgent(FakeLLM(lambda *args: raw)).evaluate_and_refine(
        "q", "draft", "visual", [source], image=Image.new("RGB", (10, 10))
    )
    assert report["overall_status"] == "UNVERIFIED"
    assert report["criteria_evaluation"] == {}
    assert report["final_response"] is None
    assert report["hallucination_detected"] is None


def test_judge_sees_real_image_and_snippet(source):
    llm = FakeLLM()
    report, _ = JudgeAgent(llm).evaluate_and_refine(
        "q", "draft", "visual", [source], image=Image.new("RGB", (10, 10)), require_sources=True
    )
    assert source["snippet"] in llm.history[0]["prompt"]
    assert llm.history[0]["image"] is not None
    assert report["verification_status"] == "reviewed"
    assert report["sources"][0]["source_id"] == "wiki_a"


def test_unknown_citation_is_not_approved(source):
    review = valid_review()
    review["cited_source_ids"] = ["invented"]
    report, _ = JudgeAgent(FakeLLM(lambda *args: json.dumps(review))).evaluate_and_refine(
        "q", "draft", "visual", [source], image=Image.new("RGB", (10, 10))
    )
    assert report["overall_status"] == "UNVERIFIED"


def test_unknown_inline_citation_is_not_approved(source):
    review = valid_review()
    review["final_response"] += " Claim [wiki_invented]"
    report, _ = JudgeAgent(FakeLLM(lambda *args: json.dumps(review))).evaluate_and_refine(
        "q", "draft", "visual", [source], image=Image.new("RGB", (10, 10))
    )
    assert report["verification_status"] == "unverified"


def test_missing_image_or_source_does_not_call_model(source):
    llm = FakeLLM()
    report, _ = JudgeAgent(llm).evaluate_and_refine("q", "draft", "visual", [source])
    assert report["verification_status"] == "unverified"
    assert not llm.calls


def test_image_validation(photo):
    assert validate_image(photo, AppConfig())
    with pytest.raises(ValueError):
        validate_image(b"not image", AppConfig())
    with pytest.raises(ValueError):
        validate_image(photo, AppConfig(max_image_pixels=10))
    with pytest.raises(ValueError):
        validate_image(photo, AppConfig(max_image_bytes=10))


def test_config_default_and_explicit_role_override(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "openai")
    config = load_config()
    assert config.roles["visual"].provider == "gemini"
    assert config.roles["knowledge"].provider == "openai"
    assert config.providers["gemini"].model == "gemini-3.8-flash"
