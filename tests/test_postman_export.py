import json

import pytest

from api.main import app
from scripts.export_postman import DEFAULTS, ROOT, SECRET_KEYS, build_collection, environment


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
    assert len(operations) == 81 and len(requests) == 84
    assert len({item["id"] for item in requests}) == len(requests)


def test_environment_templates_have_no_secrets_or_runtime_ids():
    for suffix, name, url in (
        ("demo", "Heritage VQA - Demo", "http://127.0.0.1:8001"),
        ("local", "Heritage VQA - Local API", "http://127.0.0.1:8000"),
    ):
        data = read(f"heritage-vqa-{suffix}.postman_environment.json")
        assert data == environment(name, url)
        values = {entry["key"]: entry for entry in data["values"]}
        for key in SECRET_KEYS:
            assert values[key]["value"] == "" and values[key]["type"] == "secret"
        for key in (
            "session_id",
            "asset_id",
            "run_id",
            "retry_run_id",
            "heritage_id",
            "heritage_media_id",
            "account_id",
            "conversation_id",
            "source_id",
            "version_id",
            "delete_run_id",
            "delete_media_id",
            "delete_conversation_id",
            "archive_heritage_id",
        ):
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
            if path.startswith("/api/v1/operations/"):
                editor = any("AccountBearer" in rule for rule in operation.get("security", []))
                expected_token = (
                    "{{role_token}}"
                    if path.startswith("/api/v1/operations/accounts/")
                    else "{{editorial_token}}"
                    if editor
                    else "{{operations_token}}"
                )
                assert request["auth"]["bearer"][0]["value"] == expected_token


def test_new_api_operation_requires_exporter_update():
    schema = {"paths": {**app.openapi()["paths"], "/new-route": {"get": {}}}}
    with pytest.raises(ValueError, match="API contract changed"):
        build_collection(schema)


def test_runner_defaults_require_explicit_model_editorial_account_and_deletion_intent():
    collection = build_collection(app.openapi())
    requests = [item for folder in collection["item"] for item in folder["item"]]
    for key, value in DEFAULTS.items():
        if key.startswith(("enable_", "allow_live_")) or key == "live_model_consent":
            assert value == "false", key
    for item in requests:
        method, path = item["request"]["description"].splitlines()[0].split(" ", 1)
        before = "\n".join(
            line
            for event in item["event"]
            if event["listen"] == "prerequest"
            for line in event["script"]["exec"]
        )
        model_call = method == "POST" and (
            path == "/api/v1/runs"
            or (
                path.startswith("/api/v1/runs/")
                and path.endswith(("/retry", "/review", "/clarification", "/resume"))
            )
        )
        if model_call:
            assert "enable_model_calls" in before
            assert "await pm.sendRequest" in before
            assert "allow_live_model_calls" in before and "live_model_consent" in before
            assert "caps.model_mode" in before
        if method == "DELETE" or path.endswith(("/archive", "/withdraw")):
            assert "enable_destructive_actions" in before
        if method == "POST" and path == "/api/v1/accounts":
            assert "enable_accounts" in before
        if path.endswith("/role"):
            assert "enable_role_changes" in before
        if path.startswith("/api/v1/operations/content-sources") and path.endswith("/review"):
            assert "enable_source_review" in before and "reviewed_against_source" in before
        if path.startswith("/api/v1/operations/content-sources") and path.endswith("/publish"):
            assert "enable_source_publish" in before
    delete_run = next(
        item
        for item in requests
        if item["request"]["description"].startswith("DELETE /api/v1/runs/{run_id}\n")
    )
    assert "{{delete_run_id}}" in delete_run["request"]["url"]["raw"]
    assert collection["item"][-1]["name"].startswith("15 Session teardown")
