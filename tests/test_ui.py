from pathlib import Path

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
