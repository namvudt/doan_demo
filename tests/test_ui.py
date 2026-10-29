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
    assert any("Answer [wiki_a]" in markdown.value for markdown in app.markdown)
    app.text_area(key="query").input("Different question").run()
    assert "result" not in app.session_state
    assert not any("Answer [wiki_a]" in markdown.value for markdown in app.markdown)


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
