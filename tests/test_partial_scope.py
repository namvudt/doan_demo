import pytest

from api.demo import DemoSearch
from core.config import load_config
from core.question_scope import question_scope
from tests.conftest import FakeLLM
from workflow.service import RunService


@pytest.mark.parametrize(
    "question", ["Hãy đọc chữ Hán trên hoành phi", "Dịch chữ Hán và Nôm", "Hãy sáng tác bài thơ"]
)
def test_pure_unsupported_questions_do_not_call_models(question, photo):
    manager = FakeLLM(config=load_config("config/hanoi-evidence.yaml"))
    result = RunService(manager).run(photo, question)
    assert result.status == "out_of_scope"
    assert not manager.history


def test_mixed_question_keeps_supported_answer_and_explicit_limitation(photo):
    question = "Mô tả kiến trúc nhìn thấy và đọc chữ Hán trên hoành phi."
    manager = FakeLLM(config=load_config("config/hanoi-evidence.yaml"))
    result = RunService(manager, search_engine_factory=DemoSearch).run(photo, question)
    assert result.query == question
    assert result.status == "reviewed"
    assert result.answer_status == "partial"
    assert "Phần chưa hỗ trợ" in result.final_response
    assert "Hán–Nôm" in result.final_response
    assert result.claims
    coordinator = next(item for item in manager.history if item["agent_role"] == "coordinator")
    assert question not in coordinator["prompt"]
    assert "Mô tả kiến trúc nhìn thấy" in coordinator["prompt"]


def test_support_is_not_invented_from_remaining_generic_words():
    assert question_scope("Đọc Hán–Nôm và cho biết thêm").out_of_scope
    mixed = question_scope("Đọc chữ Hán và mô tả kiến trúc")
    assert not mixed.out_of_scope and mixed.supported_question == "mô tả kiến trúc"
    allowed = question_scope("Hãy sáng tác bài thơ", allow_generation=True)
    assert not allowed.out_of_scope and not allowed.limitations
