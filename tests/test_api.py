import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import make_url

from api.main import create_app
from api.models import Run
from api.settings import Settings
from api.worker import Worker
from tests.conftest import FakeLLM
from ui.api_client import RemoteManager


@pytest.fixture
def settings(tmp_path):
    url = f"sqlite:///{(tmp_path / 'api.sqlite').as_posix()}"
    engine, schema = None, None
    if pg_url := os.getenv("API_TEST_DATABASE_URL"):
        engine = create_engine(pg_url)
        schema = "api_test_" + uuid4().hex
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = (
            make_url(pg_url)
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
    yield Settings(
        database_url=url,
        data_dir=tmp_path / "media",
        model_mode="demo",
        embedded_worker=False,
        poll_seconds=0.01,
        heartbeat_seconds=0.1,
        lease_seconds=1,
    )
    if engine:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def identity(client, label="test"):
    response = client.post("/api/v1/sessions", json={"label": label})
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def upload(client, headers, photo):
    response = client.post(
        "/api/v1/assets", headers=headers, files={"file": ("photo.png", photo, "image/png")}
    )
    assert response.status_code == 201, response.text
    return response.json()["asset_id"]


def enqueue(client, headers, asset_id, **values):
    response = client.post(
        "/api/v1/runs",
        headers=headers,
        json={"asset_id": asset_id, "question": "Nhận diện công trình", **values},
    )
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def test_swagger_schema_security_and_config_do_not_expose_secrets(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    assert "/api/v1/runs/{run_id}/events/history" in schema["paths"]
    assert schema["paths"]["/api/v1/assets"]["post"]["requestBody"]["content"].get(
        "multipart/form-data"
    )
    assert client.get("/health/live").json() == {"status": "ok"}
    caps = client.get("/api/v1/capabilities").json()
    assert caps["model_mode"] == "demo" and caps["model_configured"]
    assert "api_key" not in json.dumps(caps).lower()
    assert client.get("/api/v1/runs").status_code == 401


def test_complete_graph_result_sources_feedback_and_bookmarks(client, photo):
    auth = identity(client)
    asset = upload(client, auth, photo)
    identifier = enqueue(client, auth, asset)
    assert client.get(f"/api/v1/runs/{identifier}/result", headers=auth).status_code == 409
    worker = Worker(client.app.state.runtime)
    assert worker.process_one()
    response = client.get(f"/api/v1/runs/{identifier}", headers=auth)
    assert response.json()["execution_status"] == "succeeded"
    result = client.get(f"/api/v1/runs/{identifier}/result", headers=auth).json()
    assert result["run_id"] == identifier and result["model_mode"] == "demo"
    assert "DEMO" in result["final_response"]
    assert result["intermediate"] is None
    assert "config_snapshot" not in result
    assert len(result["sources"]) == 1
    full = client.get(
        f"/api/v1/runs/{identifier}/result?include_intermediate=true", headers=auth
    ).json()
    assert full["intermediate"]["draft_response"]
    steps = client.get(f"/api/v1/runs/{identifier}/steps", headers=auth).json()["items"]
    assert "content" not in steps["aggregate"]["payload"]
    assert steps["visual"]["payload"]["content"]
    assert client.get(f"/api/v1/runs/{identifier}/sources", headers=auth).json()["items"]
    assert (
        client.get(f"/api/v1/runs/{identifier}/metrics", headers=auth).json()["usage"][
            "total_tokens"
        ]
        is None
    )
    assert (
        client.put(
            f"/api/v1/runs/{identifier}/bookmark", headers=auth, json={"saved": True}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/runs?saved_only=true", headers=auth).json()["total"] == 1
    feedback = {"rating": "helpful", "note": "Nguồn dễ quan sát"}
    assert (
        client.post(f"/api/v1/runs/{identifier}/feedback", headers=auth, json=feedback).json()
        == feedback
    )
    assert client.get(f"/api/v1/runs/{identifier}/feedback", headers=auth).json() == feedback
    assert (
        client.get(f"/api/v1/runs/{identifier}/export?format=markdown", headers=auth).status_code
        == 200
    )
    assert (
        "config_snapshot"
        not in client.get(f"/api/v1/runs/{identifier}/export", headers=auth).json()
    )
    assert client.delete(f"/api/v1/assets/{asset}", headers=auth).status_code == 409


def test_ownership_applies_to_every_resource(client, photo):
    alice, bob = identity(client, "alice"), identity(client, "bob")
    asset = upload(client, alice, photo)
    identifier = enqueue(client, alice, asset)
    for path in (
        f"assets/{asset}",
        f"assets/{asset}/content",
        f"runs/{identifier}",
        f"runs/{identifier}/events",
        f"runs/{identifier}/events/history",
        f"runs/{identifier}/result",
        f"runs/{identifier}/sources",
        f"runs/{identifier}/steps",
        f"runs/{identifier}/metrics",
        f"runs/{identifier}/feedback",
        f"runs/{identifier}/export",
    ):
        assert client.get("/api/v1/" + path, headers=bob).status_code == 404, path
    assert client.post(f"/api/v1/runs/{identifier}/cancel", headers=bob).status_code == 404
    assert client.delete(f"/api/v1/assets/{asset}", headers=bob).status_code == 404
    assert (
        client.post(
            "/api/v1/runs", headers=bob, json={"asset_id": asset, "question": "q"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/runs", headers=bob).json()["items"] == []


def test_idempotency_conflict_parallel_admission_and_queue_limit(client, photo):
    auth = identity(client)
    asset = upload(client, auth, photo)
    key = {**auth, "Idempotency-Key": "stable-key"}
    body = {"asset_id": asset, "question": "q"}
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/v1/runs", headers=key, json=body), range(2))
        )
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["run_id"] for r in responses}) == 1
    assert (
        client.post("/api/v1/runs", headers=key, json={**body, "question": "different"}).status_code
        == 409
    )
    for _ in range(2):
        enqueue(client, auth, asset)
    assert client.post("/api/v1/runs", headers=auth, json=body).status_code == 429


def test_invalid_upload_validation_size_and_unknown_asset(client, photo):
    auth = identity(client)
    assert (
        client.post(
            "/api/v1/assets", headers=auth, files={"file": ("a.png", b"invalid")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/runs", headers=auth, json={"asset_id": str(uuid4()), "question": "q"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/runs", headers=auth, json={"asset_id": str(uuid4()), "question": "  "}
        ).status_code
        == 422
    )
    response = client.post(
        "/api/v1/assets",
        headers={**auth, "Content-Length": "999999999", "Origin": "http://localhost:3000"},
        content=b"tiny",
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    data = photo + b"0" * 10_000_001
    assert (
        client.post("/api/v1/assets", headers=auth, files={"file": ("a.png", data)}).status_code
        == 413
    )


def test_events_replay_sse_cursor_and_hidden_draft(client, photo):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    Worker(client.app.state.runtime).process_one()
    base = f"/api/v1/runs/{identifier}"
    history = client.get(base + "/events/history", headers=auth).json()
    records = history["items"]
    assert [e["sequence"] for e in records] == list(range(1, len(records) + 1))
    assert records[-1]["event"] == "run.succeeded"
    assert history["terminal"]
    aggregate = [e for e in records if e["data"].get("node") == "aggregate"][-1]
    assert "content" not in aggregate["data"]["payload"]
    position = records[-3]["sequence"]
    response = client.get(base + "/events", headers={**auth, "Last-Event-ID": str(position)})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    ids = [int(line[4:]) for line in response.text.splitlines() if line.startswith("id: ")]
    assert ids == [e["sequence"] for e in records if e["sequence"] > position]
    full = client.get(base + "/events/history?include_draft=true", headers=auth).json()
    assert any(
        e["data"].get("payload", {}).get("content")
        for e in full["items"]
        if e["data"].get("node") == "aggregate"
    )


def test_queued_cancel_retry_requires_explicit_key_and_revoked_token(client, photo):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    base = f"/api/v1/runs/{identifier}"
    assert client.post(base + "/cancel", headers=auth).json()["execution_status"] == "cancelled"
    assert not Worker(client.app.state.runtime).process_one()
    assert client.post(base + "/retry", headers=auth).status_code == 422
    retried = client.post(base + "/retry", headers={**auth, "Idempotency-Key": "retry-key"})
    assert retried.status_code == 202
    assert retried.json()["parent_run_id"] == identifier
    assert client.delete("/api/v1/sessions/me", headers=auth).status_code == 204
    assert client.get("/api/v1/sessions/me", headers=auth).status_code == 401


def test_worker_atomic_claim_and_stale_lease_policy(client, photo):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    rt = client.app.state.runtime
    first, second = Worker(rt), Worker(rt)
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda w: w.claim(), (first, second)))
    assert sum(c is not None for c in claims) == 1
    with rt.db.session() as session:
        session.execute(
            update(Run).where(Run.id == identifier).values(lease_expires_at=time.time() - 1)
        )
    second.recover_stale()
    record = client.get(f"/api/v1/runs/{identifier}", headers=auth).json()
    assert record["execution_status"] == "failed" and record["error_type"] == "WorkerLost"
    assert not second.process_one()  # no automatic paid rerun


def test_storage_survives_api_restart(settings, photo):
    with TestClient(create_app(settings)) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        Worker(client.app.state.runtime).process_one()
    with TestClient(create_app(settings)) as restarted:
        response = restarted.get(f"/api/v1/runs/{identifier}/result", headers=auth)
        assert response.status_code == 200 and response.json()["run_id"] == identifier


def test_cooperative_running_cancellation(settings, photo, fake_search):
    entered, release = threading.Event(), threading.Event()

    def behavior(role, kwargs):
        if role == "coordinator":
            entered.set()
            assert release.wait(5)

    def manager(config):
        return FakeLLM(behavior, config)

    with TestClient(create_app(settings, manager_factory=manager)) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        worker = Worker(client.app.state.runtime)
        with ThreadPoolExecutor(1) as pool:
            work = pool.submit(worker.process_one)
            try:
                assert entered.wait(5)
                assert (
                    client.post(f"/api/v1/runs/{identifier}/cancel", headers=auth).json()[
                        "execution_status"
                    ]
                    == "cancel_requested"
                )
            finally:
                release.set()
            assert work.result(timeout=5)
        run = client.get(f"/api/v1/runs/{identifier}", headers=auth).json()
        assert run["execution_status"] == "cancelled"


def test_samples_asset_content_delete_cors_and_worker_readiness(client):
    auth = identity(client)
    samples = client.get("/api/v1/samples").json()["items"]
    assert samples
    response = client.post("/api/v1/samples/chua_mot_cot/assets", headers=auth)
    assert response.status_code == 201
    identifier = response.json()["asset_id"]
    assert (
        client.get(f"/api/v1/assets/{identifier}/content", headers=auth).headers["content-type"]
        == "image/png"
    )
    assert client.delete(f"/api/v1/assets/{identifier}", headers=auth).status_code == 204
    assert client.get("/health/ready").status_code == 503
    Worker(client.app.state.runtime).heartbeat()
    assert client.get("/health/ready").status_code == 200
    response = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_bootstrap_required_and_live_provider_preflight(settings, photo):
    locked = Settings(**{**settings.model_dump(), "bootstrap_token": "not-secret-for-test"})
    with TestClient(create_app(locked)) as client:
        assert client.post("/api/v1/sessions", json={}).status_code == 403
        assert (
            client.post(
                "/api/v1/sessions", headers={"X-Bootstrap-Token": "not-secret-for-test"}, json={}
            ).status_code
            == 201
        )
    live = settings.model_copy(update={"model_mode": "live"})
    with TestClient(create_app(live)) as client:
        auth = identity(client)
        asset = upload(client, auth, photo)
        response = client.post(
            "/api/v1/runs", headers=auth, json={"asset_id": asset, "question": "q"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_not_configured"


def test_remote_frontend_adapter_uses_http_contract(client, photo):
    def proxy(request):
        response = client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.read(),
        )
        if (
            request.method == "POST"
            and (request.url.path == "/api/v1/runs" or request.url.path.endswith("/review"))
            and response.status_code == 202
        ):
            Worker(client.app.state.runtime).process_one()
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    manager = RemoteManager("http://testserver", transport=httpx.MockTransport(proxy))
    events = list(manager.remote_stream(photo, "Question", "tourist"))
    result = events[-1].result
    assert result.status == "reviewed"
    assert result.expert_results["visual"]["text"]
    assert result.expert_results["knowledge"]["meta"]["live_search_sources"]
    assert result.judge_report["sources"]
    assert result.events
    assert manager.get_status()["description"].startswith("Backend API")
    reviewed = list(manager.remote_review_stream(photo, result.model_dump()))[-1].result
    assert reviewed.parent_run_id == result.run_id
    assert reviewed.run_kind == "review" and reviewed.status == "reviewed"
    assert len(reviewed.calls) == 1
    assert reviewed.calls[0]["agent_role"] == "judge"


def test_streamlit_http_frontend_runs_and_renders_sources(client, monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    def proxy(request):
        response = client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.read(),
        )
        if (
            request.method == "POST"
            and (request.url.path == "/api/v1/runs" or request.url.path.endswith("/review"))
            and response.status_code == 202
        ):
            Worker(client.app.state.runtime).process_one()
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    class TestRemote(RemoteManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, transport=httpx.MockTransport(proxy), **kwargs)

    monkeypatch.setenv("HERITAGE_API_URL", "http://testserver")
    monkeypatch.setattr("ui_app.RemoteManager", TestRemote)
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(root / "app.py", default_timeout=30).run()
    app.selectbox(key="sample").set_value(root / "samples/chua_mot_cot.jpg").run()
    app.text_area(key="query").input("Kiến trúc nhìn thấy trong ảnh?").run()
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state.result["status"] == "reviewed"
    assert app.session_state.result["judge_report"]["sources"]
    assert any("DEMO" in item.value for item in app.markdown)
    original_id = app.session_state.result["run_id"]
    app.button(key="review_again").click().run()
    assert not app.exception
    assert app.session_state.result["parent_run_id"] == original_id
    assert app.session_state.result["run_kind"] == "review"
    assert len(app.session_state.result["calls"]) == 1


def test_embedded_worker_processes_job_without_foreground_client(settings, photo):
    embedded = settings.model_copy(update={"embedded_worker": True})
    with TestClient(create_app(embedded)) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        until = time.monotonic() + 10
        while time.monotonic() < until:
            record = client.get(f"/api/v1/runs/{identifier}", headers=auth).json()
            if record["execution_status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        assert record["execution_status"] == "succeeded"
        assert client.get("/health/ready").status_code == 200


def test_chunked_body_limit_and_safe_errors(client, caplog):
    auth = identity(client)

    def chunks():
        yield b"x" * 6_000_000
        yield b"x" * 6_000_000

    response = client.post(
        "/api/v1/sessions", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    original = client.app.state.runtime.store.get_run

    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE_PROVIDER_DATA")

    client.app.state.runtime.store.get_run = broken
    response = client.get(f"/api/v1/runs/{uuid4()}", headers=auth)
    assert response.status_code == 500
    assert "PRIVATE_PROVIDER_DATA" not in response.text + caplog.text
    client.app.state.runtime.store.get_run = original


def test_session_expiry_and_post_completion_cancellation(client, photo):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    worker = Worker(client.app.state.runtime)
    worker.process_one()
    base = f"/api/v1/runs/{identifier}"
    assert client.post(base + "/cancel", headers=auth).json()["execution_status"] == "succeeded"
    from api.models import SessionToken

    with client.app.state.runtime.db.session() as session:
        record = session.get(
            SessionToken, client.get("/api/v1/sessions/me", headers=auth).json()["session_id"]
        )
        record.expires_at = time.time() - 1
    assert client.get(base, headers=auth).status_code == 401
