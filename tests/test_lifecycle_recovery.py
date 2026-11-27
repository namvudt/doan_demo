"""Actual worker recovery and deletion/retention contracts, without external models."""

import time

import pytest
from sqlalchemy import func, select

from api.lifecycle import purge_data
from api.models import Asset, ModelAttempt, Run, SessionToken
from api.recovery import NodeRecovery, checkpoint_nodes
from api.telemetry import persist_attempt
from api.worker import Worker
from tests.test_api import client as client
from tests.test_api import enqueue, identity, upload
from tests.test_api import settings as settings
from workflow.service import RunCancelled


def completed(client, photo, auth):
    asset = upload(client, auth, photo)
    identifier = enqueue(client, auth, asset)
    assert Worker(client.app.state.runtime).process_one()
    assert (
        client.get(f"/api/v1/runs/{identifier}", headers=auth).json()["execution_status"]
        == "succeeded"
    )
    return identifier, asset


@pytest.mark.parametrize(
    "profile,stop_node", [(None, "coordinate"), ("config/hanoi-evidence.yaml", "visual")]
)
def test_worker_recovers_completed_nodes_and_keeps_attempts(
    client, photo, monkeypatch, profile, stop_node
):
    if profile:
        monkeypatch.setenv("HERITAGE_CONFIG", profile)
    auth = identity(client)
    options = {"focus_box": [0.1, 0.1, 0.8, 0.8]} if profile else {}
    identifier = enqueue(client, auth, upload(client, auth, photo), **options)
    runtime = client.app.state.runtime
    first = Worker(runtime)
    run, _ = first.claim()
    service = runtime.service(run)
    stream = service.stream(
        photo,
        run.question,
        run.audience,
        run_id=run.id,
        focus_box=(run.input_context or {}).get("focus_box"),
    )
    try:
        for event in stream:
            if event.kind == "node" and event.node == stop_node and event.status == "completed":
                break
    finally:
        stream.close()
        service.llm.close()
    assert "coordinate" in checkpoint_nodes(runtime.db, identifier)
    with runtime.db.session() as session:
        run = session.get(Run, identifier)
        run.lease_expires_at = time.time() - 1
    second = Worker(runtime)
    assert second.process_one()
    body = client.get(f"/api/v1/runs/{identifier}", headers=auth).json()
    assert body["execution_status"] == "succeeded"
    result = client.get(
        f"/api/v1/runs/{identifier}/result?include_intermediate=true", headers=auth
    ).json()
    with runtime.db.session() as session:
        attempts = session.scalar(
            select(func.count())
            .select_from(ModelAttempt)
            .where(ModelAttempt.run_id == identifier, ModelAttempt.agent_role == "coordinator")
        )
        record = session.get(Run, identifier)
        assert record.recovery_count == 1
        assert record.result["node_metadata"]["coordinate"]["checkpoint_reused"]
        if profile:
            assert record.result["result_schema_version"] == 2
            assert record.result["evidence"]
            assert record.result["regions"]
            assert record.result["node_metadata"]["visual"]["checkpoint_reused"]
    assert attempts == 1
    assert result["final_response"]
    status = client.get(f"/api/v1/runs/{identifier}/recovery", headers=auth).json()
    assert status["recoveries"] == 1 and not status["can_resume"]


def test_checkpoint_invalidated_by_source_revision_and_lease(client, photo):
    auth = identity(client)
    enqueue(client, auth, upload(client, auth, photo))
    runtime = client.app.state.runtime
    run, token = Worker(runtime).claim()
    revision = ["one"]
    cache = NodeRecovery(runtime.db, run, revision_provider=lambda: revision[0])
    state = {"query": "q", "image_data": photo}
    signature = cache.signature("coordinate", state)

    class Calls:
        calls = []

    cache.save("coordinate", signature, {"plan": {"safe": True}}, None, Calls())
    cache.resuming = True
    assert cache.load("coordinate", cache.signature("coordinate", state), None)["plan"] == {
        "safe": True
    }
    revision[0] = "withdrawn"
    assert cache.load("coordinate", cache.signature("coordinate", state), None) is None
    assert run.worker_token == token


def test_owner_hide_is_immediate_and_purge_respects_grace_and_other_owner(client, photo):
    auth, other = identity(client), identity(client)
    identifier, asset_id = completed(client, photo, auth)
    other_id, other_asset = completed(client, photo, other)
    runtime = client.app.state.runtime
    assert client.delete(f"/api/v1/runs/{identifier}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/runs/{identifier}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/runs/{identifier}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/runs/{identifier}", headers=auth).status_code == 404
    assert client.get("/api/v1/runs", headers=auth).json()["total"] == 0
    assert purge_data(runtime)["runs"] == 0
    future = time.time() + 8 * 86400
    plan = purge_data(runtime, now=future)
    assert plan["dry_run"] and plan["runs"] == 1 and plan["assets"] == 1
    with runtime.db.session() as session:
        assert session.get(Run, identifier)
        storage_key = session.get(Asset, asset_id).storage_key
    result = purge_data(runtime, apply=True, now=future)
    assert result["runs"] == 1
    assert not runtime.asset_path(storage_key).exists()
    with runtime.db.session() as session:
        assert session.get(Run, identifier) is None
        assert session.get(Asset, asset_id) is None
        assert session.get(Run, other_id) and session.get(Asset, other_asset)


def test_active_run_requires_cancel_before_deletion(client, photo):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    assert client.delete(f"/api/v1/runs/{identifier}", headers=auth).status_code == 409
    assert client.post(f"/api/v1/runs/{identifier}/cancel", headers=auth).status_code == 200
    assert client.delete(f"/api/v1/runs/{identifier}", headers=auth).status_code == 204


def test_expired_guest_cleanup_keeps_account_owner(client):
    registered = client.post(
        "/api/v1/accounts",
        json={
            "email": "retention@example.test",
            "password": "retention-password-123",
            "display_name": "Retention",
        },
    )
    assert registered.status_code == 201
    from api.product_models import Account

    runtime = client.app.state.runtime
    with runtime.db.session() as session:
        account = session.scalar(select(Account))
        stable_id = account.owner_id
        owner = session.get(SessionToken, stable_id)
        owner.expires_at = owner.last_seen = time.time() - 100 * 86400
        owner.revoked = True
    purge_data(runtime, apply=True)
    with runtime.db.session() as session:
        assert session.get(SessionToken, stable_id) is not None


def test_parent_deletion_requires_leaf_first_without_breaking_an_admitted_child(client, photo):
    auth = identity(client)
    parent, _ = completed(client, photo, auth)
    child = client.post(
        f"/api/v1/runs/{parent}/retry",
        headers={**auth, "Idempotency-Key": "retention-child"},
    )
    assert child.status_code == 202
    child_id = child.json()["run_id"]
    blocked = client.delete(f"/api/v1/runs/{parent}", headers=auth)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "run_has_children"
    assert Worker(client.app.state.runtime).process_one()
    assert (
        client.get(f"/api/v1/runs/{child_id}", headers=auth).json()["execution_status"]
        == "succeeded"
    )
    assert client.delete(f"/api/v1/runs/{parent}", headers=auth).status_code == 409
    assert client.delete(f"/api/v1/runs/{child_id}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/runs/{parent}", headers=auth).status_code == 204


def test_model_admission_is_fenced_by_worker_lease_and_stale_completion_cannot_overwrite(
    client, photo
):
    auth = identity(client)
    identifier = enqueue(client, auth, upload(client, auth, photo))
    runtime = client.app.state.runtime
    run, first_token = Worker(runtime).claim()
    record = {
        "attempt": 1,
        "agent_role": "visual",
        "actual_provider": "mock",
        "model_used": "mock",
        "status": "running",
    }
    persist_attempt(runtime.db, identifier, record, expected_worker_token=first_token)
    with pytest.raises(RunCancelled, match="already admitted"):
        persist_attempt(runtime.db, identifier, record, expected_worker_token=first_token)
    with runtime.db.session() as session:
        active = session.get(Run, identifier)
        active.worker_token = "second-worker-token"
        existing = session.get(ModelAttempt, (identifier, 1))
        existing.status = "interrupted"
    for stale in (
        {**record, "attempt": 2},
        {**record, "status": "success", "usage": {"total_tokens": 99}},
    ):
        with pytest.raises(RunCancelled, match="lease"):
            persist_attempt(runtime.db, identifier, stale, expected_worker_token=first_token)
    with runtime.db.session() as session:
        assert session.get(ModelAttempt, (identifier, 1)).status == "interrupted"
        assert session.get(ModelAttempt, (identifier, 2)) is None
        active = session.get(Run, identifier)
        active.lease_expires_at = time.time() - 1
    with pytest.raises(RunCancelled, match="lease"):
        persist_attempt(
            runtime.db,
            identifier,
            {**record, "attempt": 2},
            expected_worker_token="second-worker-token",
        )
