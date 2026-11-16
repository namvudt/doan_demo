from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from tests.conftest import FakeLLM

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def prepared_app(monkeypatch, fake=None):
    monkeypatch.setattr("ui_app.LLMManager", lambda: fake or FakeLLM())
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    sample = Path(__file__).resolve().parents[1] / "samples/chua_mot_cot.jpg"
    app.selectbox(key="sample").set_value(sample).run()
    app.text_area(key="query").input("Test question").run()
    return app


def test_ui_uses_graph_and_invalidates_old_result(monkeypatch, fake_search):
    app = prepared_app(monkeypatch)
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state.result["status"] == "reviewed"
    assert any(
        "Answer [1](https://vi.wikipedia.org/wiki/Test)" in markdown.value
        for markdown in app.markdown
    )
    app.text_area(key="query").input("Different question").run()
    assert "result" not in app.session_state
    assert not any("Answer [1]" in markdown.value for markdown in app.markdown)


def test_ui_hides_unreviewed_draft(monkeypatch, fake_search):
    fake = FakeLLM(lambda role, kwargs: "invalid" if role == "judge" else None)
    app = prepared_app(monkeypatch, fake)
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state.result["status"] == "unverified"
    assert app.warning
    assert not any("mock aggregator findings" in markdown.value for markdown in app.markdown)


def test_ui_can_recover_judge_without_rerunning_experts(monkeypatch, fake_search):
    failing = {"judge": True}
    fake = FakeLLM(lambda role, kwargs: "invalid" if role == "judge" and failing["judge"] else None)
    app = prepared_app(monkeypatch, fake)
    app.button(key="start").click().run()
    original = app.session_state.result
    assert original["judge_report"]["error_code"] == "review_schema_invalid"
    before = len(fake.history)
    failing["judge"] = False
    app.button(key="review_again").click().run()
    assert not app.exception
    assert app.session_state.result["status"] == "reviewed"
    assert app.session_state.result["parent_run_id"] == original["run_id"]
    assert len(fake.history) == before + 1
    assert fake.history[-1]["agent_role"] == "judge"
    assert any(item["result"] == original for item in app.session_state.history)
    # Historical review must use the original image even after input changes.
    app.text_area(key="query").input("Another question").run()
    app.selectbox(key="history_view").set_value(original["run_id"]).run()
    app.button(key="review_again").click().run()
    assert not app.exception
    assert app.session_state.result["query"] == original["query"]
    assert len(fake.history) == before + 2


def test_ui_comparison_has_no_accuracy_scores(monkeypatch, fake_search):
    app = prepared_app(monkeypatch)
    app.radio(key="mode").set_value("So sánh thử nghiệm").run()
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state.comparison["verdict"] is None
    assert app.warning


def test_ui_boots_without_key():
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    assert not app.exception
    assert app.button(key="start").disabled


def test_real_manager_boots_current_evidence_schema_without_calling_models(monkeypatch):
    monkeypatch.setenv("HERITAGE_CONFIG", str(APP_PATH.parent / "config/hanoi-evidence.yaml"))
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    assert not app.exception and not app.error
    assert app.text_area(key="query") and app.selectbox(key="sample")
    app.selectbox(key="sample").set_value(APP_PATH.parent / "samples/chua_huong.jpg").run()
    assert not app.exception and not app.error
    assert not app.checkbox(key="guided_sample").value


def test_config_error_shows_fields_without_exposing_values_or_unknown_keys(monkeypatch, caplog):
    from core.config import AppConfig
    from core.runtime_logging import JsonFormatter

    private_value, private_field = "PRIVATE_CONFIG_VALUE", "PRIVATE_CONFIG_FIELD"
    with pytest.raises(ValidationError) as failure:
        AppConfig.model_validate(
            {
                "budget": {"max_llm_calls": private_value},
                "accuracy": {"recognition": {"min_observations": 0}},
                private_field: private_value,
            }
        )

    def invalid_manager():
        raise failure.value

    monkeypatch.setattr("ui_app.LLMManager", invalid_manager)
    monkeypatch.setattr("ui_app.configure_local_logging", lambda: None)
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    assert not app.exception
    assert app.error and "ValidationError" in app.error[0].value
    rendered = "\n".join(element.value for element in [*app.error, *app.markdown, *app.info])
    assert "budget.max_llm_calls" in rendered
    assert "accuracy.recognition.min_observations" in rendered
    assert "khởi động lại" in rendered
    records = [
        record
        for record in caplog.records
        if getattr(record, "operational_event", None) == "ui.configuration_invalid"
    ]
    assert {record.operational_fields["config_field"] for record in records} == {
        "budget.max_llm_calls",
        "accuracy.recognition.min_observations",
        "unknown_field",
    }
    logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert all(private not in rendered + logs for private in (private_value, private_field))


def test_evidence_ui_continues_clarification_and_shows_claims(monkeypatch, fake_search):
    from api.demo import DemoSearch
    from tests.test_accuracy_profile import ambiguous, config

    monkeypatch.setattr(
        "core.search.HeritageSearchEngine.search_heritage", DemoSearch().search_heritage
    )

    app = prepared_app(monkeypatch, FakeLLM(ambiguous, config()))
    app.button(key="start").click().run()
    assert not app.exception
    parent = app.session_state.result
    assert parent["answer_status"] == "needs_clarification"
    assert app.button(key="review_again").disabled
    app.selectbox(key="candidate_" + parent["run_id"]).set_value("DEMO")
    button = next(b for b in app.button if b.label == "Tiếp tục với thông tin bổ sung")
    button.click().run()
    assert not app.exception
    child = app.session_state.result
    assert child["answer_status"] == "answered" and child["parent_run_id"] == parent["run_id"]
    assert (
        child["claims"]
        and app.session_state.answered_clarifications[parent["run_id"]] == child["run_id"]
    )


def test_evidence_ui_sends_selected_root_region(monkeypatch, fake_search):
    from tests.test_accuracy_profile import config

    app = prepared_app(monkeypatch, FakeLLM(config=config()))
    app.checkbox(key="focus_enabled").check().run()
    app.slider(key="focus_x").set_value((10, 60)).run()
    app.button(key="start").click().run()
    assert not app.exception
    result = app.session_state.result
    assert any(r["box"] == [0.1, 0, 0.6, 1] for r in result["regions"])


def test_local_ui_initializes_json_log_once_and_keeps_run_ids(monkeypatch, fake_search, tmp_path):
    import json
    import logging

    monkeypatch.setenv("API_LOG_DIR", str(tmp_path / "logs"))
    app = prepared_app(monkeypatch)
    app.button(key="start").click().run()
    assert not app.exception
    run_id = app.session_state.result["run_id"]
    paths = list((tmp_path / "logs").glob("streamlit-*.jsonl"))
    assert len(paths) == 1
    records = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()]
    assert any(r["event"] == "run.completed" and r["run_id"] == run_id for r in records)
    assert sum(r["event"] == "process.logging_ready" for r in records) == 1
    assert "Test question" not in paths[0].read_text(encoding="utf-8")
    owned = [h for h in logging.getLogger().handlers if getattr(h, "heritage_handler", False)]
    assert len(owned) == 2


def test_preferences_and_source_filter_do_not_call_models(monkeypatch, fake_search):
    fake = FakeLLM()
    app = prepared_app(monkeypatch, fake)
    app.button(key="start").click().run()
    run_id = app.session_state.result["run_id"]
    call_count = len(fake.history)
    app.toggle(key="show_draft").set_value(True).run()
    assert any("mock aggregator findings" in m.value for m in app.markdown)
    app.text_input(key=f"source_filter_{run_id}").input("no matching source").run()
    assert len(fake.history) == call_count
    assert app.session_state.result["run_id"] == run_id
    assert not app.exception


def test_history_bookmarks_and_feedback_survive_changing_questions(monkeypatch, fake_search):
    fake = FakeLLM()
    app = prepared_app(monkeypatch, fake)
    app.button(key="start").click().run()
    run_id = app.session_state.result["run_id"]
    app.checkbox(key=f"saved_widget_{run_id}").set_value(True).run()
    app.text_area(key=f"note_widget_{run_id}").input("Check this source later").run()
    before = len(fake.history)
    app.text_area(key="query").input("Another question").run()
    app.selectbox(key="history_view").set_value(run_id).run()
    assert not app.exception
    assert len(fake.history) == before
    assert app.checkbox(key=f"saved_widget_{run_id}").value
    assert app.text_area(key=f"note_widget_{run_id}").value == "Check this source later"
    app.button(key="clear_history").click().run()
    assert app.session_state.history == []


def test_prompt_and_rotation_invalidate_current_result_without_model_call(monkeypatch, fake_search):
    fake = FakeLLM()
    app = prepared_app(monkeypatch, fake)
    app.button(key="start").click().run()
    count = len(fake.history)
    app.button(key="rotate").click().run()
    assert "result" not in app.session_state
    assert len(app.session_state.history) == 1
    app.button(key="prompt_1").click().run()
    assert "kiến trúc" in app.text_area(key="query").value
    assert len(fake.history) == count
