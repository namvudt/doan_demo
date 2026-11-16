"""Editorial publication, canonical context and media tested against isolated DBs."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from random import Random

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.content_models import ContentVersion
from api.content_store import ContentStore, database_search_factory
from api.main import create_app
from core.config import RetrievalPolicy
from tests.test_api import settings as settings
from tests.test_catalog import OPERATIONS, record
from tests.test_catalog import catalog_settings as catalog_settings

SOURCES = "/api/v1/operations/content-sources"
HERITAGES = "/api/v1/operations/heritages"


@pytest.fixture
def editor_client(catalog_settings):
    with TestClient(create_app(catalog_settings)) as client:
        yield client


def heritage(client, identifier="editor-site", **kwargs):
    payload = record(identifier, name="Văn Miếu – Quốc Tử Giám", **kwargs)
    response = client.post(HERITAGES, headers=OPERATIONS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def source(client, site="editor-site", text=None):
    response = client.post(
        SOURCES,
        headers=OPERATIONS,
        json={
            "heritage_id": site,
            "title": "Văn Miếu — tư liệu dùng trong kiểm thử",
            "url": "https://vanmieu.gov.vn/nguon-kiem-thu",
            "publisher": "Nhà xuất bản kiểm thử",
            "text": text
            or "Văn Miếu có một dữ kiện tư liệu minh họa được người vận hành kiểm tra.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def transition(client, document, action, *, version_id=None, expected_status=200):
    version = version_id or document["versions"][0]["version_id"]
    body = {"version": document["version"]}
    if action == "review":
        body.update(attestation="reviewed_against_source", note="Đã đối chiếu tư liệu kiểm thử.")
    response = client.post(
        f"{SOURCES}/{document['source_id']}/versions/{version}/{action}",
        headers=OPERATIONS,
        json=body,
    )
    assert response.status_code == expected_status, response.text
    return response.json()


def test_sources_require_account_editor_or_server_operations(editor_client):
    client = editor_client
    heritage(client)
    assert client.get(SOURCES).status_code == 401
    guest = client.post("/api/v1/sessions", json={"label": "reader"}).json()
    assert (
        client.get(
            SOURCES, headers={"Authorization": f"Bearer {guest['access_token']}"}
        ).status_code
        == 403
    )
    body = {
        "email": "editor@example.test",
        "password": "safe-test-password-123",
        "display_name": "Biên tập",
    }
    account = client.post("/api/v1/accounts", json=body)
    assert account.status_code == 201, account.text
    created = account.json()
    login = client.post(
        "/api/v1/auth/sessions", json={"email": body["email"], "password": body["password"]}
    )
    assert login.status_code == 200, login.text
    auth = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get(SOURCES, headers=auth).status_code == 403
    promoted = client.put(
        f"/api/v1/operations/accounts/{created['account_id']}/role",
        headers=OPERATIONS,
        json={"role": "editor", "version": created["version"]},
    )
    assert promoted.status_code == 200, promoted.text
    assert client.get(SOURCES, headers=auth).status_code == 200
    assert (
        client.post(HERITAGES, headers=auth, json=record("account-edited-site")).status_code == 201
    )
    rejected_role = client.put(
        f"/api/v1/operations/accounts/{created['account_id']}/role",
        headers=auth,
        json={"role": "admin", "version": promoted.json()["version"]},
    )
    assert rejected_role.status_code in {401, 403}


def test_source_review_publish_versions_and_withdrawal_are_transactional(editor_client, tmp_path):
    client = editor_client
    heritage(client)
    store = ContentStore(client.app.state.runtime.db)
    policy = RetrievalPolicy(wikipedia_enabled=False, corpus_path=str(tmp_path / "missing.jsonl"))
    engine = database_search_factory(store.db, policy=policy, bound_heritage_id="editor-site")()
    original = source(client)
    original_text = original["versions"][0]["text"]
    identifier = original["source_id"]
    assert original["versions"][0]["status"] == "draft"
    assert client.get("/api/v1/heritages/editor-site/sources").json()["items"] == []
    assert engine.curated_sources("Văn Miếu tư liệu") == []
    transition(client, original, "publish", expected_status=409)
    assert store.get(identifier)["version"] == 1
    reviewed = transition(client, original, "review")
    assert reviewed["versions"][0]["reviewer"] == "operations"
    assert (
        reviewed["versions"][0]["content_hash"]
        == hashlib.sha256(original_text.encode()).hexdigest()
    )
    before_publish = store.retrieval_revision()
    published = transition(client, reviewed, "publish")
    assert store.retrieval_revision() != before_publish
    retrieved = engine.curated_sources("Văn Miếu tư liệu", entity_terms=["Văn Miếu"])
    assert len(retrieved) == 1
    assert retrieved[0]["annotation_status"] == "reviewed"
    assert retrieved[0]["revision_id"] == published["versions"][0]["version_id"]
    assert retrieved[0]["content_hash"] == published["versions"][0]["content_hash"]
    second = client.post(
        f"{SOURCES}/{identifier}/versions",
        headers=OPERATIONS,
        json={
            "version": published["version"],
            "text": "Văn Miếu có nội dung phiên bản kế tiếp, riêng biệt với bản đầu.",
        },
    )
    assert second.status_code == 201, second.text
    second = second.json()
    assert second["versions"][1]["text"] == original_text
    assert (
        engine.curated_sources("Văn Miếu tư liệu")[0]["revision_id"]
        == published["versions"][0]["version_id"]
    )
    reviewed_second = transition(client, second, "review")
    published_second = transition(client, reviewed_second, "publish")
    assert [v["status"] for v in published_second["versions"]] == ["published", "archived"]
    assert (
        engine.curated_sources("Văn Miếu nội dung")[0]["revision_id"]
        == published_second["versions"][0]["version_id"]
    )
    before_withdraw = store.retrieval_revision()
    withdrawn = transition(client, published_second, "withdraw")
    assert withdrawn["versions"][0]["status"] == "archived"
    assert store.retrieval_revision() != before_withdraw
    assert engine.curated_sources("Văn Miếu nội dung") == []
    history = client.get(
        "/api/v1/operations/heritages/editor-site/audit", headers=OPERATIONS
    ).json()
    assert {entry["action"] for entry in history["items"]} >= {
        "source.review",
        "source.publish",
        "source.withdraw",
    }


def test_stale_publish_concurrency_and_hash_tampering_fail_closed(editor_client):
    client = editor_client
    heritage(client)
    reviewed = transition(client, source(client), "review")
    url = f"{SOURCES}/{reviewed['source_id']}/versions/{reviewed['versions'][0]['version_id']}/publish"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    url, headers=OPERATIONS, json={"version": reviewed["version"]}
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    document = client.get(f"{SOURCES}/{reviewed['source_id']}", headers=OPERATIONS).json()
    assert document["version"] == 3
    store = ContentStore(client.app.state.runtime.db)
    with store.db.session() as session:
        row = session.get(ContentVersion, reviewed["versions"][0]["version_id"])
        row.text = "Văn Miếu: nội dung bị sửa trái với hash của bản đã duyệt."
    assert store.published_sources() == []
    transition(client, document, "withdraw", expected_status=409)


def test_entity_binding_preserves_parent_component_and_unverified_context(editor_client):
    client = editor_client
    site = heritage(client)
    url = "/api/v1/operations/heritages/editor-site/entity-binding"
    binding = client.put(
        url,
        headers=OPERATIONS,
        json={
            "version": site["version"],
            "entity_id": "hanoi:van-mieu",
            "note": "Ánh xạ nhãn di tích, chưa xác minh ảnh.",
        },
    )
    assert binding.status_code == 200, binding.text
    context = client.get("/api/v1/heritages/editor-site/context").json()
    assert context["canonical_entity_id"] == "hanoi:van-mieu"
    assert context["location_hint"]["provenance"] == "user"
    assert "evidence" not in context
    component = heritage(client, "component-site")
    component_url = "/api/v1/operations/heritages/component-site/entity-binding"
    payload = {
        "version": component["version"],
        "entity_id": "hanoi:khue-van-cac",
        "note": "Nhãn cấu phần được liên kết rõ.",
    }
    assert client.put(component_url, headers=OPERATIONS, json=payload).status_code == 422
    payload["parent_heritage_id"] = "editor-site"
    assert client.put(component_url, headers=OPERATIONS, json=payload).status_code == 200
    assert (
        client.put(
            url,
            headers=OPERATIONS,
            json={
                "version": context["heritage_version"],
                "entity_id": "hanoi:hoang-thanh",
                "note": "Không được làm hỏng liên kết cấu phần.",
            },
        ).status_code
        == 422
    )
    assert client.get("/api/v1/heritages/editor-site/context").json() == context


def test_uploaded_media_replace_delete_archive_and_conflict_cleanup(
    editor_client, photo, catalog_settings
):
    client = editor_client
    site = heritage(client)
    upload_url = "/api/v1/operations/heritages/editor-site/media"
    directory = catalog_settings.data_dir / "catalog-media"

    def upload(version, data=photo, url=upload_url, method="post"):
        return getattr(client, method)(
            url,
            headers=OPERATIONS,
            data={"version": version, "alt": "Ảnh kiểm thử"},
            files={"file": ("../../client-name.png", data, "image/png")},
        )

    assert upload(site["version"], b"not-an-image").status_code == 422
    first = upload(site["version"])
    assert first.status_code == 201, first.text
    first = first.json()
    assert len(list(directory.glob("*.png"))) == 1
    details = client.get("/api/v1/heritages/editor-site").json()
    added = next(m for m in details["media"] if m["media_id"] == first["media_id"])
    assert client.get(added["url"]).status_code == 200
    assert upload(site["version"]).status_code == 409
    assert len(list(directory.glob("*.png"))) == 1
    replaced = upload(details["version"], url=upload_url + "/" + first["media_id"], method="put")
    assert replaced.status_code == 200, replaced.text
    assert len(list(directory.glob("*.png"))) == 1
    assert (
        client.delete(
            upload_url + "/" + first["media_id"],
            headers=OPERATIONS,
            params={"version": replaced.json()["heritage_version"]},
        ).status_code
        == 204
    )
    assert client.get(added["url"]).status_code == 404
    assert not list(directory.glob("*.png"))
    assert (catalog_settings.catalog_media_dir / "catalog-test.png").is_file()
    current = client.get("/api/v1/heritages/editor-site").json()
    document = transition(client, transition(client, source(client), "review"), "publish")
    assert client.get("/api/v1/heritages/editor-site/sources").json()["items"]
    archived = client.post(
        "/api/v1/operations/heritages/editor-site/archive",
        headers=OPERATIONS,
        json={"version": current["version"]},
    )
    assert archived.status_code == 200, archived.text
    assert client.get("/api/v1/heritages/editor-site").status_code == 404
    assert client.get("/api/v1/heritages/editor-site/sources").status_code == 404
    assert ContentStore(client.app.state.runtime.db).published_sources() == []
    assert document["versions"][0]["status"] == "published"


def test_ingest_validates_url_and_never_accepts_fetcher_review_status(editor_client, monkeypatch):
    client = editor_client
    heritage(client)
    assert (
        client.post(
            SOURCES + "/ingest",
            headers=OPERATIONS,
            json={"heritage_id": "editor-site", "url": "http://127.0.0.1/private"},
        ).status_code
        == 422
    )
    calls = []

    def fetched(url, policy):
        calls.append(url)
        return {
            "title": "Văn Miếu — nội dung kiểm thử",
            "url": url,
            "snippet": "Văn Miếu: đoạn văn mô phỏng được nhập để kiểm tra trạng thái dự thảo.",
            "publisher": "Kiểm thử",
            "annotation_status": "reviewed",
            "reviewer": "untrusted-network",
        }

    monkeypatch.setattr("api.content.fetch_source", fetched)
    response = client.post(
        SOURCES + "/ingest",
        headers=OPERATIONS,
        json={"heritage_id": "editor-site", "url": "https://vanmieu.gov.vn/nguon"},
    )
    assert response.status_code == 201, response.text
    version = response.json()["versions"][0]
    assert calls == ["https://vanmieu.gov.vn/nguon"]
    assert version["status"] == "draft" and version["reviewer"] is None
    assert (
        client.post(
            SOURCES,
            headers=OPERATIONS,
            json={
                "heritage_id": "editor-site",
                "title": "Test",
                "url": "https://unlisted.example.test/source",
                "text": "Nội dung kiểm thử đủ dài và chưa được duyệt.",
            },
        ).status_code
        == 422
    )


def test_editor_input_cannot_self_declare_review_or_bypass_trimmed_content_limits(editor_client):
    client = editor_client
    heritage(client)
    payload = {
        "heritage_id": "editor-site",
        "title": "Văn Miếu: nguồn kiểm thử",
        "url": "https://vanmieu.gov.vn/source",
        "text": "Văn Miếu là tên được dùng trong đoạn nguồn kiểm thử.",
    }
    assert (
        client.post(
            SOURCES, headers=OPERATIONS, json={**payload, "text": " " * 30 + "x"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            SOURCES, headers=OPERATIONS, json={**payload, "annotation_status": "reviewed"}
        ).status_code
        == 422
    )
    document = source(client)
    url = (
        f"{SOURCES}/{document['source_id']}/versions/{document['versions'][0]['version_id']}/review"
    )
    assert (
        client.post(
            url,
            headers=OPERATIONS,
            json={"version": 1, "attestation": "reviewed_against_source", "note": " " * 20},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            headers=OPERATIONS,
            json={
                "version": 1,
                "attestation": "reviewed_against_source",
                "note": "Đã kiểm tra nội dung.",
                "reviewer": "spoofed-human",
            },
        ).status_code
        == 422
    )
    assert (
        client.get(f"{SOURCES}/{document['source_id']}", headers=OPERATIONS).json()["version"] == 1
    )


def test_image_normalization_cannot_expand_past_storage_limit(catalog_settings):
    bounded = catalog_settings.model_copy(update={"max_upload_bytes": 4096})
    image = Image.frombytes("RGB", (64, 64), Random(7).randbytes(64 * 64 * 3))
    stream = BytesIO()
    image.save(stream, format="JPEG", quality=50)
    data = stream.getvalue()
    assert len(data) < bounded.max_upload_bytes
    with TestClient(create_app(bounded)) as client:
        site = heritage(client)
        response = client.post(
            "/api/v1/operations/heritages/editor-site/media",
            headers=OPERATIONS,
            data={"version": site["version"]},
            files={"file": ("photo.jpg", data, "image/jpeg")},
        )
        assert response.status_code == 413, response.text
        assert not list((bounded.data_dir / "catalog-media").glob("*.png"))
