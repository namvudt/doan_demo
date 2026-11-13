import json

import pytest

from api.main import app
from scripts.export_postman import ROOT, build_collection, environment


def read(name):
    return json.loads((ROOT / "postman" / name).read_text(encoding="utf-8"))


def test_committed_artifacts_match_current_api_and_cover_all_operations():
    schema = app.openapi()
    collection = read("heritage-vqa.postman_collection.json")
    assert collection == build_collection(schema)
    requests = [item for folder in collection["item"] for item in folder["item"]]
    operations = {item["request"]["description"].splitlines()[0] for item in requests}
    actual = {
        f"{method.upper()} {path}"
        for path, verbs in schema["paths"].items()
        for method in verbs
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert operations == actual
    assert len(operations) == 33 and len(requests) == 36
    assert len({item["id"] for item in requests}) == len(requests)


def test_environment_templates_have_no_secrets_or_runtime_ids():
    for suffix, name, url in (
        ("demo", "Heritage VQA - Demo", "http://127.0.0.1:8001"),
        ("local", "Heritage VQA - Local API", "http://127.0.0.1:8000"),
    ):
        data = read(f"heritage-vqa-{suffix}.postman_environment.json")
        assert data == environment(name, url)
        values = {entry["key"]: entry for entry in data["values"]}
        for key in ("access_token", "bootstrap_token", "operations_token"):
            assert values[key]["value"] == "" and values[key]["type"] == "secret"
        for key in ("session_id", "asset_id", "run_id", "retry_run_id"):
            assert values[key]["value"] == ""


def test_auth_separation_and_all_declared_query_parameters_exported():
    schema = app.openapi()
    collection = read("heritage-vqa.postman_collection.json")
    for folder in collection["item"]:
        for item in folder["item"]:
            request = item["request"]
            method, path = request["description"].splitlines()[0].split(" ", 1)
            operation = schema["paths"][path][method.lower()]
            expected = {p["name"] for p in operation.get("parameters", []) if p["in"] == "query"}
            assert {q["key"] for q in request["url"].get("query", [])} == expected
            if path == "/api/v1/sessions":
                assert request["auth"]["type"] == "noauth"
            if path == "/api/v1/operations/metrics":
                assert request["auth"]["bearer"][0]["value"] == "{{operations_token}}"


def test_new_api_operation_requires_exporter_update():
    schema = {"paths": {**app.openapi()["paths"], "/new-route": {"get": {}}}}
    with pytest.raises(ValueError, match="API contract changed"):
        build_collection(schema)
