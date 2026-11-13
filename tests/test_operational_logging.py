import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text, update

from api.database import Database
from api.main import create_app
from api.models import ModelAttempt, Run
from api.runtime import Runtime
from api.settings import ROOT, Settings
from api.telemetry import ProcessMetrics, RequestEnvelopeMiddleware, persist_attempt
from api.worker import Worker
from core.config import AppConfig, BudgetConfig
from core.gateway import LLMManager
from core.runtime_logging import (
    JsonFormatter,
    RateLimitedLog,
    configure_logging,
    context_fields,
    log_context,
    log_event,
)
from tests.test_api import enqueue, identity, upload


@pytest.fixture
def api_settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}",
        data_dir=tmp_path / "media",
        embedded_worker=False,
        model_mode="demo",
        operations_token="operations-test-" + "x" * 40,
    )


def structured(caplog):
    return [r for r in caplog.records if hasattr(r, "operational_event")]


def test_formatter_drops_messages_secrets_and_traceback_values(caplog):
    private = "PRIVATE_DO_NOT_LOG"
    try:
        raise RuntimeError(private)
    except RuntimeError as exc:
        log_event(
            "test.error",
            error=exc,
            prompt=private,
            api_key=private,
            request_id=private,
            duration_ms=float("inf"),
        )
    record = structured(caplog)[-1]
    result = JsonFormatter().format(record)
    assert private not in result
    payload = json.loads(result)
    assert payload["error_type"] == "RuntimeError"
    assert (
        payload["frames"][-1]["function"]
        == "test_formatter_drops_messages_secrets_and_traceback_values"
    )
    assert "duration_ms" not in payload
    external = logging.LogRecord("third.party", logging.ERROR, __file__, 1, private, (), None)
    assert private not in JsonFormatter().format(external)


def test_concurrent_contexts_do_not_leak(caplog):
    def run(_):
        value = str(uuid4())
        with log_context(run_id=value):
            log_event("test.context")
            assert context_fields()["run_id"] == value
        assert "run_id" not in context_fields()
        return value

    with ThreadPoolExecutor(max_workers=4) as pool:
        expected = set(pool.map(run, range(12)))
    actual = {
        r.operational_fields["run_id"]
        for r in structured(caplog)
        if r.operational_event == "test.context"
    }
    assert actual == expected


def test_api_run_worker_stage_sse_correlation_and_metrics(api_settings, photo, caplog):
    with TestClient(create_app(api_settings)) as client:
        auth = identity(client)
        asset = upload(client, auth, photo)
        response = client.post(
            "/api/v1/runs", headers=auth, json={"asset_id": asset, "question": "PRIVATE_QUESTION"}
        )
        assert response.status_code == 202
        run = response.json()
        identifier = run["run_id"]
        assert run["request_id"] == response.headers["x-request-id"]
        assert run["trace_id"] == identifier
        worker = Worker(client.app.state.runtime)
        worker.heartbeat()
        assert worker.process_one()
        base = f"/api/v1/runs/{identifier}"
        metrics = client.get(base + "/metrics", headers=auth).json()
        assert len(metrics["calls"]) == 5
        assert all(c["status"] == "success" for c in metrics["calls"])
        assert metrics["usage"]["total_tokens"] is None
        response = client.get(base + "/events", headers={**auth, "Last-Event-ID": "19"})
        assert response.text.count("\nid: ") + response.text.startswith("id: ") == 2
        ops = "/api/v1/operations/metrics"
        assert client.get("/openapi.json").json()["paths"][ops]["get"]["security"] == [
            {"OperationsBearer": []}
        ]
        assert client.get(ops).status_code == 401
        assert client.get(ops, headers=auth).status_code == 401
        output = client.get(
            ops,
            headers={"Authorization": "Bearer " + api_settings.operations_token.get_secret_value()},
        )
        assert output.status_code == 200
        assert 'heritage_runs{status="succeeded"} 1' in output.text
        assert 'heritage_model_attempts{status="success"} 5' in output.text
        assert "heritage_sse_active 0" in output.text
        assert "heritage_sse_events_total 2" in output.text
        assert "heritage_model_attempts_unknown_usage 5" in output.text
        client.get("/PRIVATE_PATH?token=PRIVATE_QUERY", headers=auth)
        records = structured(caplog)
        for event in ("run.running", "run.succeeded", "stage.completed", "model.success"):
            selected = [r.operational_fields for r in records if r.operational_event == event]
            assert selected
            assert all(
                p["request_id"] == run["request_id"]
                and p["run_id"] == identifier
                and p["trace_id"] == identifier
                and p["worker_id"] == worker.id
                for p in selected
            )
        closed = [r.operational_fields for r in records if r.operational_event == "sse.closed"][-1]
        assert closed["events_sent"] == 2 and closed["reason"] == "terminal"
        serialized = "\n".join(JsonFormatter().format(r) for r in caplog.records)
        for value in (
            "PRIVATE_QUESTION",
            "PRIVATE_PATH",
            "PRIVATE_QUERY",
            auth["Authorization"],
            api_settings.operations_token.get_secret_value(),
            "Báo cáo visual",
            "Dữ liệu mô phỏng",
        ):
            assert value not in serialized
        assert identifier not in output.text  # No per-user/per-run labels.


def test_sse_disconnect_records_completion_and_releases_gauge(api_settings, photo, caplog):
    """Exercise the real StreamingResponse over ASGI, cancel after the first data frame."""
    app = create_app(api_settings)
    with TestClient(app) as client:
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))

        async def disconnect():
            connected = asyncio.Event()
            disconnected = asyncio.Event()
            messages = []

            async def receive():
                if not connected.is_set():
                    connected.set()
                    return {"type": "http.request", "body": b"", "more_body": False}
                await disconnected.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                messages.append(message)
                if b"data:" in message.get("body", b""):
                    disconnected.set()

            path = f"/api/v1/runs/{identifier}/events"
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [(b"authorization", auth["Authorization"].encode())],
                "server": ("testserver", 80),
                "client": ("127.0.0.1", 1),
            }
            await asyncio.wait_for(app(scope, receive, send), timeout=3)
            assert any(b"run.queued" in message.get("body", b"") for message in messages)

        asyncio.run(disconnect())
        assert app.state.process_metrics.sse_active == 0
        closed = [
            r.operational_fields for r in structured(caplog) if r.operational_event == "sse.closed"
        ]
        assert closed[-1]["reason"] == "disconnected"
        assert (
            client.get(f"/api/v1/runs/{identifier}", headers=auth).json()["execution_status"]
            == "queued"
        )


def test_operations_disabled_by_default(api_settings):
    settings = Settings(**{**api_settings.model_dump(), "operations_token": ""})
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/operations/metrics").status_code == 503


def test_durable_attempts_before_call_retry_and_lease_loss(api_settings, photo, monkeypatch):
    with TestClient(create_app(api_settings)) as client:
        rt = client.app.state.runtime
        auth = identity(client)
        identifier = enqueue(client, auth, upload(client, auth, photo))
        worker = Worker(rt)
        run, token = worker.claim()
        manager = LLMManager(
            config=AppConfig(budget=BudgetConfig(transient_retries=1)), credentials={}
        )
        manager.attempt_observer = lambda r: persist_attempt(rt.db, identifier, r)
        monkeypatch.setattr(manager, "_client", lambda *args: object())
        calls = 0

        def provider(*args):
            nonlocal calls
            calls += 1
            with rt.db.session() as session:
                row = session.get(ModelAttempt, (identifier, calls))
                assert row.status == "running" and row.finished_at is None
            if calls == 1:
                raise TimeoutError("PRIVATE_ERROR")
            return (
                "PRIVATE_ANSWER",
                {"prompt_token_count": 3, "candidates_token_count": 2, "total_token_count": 5},
                "STOP",
            )

        monkeypatch.setattr(manager, "_provider_call", provider)
        manager.call_llm("PRIVATE_PROMPT", agent_role="visual")
        data = client.get(f"/api/v1/runs/{identifier}/metrics", headers=auth).json()
        assert [c["status"] for c in data["calls"]] == ["error", "success"]
        assert data["usage"]["total_tokens"] == 5
        assert data["usage"]["partial"] is True
        persist_attempt(
            rt.db, identifier, {"attempt": 3, "status": "running", "agent_role": "visual"}
        )
        with rt.db.session() as session:
            session.execute(
                update(Run).where(Run.id == identifier).values(lease_expires_at=time.time() - 10)
            )
        worker.recover_stale()
        with rt.db.session() as session:
            assert session.get(ModelAttempt, (identifier, 3)).status == "interrupted"
            assert session.get(Run, identifier).error_type == "WorkerLost"


def test_telemetry_finish_failure_never_repeats_paid_request(monkeypatch):
    manager = LLMManager(credentials={})
    monkeypatch.setattr(manager, "_client", lambda *args: object())
    attempts, notifications = [], []
    monkeypatch.setattr(
        manager, "_provider_call", lambda *args: (attempts.append(1) or "answer", None, "STOP")
    )

    def observer(record):
        notifications.append(record["status"])
        if record["status"] != "running":
            raise RuntimeError("PRIVATE_DB_PASSWORD")

    manager.attempt_observer = observer
    answer, _ = manager.call_llm("prompt", agent_role="visual")
    assert answer == "answer" and len(attempts) == 1
    assert notifications == ["running", "success"]
    manager.attempt_observer = lambda _: (_ for _ in ()).throw(RuntimeError("PRIVATE_DB"))
    with pytest.raises(RuntimeError):
        manager.call_llm("prompt", agent_role="visual")
    assert len(attempts) == 1  # Failed start is before the SDK request.


def test_queued_cancellation_and_failure_have_safe_logs(api_settings, photo, caplog):
    with TestClient(create_app(api_settings)) as client:
        auth = identity(client)
        asset = upload(client, auth, photo)
        identifier = enqueue(client, auth, asset)
        assert client.post(f"/api/v1/runs/{identifier}/cancel", headers=auth).status_code == 200
        failed = enqueue(client, auth, asset)
        worker = Worker(client.app.state.runtime)
        run, token = worker.claim()
        assert run.id == failed
        try:
            raise ValueError("PRIVATE_FAILURE")
        except ValueError as exc:
            with log_context(run_id=failed, worker_id=worker.id):
                worker.finish_error(failed, token, exc)
        assert (
            client.get(f"/api/v1/runs/{failed}", headers=auth).json()["execution_status"]
            == "failed"
        )
        events = [r.operational_event for r in structured(caplog)]
        assert "run.cancel" in events and "run.failed" in events
        assert "PRIVATE_FAILURE" not in caplog.text


def test_migration_preserves_old_records(api_settings):
    db = Database(api_settings.database_url.get_secret_value())
    config = Config(str(ROOT / "alembic.ini"))
    with db.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_api_storage")
        connection.execute(
            text(
                "INSERT INTO api_sessions (id,token_hash,label,created_at,expires_at,last_seen,revoked) VALUES ('old', 'hash', 'keep', 0, 100, 0, false)"
            )
        )
    assert "request_id" not in {c["name"] for c in inspect(db.engine).get_columns("api_runs")}
    rt = Runtime(api_settings)
    rt.migrate()
    with rt.db.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT label FROM api_sessions WHERE id='old'")).scalar()
            == "keep"
        )
    assert "api_model_attempts" in inspect(rt.db.engine).get_table_names()
    with rt.db.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
    rt.db.close()
    db.close()


def test_file_rotation_and_reconfiguration(api_settings, tmp_path):
    settings = Settings(
        **{
            **api_settings.model_dump(),
            "log_dir": tmp_path / "logs",
            "log_max_bytes": 1024,
            "log_backups": 2,
        }
    )
    try:
        configure_logging(settings)
        for _ in range(50):
            log_event("test.rotation", status="success")
        paths = list(settings.log_dir.glob("*.jsonl*"))
        assert 2 <= len(paths) <= 3
        for path in paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                assert json.loads(line)["event"].startswith(("test.", "process."))
        configure_logging(settings)
        owned = [h for h in logging.getLogger().handlers if getattr(h, "heritage_handler", False)]
        assert len(owned) == 2
    finally:
        configure_logging(api_settings)


def test_outage_warnings_are_rate_limited(caplog):
    limiter = RateLimitedLog(interval=100)
    for _ in range(100):
        limiter.emit("test.outage")
    assert sum(r.operational_event == "test.outage" for r in structured(caplog)) == 1


def test_late_stream_exception_preserves_status_and_safe_log(api_settings, caplog):
    from types import SimpleNamespace

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise ValueError("PRIVATE_STREAM_FAILURE")

    state = SimpleNamespace(settings=api_settings, process_metrics=ProcessMetrics())
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "state": {},
        "app": SimpleNamespace(state=state),
    }
    messages = []

    async def send(message):
        messages.append(message)

    with pytest.raises(ValueError):
        asyncio.run(RequestEnvelopeMiddleware(app)(scope, None, send))
    assert len(messages) == 1  # Never send a second HTTP status after stream starts.
    assert "PRIVATE_STREAM_FAILURE" not in caplog.text
    assert "http.error" in [r.operational_event for r in structured(caplog)]
