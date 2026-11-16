"""Durable public catalog contracts; no provider, model, or network access."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.main import create_app
from tests.test_api import settings as settings

OPERATIONS_TOKEN = "catalog-tests-operations-" + "x" * 32
OPERATIONS = {"Authorization": f"Bearer {OPERATIONS_TOKEN}"}
CATALOG = "/api/v1/heritages"
OPERATIONS_CATALOG = "/api/v1/operations/heritages"


@pytest.fixture
def catalog_settings(tmp_path, photo, settings):
    media = tmp_path / "catalog-media"
    media.mkdir()
    (media / "catalog-test.png").write_bytes(photo)
    return settings.model_copy(
        update={
            "catalog_media_dir": media,
            "operations_token": SecretStr(OPERATIONS_TOKEN),
        }
    )


@pytest.fixture
def catalog_client(catalog_settings):
    with TestClient(create_app(catalog_settings)) as client:
        yield client


def record(identifier="catalog-monument-a", **overrides):
    payload = {
        "heritage_id": identifier,
        "slug": identifier,
        "name": "Di tích kiểm thử Hà Nội",
        "province": "Hà Nội",
        "address": "Địa chỉ minh họa",
        "category": "monument",
        "period": "Tư liệu minh họa",
        "summary": "Hồ sơ phục vụ kiểm thử catalog, không phải tư liệu lịch sử.",
        "historical_information": "Cần đối chiếu trước khi sử dụng.",
        "cultural_information": "Thông tin minh họa.",
        "tags": ["Kiến trúc", "Catalog"],
        "content_status": "published",
        "illustrative": True,
        "location": {
            "latitude": 21.0287,
            "longitude": 105.8522,
            "verification_status": "illustrative",
            "verification_note": "Tọa độ phục vụ kiểm thử; chưa xác minh.",
        },
        "media": [
            {
                "media_id": f"{identifier}-photo",
                "kind": "image",
                "storage_key": "catalog-test.png",
                "alt": "Ảnh kiểm thử catalog",
                "caption": "Ảnh fixture local.",
                "verified": False,
            }
        ],
        "information_sources": [
            {
                "source_id": f"{identifier}-source",
                "title": "Tư liệu kiểm thử",
                "publisher": "Test suite",
                "url": "https://example.test/catalog-reference",
                "kind": "reference",
                "summary": "Metadata minh họa, chưa được lập chỉ mục RAG.",
                "verified": False,
                "verification_note": "Chưa kiểm chứng.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def create_record(client, payload):
    response = client.post(OPERATIONS_CATALOG, headers=OPERATIONS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def guest(client, label):
    response = client.post("/api/v1/sessions", json={"label": label})
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_catalog_records_and_media_survive_an_application_restart(catalog_settings, photo):
    with TestClient(create_app(catalog_settings)) as first:
        original = create_record(first, record())
        assert original["version"] == 1
        assert original["location"]["verification_status"] == "illustrative"
        assert original["information_sources"][0]["index_status"] == "not_indexed"
        content_url = original["media"][0]["url"]
        assert content_url.startswith(f"{CATALOG}/catalog-monument-a/media/")
        assert first.get(content_url).content == photo

    # A fresh Runtime and database engine use the same persisted database/file.
    with TestClient(create_app(catalog_settings)) as reopened:
        caps = reopened.get("/api/v1/capabilities").json()
        assert caps["features"]["heritage_catalog"] is True
        page = reopened.get(CATALOG).json()
        assert page["total"] == 1
        assert page["items"][0]["heritage_id"] == original["heritage_id"]
        assert reopened.get(content_url).content == photo


def test_public_catalog_only_lists_published_records_and_filters_consistently(catalog_client):
    create_record(catalog_client, record())
    create_record(
        catalog_client,
        record(
            "catalog-temple-hue",
            name="Ngôi đền kiểm thử Huế",
            province="Thành phố Huế",
            category="temple",
            location=None,
        ),
    )
    create_record(catalog_client, record("catalog-private-draft", content_status="draft"))
    page = catalog_client.get(CATALOG, params={"limit": 1}).json()
    assert page["total"] == 2
    assert page["limit"] == 1 and page["offset"] == 0 and page["has_more"] is True
    next_page = catalog_client.get(CATALOG, params={"limit": 1, "offset": 1}).json()
    assert next_page["has_more"] is False
    assert page["items"][0]["heritage_id"] != next_page["items"][0]["heritage_id"]
    assert catalog_client.get(f"{CATALOG}/catalog-private-draft").status_code == 404
    for params in (
        {"q": "Hà Nội"},
        {"province": "Hà Nội"},
        {"category": "monument"},
        {"has_location": "true"},
    ):
        filtered = catalog_client.get(CATALOG, params=params).json()
        assert filtered["total"] == 1
        assert filtered["items"][0]["heritage_id"] == "catalog-monument-a"
    assert catalog_client.get(CATALOG, params={"q": "không có hồ sơ này"}).json()["items"] == []
    unlocated = catalog_client.get(CATALOG, params={"has_location": "false"}).json()
    assert [item["heritage_id"] for item in unlocated["items"]] == ["catalog-temple-hue"]
    draft_media = f"{CATALOG}/catalog-private-draft/media/catalog-private-draft-photo/content"
    assert catalog_client.get(draft_media).status_code == 404


def test_catalog_writes_require_an_operator_and_reject_stale_replacements(catalog_client):
    payload = record()
    assert catalog_client.post(OPERATIONS_CATALOG, json=payload).status_code == 401
    visitor = guest(catalog_client, "catalog visitor")
    assert catalog_client.post(OPERATIONS_CATALOG, headers=visitor, json=payload).status_code == 401
    assert catalog_client.post(CATALOG, json=payload).status_code in {404, 405}
    original = create_record(catalog_client, payload)
    update_url = f"{OPERATIONS_CATALOG}/{original['heritage_id']}"
    assert catalog_client.put(update_url, headers=OPERATIONS, json=payload).status_code == 428
    updated = catalog_client.put(
        update_url,
        headers=OPERATIONS,
        json={**payload, "name": "Tên đã được chỉnh sửa", "version": original["version"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    conflict = catalog_client.put(
        update_url, headers=OPERATIONS, json={**payload, "version": original["version"]}
    )
    assert conflict.status_code == 409
    assert (
        catalog_client.get(f"{CATALOG}/{original['heritage_id']}").json()["name"]
        == "Tên đã được chỉnh sửa"
    )


def test_catalog_operations_remain_disabled_without_server_configuration(catalog_settings):
    disabled = catalog_settings.model_copy(update={"operations_token": SecretStr("")})
    with TestClient(create_app(disabled)) as client:
        response = client.post(OPERATIONS_CATALOG, headers=OPERATIONS, json=record())
        assert response.status_code == 503
        assert client.get(CATALOG).json()["items"] == []


def test_withdrawn_record_and_its_public_media_are_no_longer_readable(catalog_client):
    payload = record()
    original = create_record(catalog_client, payload)
    content_url = original["media"][0]["url"]
    assert catalog_client.get(content_url).status_code == 200
    response = catalog_client.put(
        f"{OPERATIONS_CATALOG}/{original['heritage_id']}",
        headers=OPERATIONS,
        json={**payload, "content_status": "draft", "version": original["version"]},
    )
    assert response.status_code == 200
    assert catalog_client.get(CATALOG).json()["total"] == 0
    assert catalog_client.get(f"{CATALOG}/{original['heritage_id']}").status_code == 404
    assert catalog_client.get(content_url).status_code == 404


@pytest.mark.parametrize(
    "location",
    [
        {"latitude": 91, "longitude": 105, "verification_status": "illustrative"},
        {"latitude": 21, "longitude": -181, "verification_status": "illustrative"},
        {"latitude": 21, "verification_status": "illustrative"},
        {"latitude": 21, "longitude": 105, "verification_status": "verified"},
    ],
)
def test_invalid_or_unproven_coordinates_are_not_published(catalog_client, location):
    response = catalog_client.post(
        OPERATIONS_CATALOG, headers=OPERATIONS, json=record(location=location)
    )
    assert response.status_code == 422
    assert response.json()["error"]["request_id"]
    assert catalog_client.get(CATALOG).json()["total"] == 0


def test_verified_coordinates_require_a_verified_linked_source(catalog_client):
    payload = record(illustrative=False)
    payload["location"] = {
        "latitude": 21,
        "longitude": 105,
        "verification_status": "verified",
        "source_id": payload["information_sources"][0]["source_id"],
        "verification_note": "Đối chiếu với tư liệu đã xác minh trong test fixture.",
    }
    rejected = catalog_client.post(OPERATIONS_CATALOG, headers=OPERATIONS, json=payload)
    assert rejected.status_code == 422
    payload["information_sources"][0]["verified"] = True
    created = create_record(catalog_client, payload)
    assert created["location"]["verification_status"] == "verified"
    assert created["location"]["source_id"] == created["information_sources"][0]["source_id"]


@pytest.mark.parametrize(
    "storage_key", ["../private.png", "subdir/photo.png", "https://example.test/a.jpg"]
)
def test_catalog_media_does_not_accept_paths_or_external_fetches(catalog_client, storage_key):
    payload = record()
    payload["media"][0]["storage_key"] = storage_key
    response = catalog_client.post(OPERATIONS_CATALOG, headers=OPERATIONS, json=payload)
    assert response.status_code == 422
    assert catalog_client.get(CATALOG).json()["total"] == 0


def test_catalog_photo_can_be_imported_as_an_owned_asset_without_creating_an_ai_run(catalog_client):
    created = create_record(catalog_client, record())
    media_id = created["media"][0]["media_id"]
    bridge = f"{CATALOG}/{created['heritage_id']}/media/{media_id}/assets"
    assert catalog_client.post(bridge).status_code == 401
    alice = guest(catalog_client, "catalog importer")
    bob = guest(catalog_client, "other catalog visitor")
    response = catalog_client.post(bridge, headers=alice)
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["width"] > 0 and asset["height"] > 0
    assert catalog_client.get(asset["content_url"], headers=alice).status_code == 200
    assert catalog_client.get(asset["content_url"], headers=bob).status_code == 404
    assert catalog_client.get(asset["content_url"]).status_code == 401
    assert catalog_client.get("/api/v1/runs", headers=alice).json()["total"] == 0


def test_repeated_seed_does_not_duplicate_or_overwrite_an_edited_record(catalog_client):
    from api.catalog_store import CatalogStore

    store = CatalogStore(catalog_client.app.state.runtime.db)
    seed = record()
    assert store.upsert_seed([deepcopy(seed)]) == {"created": 1, "updated": 0, "skipped": 0}
    assert store.upsert_seed([deepcopy(seed)]) == {"created": 0, "updated": 0, "skipped": 1}
    assert catalog_client.get(CATALOG).json()["total"] == 1
    current = catalog_client.get(f"{CATALOG}/{seed['heritage_id']}").json()
    response = catalog_client.put(
        f"{OPERATIONS_CATALOG}/{seed['heritage_id']}",
        headers=OPERATIONS,
        json={**seed, "version": current["version"], "name": "Tên do biên tập viên sửa"},
    )
    assert response.status_code == 200
    store.upsert_seed([deepcopy(seed)])
    preserved = catalog_client.get(f"{CATALOG}/{seed['heritage_id']}").json()
    assert preserved["name"] == "Tên do biên tập viên sửa"
    assert catalog_client.get(CATALOG).json()["total"] == 1
