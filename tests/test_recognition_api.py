from fastapi.testclient import TestClient

from api.main import create_app
from api.worker import Worker
from tests.conftest import FakeLLM
from tests.test_api import client as client
from tests.test_api import identity, upload
from tests.test_api import settings as settings
from tests.test_recognition import recognition_response


def test_hint_recognition_sse_review_retry_and_idempotency(settings, photo, monkeypatch):
    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(recognition_response(), cfg))
    ) as test:
        auth = identity(test)
        body = {
            "asset_id": upload(test, auth, photo),
            "question": "Đây có thể là công trình nào?",
            "location_hint": {"name": "Chùa Hương", "provenance": "sample_label"},
        }
        headers = {**auth, "Idempotency-Key": "recognition"}
        created = test.post("/api/v1/runs", headers=headers, json=body)
        assert created.status_code == 202
        identifier = created.json()["run_id"]
        assert test.post("/api/v1/runs", headers=headers, json=body).json()["run_id"] == identifier
        assert (
            test.post(
                "/api/v1/runs", headers=headers, json={**body, "location_hint": {"name": "Wrong"}}
            ).status_code
            == 409
        )
        assert Worker(test.app.state.runtime).process_one()
        base = f"/api/v1/runs/{identifier}"
        result = test.get(base + "/result", headers=auth).json()
        evidence = test.get(base + "/evidence", headers=auth).json()
        assert (
            result["recognition"]["status"] == "probable" and result["answer_status"] == "answered"
        )
        assert evidence["recognition"] == result["recognition"]
        assert result["location_hint"] == body["location_hint"] == evidence["location_hint"]
        assert "recognition" in test.get(base + "/events", headers=auth).text
        assert test.get(base + "/evidence", headers=identity(test)).status_code == 404
        for action in ("review", "retry"):
            response = test.post(base + "/" + action, headers={**auth, "Idempotency-Key": action})
            assert response.status_code == 202, response.text
            assert Worker(test.app.state.runtime).process_one()
            child = test.get(
                f"/api/v1/runs/{response.json()['run_id']}/result", headers=auth
            ).json()
            assert child["recognition"]["status"] == "probable"
            assert child["location_hint"] == body["location_hint"]
        assert test.get(base + "/result", headers=auth).json() == result
        schema = test.get("/openapi.json").json()["components"]["schemas"]
        assert "location_hint" in schema["RunCreate"]["properties"]
        assert "recognition" in schema["ResultView"]["properties"]


def test_location_hint_disabled_profile_is_rejected_before_queue(client, photo):
    auth = identity(client)
    response = client.post(
        "/api/v1/runs",
        headers=auth,
        json={
            "asset_id": upload(client, auth, photo),
            "question": "Identify",
            "location_hint": {"name": "Test"},
        },
    )
    assert response.status_code == 422
    assert client.get("/api/v1/runs", headers=auth).json()["total"] == 0


def test_selected_candidate_is_structured_and_validated_for_pending_revision(
    settings, photo, monkeypatch
):
    from tests.test_accuracy_profile import ambiguous

    monkeypatch.setenv("HERITAGE_CONFIG", "config/hanoi-evidence.yaml")
    with TestClient(
        create_app(settings, manager_factory=lambda cfg: FakeLLM(ambiguous, cfg))
    ) as test:
        auth = identity(test)
        created = test.post(
            "/api/v1/runs",
            headers=auth,
            json={
                "asset_id": upload(test, auth, photo),
                "question": "Identify",
            },
        )
        base = "/api/v1/runs/" + created.json()["run_id"]
        assert Worker(test.app.state.runtime).process_one()
        pending = test.get(base + "/clarification", headers=auth).json()["clarification"]
        body = {
            "clarification_id": pending["clarification_id"],
            "revision": pending["revision"],
            "selected_candidate": "Wrong",
            "answer": "",
        }
        headers = {**auth, "Idempotency-Key": "selected"}
        assert test.post(base + "/clarification", headers=headers, json=body).status_code == 422
        response = test.post(
            base + "/clarification", headers=headers, json={**body, "selected_candidate": "DEMO"}
        )
        assert response.status_code == 202
        assert Worker(test.app.state.runtime).process_one()
        child = test.get(
            "/api/v1/runs/" + response.json()["run_id"] + "/result", headers=auth
        ).json()
        assert child["answer_status"] == "answered"
        assert (
            child["recognition"]["status"] == "unrecognized"
        )  # User selection is not image proof.
