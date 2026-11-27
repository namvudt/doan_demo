"""Legacy Streamlit HTTP bridge contracts for the combined frontend/backend checkout."""

import httpx
from fastapi.testclient import TestClient

from api.main import create_app
from api.worker import Worker
from tests.conftest import FakeLLM
from tests.test_accuracy_profile import ambiguous
from tests.test_api import settings as settings
from tests.test_recognition import recognition_response
from ui.api_client import RemoteManager


def test_remote_adapter_preserves_evidence_and_continues_pending_run(settings, photo, monkeypatch):
    import httpx

    from ui.api_client import RemoteManager

    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as client:

        def proxy(request):
            response = client.request(
                request.method,
                request.url.raw_path.decode(),
                headers=dict(request.headers),
                content=request.read(),
            )
            if request.method == "POST" and response.status_code == 202:
                Worker(client.app.state.runtime).process_one()
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=response.content,
                request=request,
            )

        manager = RemoteManager("http://testserver", transport=httpx.MockTransport(proxy))
        parent = list(manager.remote_stream(photo, "Question", "tourist"))[-1].result
        assert parent.answer_status == "needs_clarification" and parent.evidence
        child = list(manager.remote_continue_stream(photo, parent.model_dump(), "DEMO"))[-1].result
        assert child.answer_status == "answered" and child.parent_run_id == parent.run_id
        assert child.claims and child.evidence and len(child.calls) == 4


def test_remote_adapter_preserves_recognition_and_hint(settings, photo, monkeypatch):
    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(recognition_response(), cfg))
    ) as test:

        def proxy(request):
            response = test.request(
                request.method,
                request.url.raw_path.decode(),
                headers=dict(request.headers),
                content=request.read(),
            )
            if request.method == "POST" and response.status_code == 202:
                Worker(test.app.state.runtime).process_one()
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=response.content,
                request=request,
            )

        manager = RemoteManager("http://testserver", transport=httpx.MockTransport(proxy))
        result = list(
            manager.remote_stream(
                photo,
                "Identify",
                "tourist",
                location_hint={"name": "Chùa Hương", "provenance": "user"},
            )
        )[-1].result
        assert result.recognition.status == "probable" and result.location_hint.name == "Chùa Hương"
        reviewed = list(manager.remote_review_stream(photo, result.model_dump()))[-1].result
        assert reviewed.recognition.status == "probable"
        assert reviewed.location_hint == result.location_hint
