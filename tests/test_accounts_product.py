"""Account identity, independent devices and owned conversation resources."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, update

from api.accounts import AccountStore, require_role
from api.catalog_schemas import HeritageWrite
from api.catalog_store import CatalogStore
from api.content_schemas import EntityBindingWrite
from api.content_store import ContentStore
from api.main import create_app
from api.models import Run, SessionToken
from api.product_models import Account, AccountSession, ConversationMessage, ProductAudit
from api.schemas import RunCreate
from api.store import StoreError
from api.worker import Worker
from tests.test_api import enqueue, identity, upload
from tests.test_api import settings as settings
from tests.test_catalog import record as catalog_record

OPERATIONS_TOKEN = "product-test-operations-" + "x" * 40
OPERATIONS = {"Authorization": "Bearer " + OPERATIONS_TOKEN}
PASSWORD = "Correct-test-password-012345"


@pytest.fixture
def product_client(settings):
    configured = settings.model_copy(update={"operations_token": SecretStr(OPERATIONS_TOKEN)})
    with TestClient(create_app(configured)) as client:
        yield client


def account(client, email="owner@example.test"):
    body = {"email": email, "display_name": "Người kiểm thử", "password": PASSWORD}
    created = client.post("/api/v1/accounts", json=body)
    assert created.status_code == 201, created.text
    signed = client.post("/api/v1/auth/sessions", json={"email": email, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    return created.json(), signed.json()


def auth(session):
    return {"Authorization": "Bearer " + session["access_token"]}


def conversation(client, headers, memory=False):
    response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Kiến trúc cần đối chiếu", "memory_enabled": memory},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_forbids_roles_and_keeps_passwords_and_tokens_hashed(product_client, photo):
    client = product_client
    rejected = client.post(
        "/api/v1/accounts",
        json={
            "email": "bad@example.test",
            "display_name": "No escalation",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert rejected.status_code == 422
    profile, first = account(client, "OWNER@example.test")
    assert profile["role"] == "user" and profile["email"] == "owner@example.test"
    assert "password_hash" not in profile
    assert "access_token" not in profile
    second = client.post(
        "/api/v1/auth/sessions", json={"email": "owner@example.test", "password": PASSWORD}
    ).json()
    first_owner = client.get("/api/v1/sessions/me", headers=auth(first)).json()["session_id"]
    assert (
        client.get("/api/v1/sessions/me", headers=auth(second)).json()["session_id"] == first_owner
    )
    asset = upload(client, auth(first), photo)
    assert client.get(f"/api/v1/assets/{asset}", headers=auth(second)).status_code == 200
    assert client.get(f"/api/v1/assets/{asset}", headers=identity(client)).status_code == 404
    with client.app.state.runtime.db.session() as session:
        stored = session.get(Account, profile["account_id"])
        assert stored.password_hash.startswith("scrypt$") and PASSWORD not in stored.password_hash
        tokens = list(session.scalars(select(AccountSession)))
        assert all(len(row.token_hash) == 64 and len(row.refresh_hash) == 64 for row in tokens)
        assert all(row.token_hash != first["access_token"] for row in tokens)
        assert session.scalar(select(func.count()).select_from(ProductAudit)) == 1


def test_refresh_is_single_use_and_logout_leaves_other_device_and_owner_active(product_client):
    client = product_client
    _, initial = account(client)
    second = client.post(
        "/api/v1/auth/sessions", json={"email": "owner@example.test", "password": PASSWORD}
    ).json()
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": initial["refresh_token"]})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    rotated = response.json()
    assert client.get("/api/v1/users/me", headers=auth(initial)).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": initial["refresh_token"]}
        ).status_code
        == 401
    )
    assert client.delete("/api/v1/sessions/me", headers=auth(rotated)).status_code == 204
    assert client.get("/api/v1/users/me", headers=auth(rotated)).status_code == 401
    assert client.get("/api/v1/users/me", headers=auth(second)).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        ).status_code
        == 401
    )
    owner = client.get("/api/v1/sessions/me", headers=auth(second)).json()["session_id"]
    with client.app.state.runtime.db.session() as session:
        assert not session.get(SessionToken, owner).revoked


def test_concurrent_refresh_has_only_one_successful_rotation(product_client):
    client = product_client
    _, session = account(client)

    def rotate(_):
        return client.post(
            "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(rotate, range(2)))
    assert sorted(statuses) == [200, 401]


def test_roles_are_server_authorized_current_and_versioned(product_client):
    client = product_client
    profile, signed = account(client)
    path = f"/api/v1/operations/accounts/{profile['account_id']}/role"
    body = {"role": "editor", "version": profile["version"]}
    assert client.put(path, headers=auth(signed), json=body).status_code == 403
    rt = client.app.state.runtime
    principal = rt.store.authenticate(signed["access_token"])
    with pytest.raises(StoreError) as error:
        require_role(rt, principal)
    assert error.value.status == 403
    promoted = client.put(path, headers=OPERATIONS, json=body)
    assert promoted.status_code == 200
    assert require_role(rt, principal).role == "editor"  # no stale cached role authorization
    assert client.put(path, headers=OPERATIONS, json=body).status_code == 409
    disabled = client.put(
        path, headers=OPERATIONS, json={"role": "editor", "version": 2, "disabled": True}
    )
    assert disabled.status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(signed)).status_code == 401
    with rt.db.session() as session:
        assert session.get(SessionToken, principal.id).revoked


def test_profile_conflict_password_change_and_guest_account_boundaries(product_client):
    client = product_client
    profile, signed = account(client)
    guest = identity(client)
    assert client.get("/api/v1/users/me", headers=guest).status_code == 403
    assert client.delete("/api/v1/auth/sessions/current", headers=guest).status_code == 403
    patch = {"display_name": "Tên mới", "version": profile["version"]}
    assert client.patch("/api/v1/users/me", headers=auth(signed), json=patch).status_code == 200
    assert client.patch("/api/v1/users/me", headers=auth(signed), json=patch).status_code == 409
    assert (
        client.post(
            "/api/v1/users/me/password",
            headers=auth(signed),
            json={"current_password": PASSWORD, "new_password": "New-correct-password-01234"},
        ).status_code
        == 204
    )
    assert client.get("/api/v1/users/me", headers=auth(signed)).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/sessions", json={"email": profile["email"], "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/sessions",
            json={"email": profile["email"], "password": "New-correct-password-01234"},
        ).status_code
        == 200
    )


def test_administrator_can_manage_roles_and_is_audited_without_operations_secret(product_client):
    client = product_client
    admin, signed_admin = account(client, "administrator@example.test")
    target, signed_target = account(client, "target@example.test")
    admin_path = f"/api/v1/operations/accounts/{admin['account_id']}/role"
    assert (
        client.put(admin_path, headers=OPERATIONS, json={"role": "admin", "version": 1}).status_code
        == 200
    )
    target_path = f"/api/v1/operations/accounts/{target['account_id']}/role"
    result = client.put(
        target_path, headers=auth(signed_admin), json={"role": "editor", "version": 1}
    )
    assert result.status_code == 200
    assert (
        client.put(
            admin_path, headers=auth(signed_target), json={"role": "user", "version": 2}
        ).status_code
        == 403
    )
    with client.app.state.runtime.db.session() as session:
        edits = list(
            session.scalars(
                select(ProductAudit).where(ProductAudit.action == "account.role_change")
            )
        )
        assert any(
            edit.actor_id == admin["account_id"] and edit.target_id == target["account_id"]
            for edit in edits
        )
    security = client.get("/openapi.json").json()["paths"][
        "/api/v1/operations/accounts/{account_id}/role"
    ]["put"]["security"]
    assert {"OperationsBearer": []} in security and {"AccountBearer": []} in security


def test_failed_login_rate_limit_is_persistent(product_client):
    client = product_client
    account(client)
    statuses = [
        client.post(
            "/api/v1/auth/sessions", json={"email": "owner@example.test", "password": "incorrect"}
        ).status_code
        for _ in range(8)
    ]
    assert statuses == [401] * 7 + [429]
    store = AccountStore(client.app.state.runtime.db, client.app.state.settings)
    with pytest.raises(StoreError) as error:
        store.login(
            type("Login", (), {"email": "owner@example.test", "password": PASSWORD})(), "new-ip"
        )
    assert error.value.status == 429


def test_conversation_turn_memory_is_owned_bounded_and_ignored_when_deleted(product_client, photo):
    client = product_client
    headers, other = identity(client), identity(client)
    chat = conversation(client, headers, memory=True)
    chat_id = chat["conversation_id"]
    assert client.get(f"/api/v1/conversations/{chat_id}", headers=other).status_code == 404
    asset = upload(client, headers, photo)
    first = enqueue(client, headers, asset, conversation_id=chat_id)
    Worker(client.app.state.runtime).process_one()
    messages = client.get(f"/api/v1/conversations/{chat_id}/messages", headers=headers).json()
    assert [item["role"] for item in messages["items"]] == ["user", "assistant"]
    assert all(item["provenance"]["verified"] is False for item in messages["items"])
    body = {"asset_id": asset, "question": "Đối chiếu thêm", "conversation_id": chat_id}
    replay_headers = {**headers, "Idempotency-Key": "one-turn"}
    second = client.post("/api/v1/runs", headers=replay_headers, json=body)
    assert second.status_code == 202
    assert (
        client.post("/api/v1/runs", headers=replay_headers, json=body).json()["run_id"]
        == second.json()["run_id"]
    )
    owner = client.get("/api/v1/sessions/me", headers=headers).json()["session_id"]
    record = client.app.state.runtime.store.get_run(second.json()["run_id"], owner)
    memory = record.input_context["conversation_memory"]
    assert len(memory) == 2 and all(item["unverified_context"] for item in memory)
    assert sum(len(item["content"]) for item in memory) <= 4000
    with client.app.state.runtime.db.session() as session:
        session.execute(update(Run).where(Run.id == first).values(deleted_at=1))
    assert (
        client.get(f"/api/v1/conversations/{chat_id}/memory", headers=headers).json()["items"] == []
    )
    page = client.get(f"/api/v1/conversations/{chat_id}/messages", headers=headers).json()
    assert page["total"] == 1  # only the next pending user message remains visible


def test_memory_is_opt_in_clearable_and_conversation_cannot_be_deleted_while_active(
    product_client, photo
):
    client = product_client
    headers = identity(client)
    chat = conversation(client, headers)
    path = "/api/v1/conversations/" + chat["conversation_id"]
    asset = upload(client, headers, photo)
    run_id = enqueue(client, headers, asset, conversation_id=chat["conversation_id"])
    assert client.delete(path, headers=headers).status_code == 409
    Worker(client.app.state.runtime).process_one()
    assert client.get(path + "/memory", headers=headers).json()["items"] == []
    updated = client.patch(path, headers=headers, json={"memory_enabled": True, "version": 1})
    assert updated.status_code == 200
    assert client.get(path + "/memory", headers=headers).json()["items"]
    assert client.delete(path + "/memory", headers=headers).status_code == 204
    assert client.get(path + "/memory", headers=headers).json()["items"] == []
    assert client.get(path + "/messages", headers=headers).json()["total"] == 2
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.get(f"/api/v1/runs/{run_id}", headers=headers).status_code == 200
    with client.app.state.runtime.db.session() as session:
        assert session.scalar(select(func.count()).select_from(ConversationMessage)) == 0


def test_memory_turns_serialize_and_rejected_admission_does_not_consume_idempotency(
    product_client, photo
):
    client = product_client
    headers = identity(client)
    chat = conversation(client, headers, memory=True)
    asset = upload(client, headers, photo)
    first = enqueue(client, headers, asset, conversation_id=chat["conversation_id"])
    body = {
        "asset_id": asset,
        "question": "Câu tiếp theo",
        "conversation_id": chat["conversation_id"],
    }
    keyed = {**headers, "Idempotency-Key": "after-first-turn"}
    response = client.post("/api/v1/runs", headers=keyed, json=body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "conversation_busy"
    assert client.get("/api/v1/runs", headers=headers).json()["total"] == 1
    Worker(client.app.state.runtime).process_one()
    second = client.post("/api/v1/runs", headers=keyed, json=body)
    assert second.status_code == 202
    assert (
        client.post("/api/v1/runs", headers=keyed, json=body).json()["run_id"]
        == second.json()["run_id"]
    )
    owner = client.get("/api/v1/sessions/me", headers=headers).json()["session_id"]
    created = client.app.state.runtime.store.get_run(second.json()["run_id"], owner)
    assert {entry["run_id"] for entry in created.input_context["conversation_memory"]} == {first}


def test_favorites_are_heritages_not_run_bookmarks_and_hide_withdrawn_records(product_client):
    client = product_client
    _, signed = account(client)
    rt = client.app.state.runtime
    store = CatalogStore(rt.db)
    created = store.create(HeritageWrite.model_validate(catalog_record()))
    identifier = created["heritage_id"]
    path = "/api/v1/users/me/heritage-favorites/" + identifier
    assert client.put(path, headers=identity(client)).status_code == 403
    first = client.put(path, headers=auth(signed))
    assert first.status_code == 200
    assert client.put(path, headers=auth(signed)).json()["created_at"] == first.json()["created_at"]
    assert (
        client.get("/api/v1/users/me/heritage-favorites", headers=auth(signed)).json()["total"] == 1
    )
    store.replace(
        identifier, HeritageWrite.model_validate(catalog_record(content_status="draft", version=1))
    )
    assert (
        client.get("/api/v1/users/me/heritage-favorites", headers=auth(signed)).json()["total"] == 0
    )


def test_operator_cli_uses_explicit_database_and_records_reason_without_secrets(product_client):
    client = product_client
    profile, signed = account(client)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "DATABASE_URL" and not key.startswith("API_")
    }
    environment.update(
        PYTHON_DOTENV_DISABLED="1",
        API_MODEL_MODE="demo",
        API_ENV="development",
        DATABASE_URL=client.app.state.settings.database_url.get_secret_value(),
    )
    command = [
        sys.executable,
        "-m",
        "scripts.manage_account",
        "--email",
        profile["email"],
        "--role",
        "editor",
        "--reason",
        "Assign test reviewer",
    ]
    cwd = Path(__file__).resolve().parents[1]
    preview = subprocess.run(
        [*command, "--dry-run"],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["dry_run"]
    assert client.get("/api/v1/users/me", headers=auth(signed)).json()["role"] == "user"
    changed = subprocess.run(
        command, cwd=cwd, env=environment, text=True, capture_output=True, check=False, timeout=30
    )
    assert changed.returncode == 0, changed.stderr
    assert json.loads(changed.stdout)["role"] == "editor"
    assert PASSWORD not in changed.stdout and signed["access_token"] not in changed.stdout
    with client.app.state.runtime.db.session() as session:
        record = session.scalar(
            select(ProductAudit).where(ProductAudit.action == "account.role_change")
        )
        assert record.metadata_json["reason"] == "Assign test reviewer"
    environment.pop("DATABASE_URL")
    missing = subprocess.run(
        command, cwd=cwd, env=environment, text=True, capture_output=True, check=False, timeout=30
    )
    assert missing.returncode != 0 and "Set DATABASE_URL explicitly" in missing.stderr


def test_child_context_keeps_catalog_binding_only_for_unchanged_identity(product_client, photo):
    client = product_client
    headers = identity(client)
    owner = client.get("/api/v1/sessions/me", headers=headers).json()["session_id"]
    asset = upload(client, headers, photo)
    rt = client.app.state.runtime
    catalog = CatalogStore(rt.db).create(HeritageWrite.model_validate(catalog_record()))
    ContentStore(rt.db).bind_entity(
        catalog["heritage_id"],
        EntityBindingWrite(
            entity_id="hanoi:van-mieu", version=catalog["version"], note="Test canonical binding"
        ),
        "operations",
    )
    snapshot = rt.config().snapshot()
    parent = rt.store.create_run(
        owner,
        RunCreate(asset_id=asset, question="Original", heritage_id=catalog["heritage_id"]),
        snapshot,
        "demo",
    )
    with rt.db.session() as session:
        session.execute(update(Run).where(Run.id == parent.id).values(execution_status="succeeded"))
    assert parent.input_context["canonical_entity_id"] == "hanoi:van-mieu"
    child = rt.store.create_run(
        owner,
        RunCreate(asset_id=asset, question="Retry", parent_run_id=parent.id),
        snapshot,
        "demo",
    )
    assert child.input_context["heritage_id"] == catalog["heritage_id"]
    assert child.input_context["canonical_entity_id"] == "hanoi:van-mieu"
    assert child.input_context["location_hint"]["provenance"] == "user"
    with rt.db.session() as session:
        session.execute(update(Run).where(Run.id == child.id).values(execution_status="succeeded"))
    candidate = rt.store.create_run(
        owner,
        RunCreate(asset_id=asset, question="Change candidate", parent_run_id=parent.id),
        snapshot,
        "demo",
        input_context={"selected_candidate": "OTHER"},
    )
    assert "heritage_id" not in candidate.input_context
    assert "canonical_entity_id" not in candidate.input_context
    with rt.db.session() as session:
        session.execute(
            update(Run).where(Run.id == candidate.id).values(execution_status="succeeded")
        )
    from PIL import Image

    from core.images import image_bytes

    replacement = upload(client, headers, image_bytes(Image.new("RGB", (40, 30), "blue")))
    new_image = rt.store.create_run(
        owner,
        RunCreate(asset_id=replacement, question="New image", parent_run_id=parent.id),
        snapshot,
        "demo",
    )
    assert "heritage_id" not in new_image.input_context
    with rt.db.session() as session:
        session.execute(
            update(Run).where(Run.id == new_image.id).values(execution_status="succeeded")
        )
    explicit = rt.store.create_run(
        owner,
        RunCreate(
            asset_id=replacement,
            question="Explicit selection",
            parent_run_id=parent.id,
            heritage_id=catalog["heritage_id"],
        ),
        snapshot,
        "demo",
        input_context={"selected_candidate": "OTHER"},
    )
    assert explicit.input_context["heritage_id"] == catalog["heritage_id"]
    assert explicit.input_context["canonical_entity_id"] == "hanoi:van-mieu"
