"""Audit the running local demo deployment without calling an external model.

The report stores operation names, statuses and safe summary fields only. Session
tokens and response bodies are never written to disk. Existing runs are not edited.
"""

import argparse
import ast
import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete"}
FEATURE_OPERATIONS = {
    ("GET", "/api/v1/runs/{run_id}/evidence"),
    ("GET", "/api/v1/runs/{run_id}/regions/{region_id}/image"),
    ("GET", "/api/v1/runs/{run_id}/clarification"),
    ("POST", "/api/v1/runs/{run_id}/clarification"),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def source_operations(path, prefix=""):
    """Read declared operations without importing an app or loading server secrets."""
    return text_operations(path.read_text(encoding="utf-8-sig"), prefix)


def text_operations(source, prefix=""):
    operations = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                not isinstance(decorator, ast.Call)
                or not isinstance(decorator.func, ast.Attribute)
                or decorator.func.attr not in METHODS
                or not decorator.args
                or not isinstance(decorator.args[0], ast.Constant)
            ):
                continue
            if any(
                item.arg == "include_in_schema"
                and isinstance(item.value, ast.Constant)
                and item.value.value is False
                for item in decorator.keywords
            ):
                continue
            operations.add((decorator.func.attr.upper(), prefix + decorator.args[0].value))
    return operations


def openapi_operations(document):
    return {
        (method.upper(), path)
        for path, methods in document["paths"].items()
        for method in methods
        if method in METHODS
    }


def checkout_operations(root):
    """Read the checkout's main app and any separately mounted API routers."""
    operations = source_operations(root / "api/main.py")
    for module in ("catalog", "accounts", "conversations", "content", "lifecycle"):
        path = root / f"api/{module}.py"
        # Historical reference checkouts may predate one or more routers.
        if path.is_file():
            operations |= source_operations(path, "/api/v1")
    return operations


def route_baseline(reference=None):
    """Use current sources by default, including in shallow or exported checkouts."""
    current = checkout_operations(ROOT)
    if reference is None:
        return current, current, "current source checkout"
    return checkout_operations(reference), current, "explicit reference checkout"


class Audit:
    def __init__(self, client):
        self.client = client
        self.cases = []

    def call(self, name, method, path, expected=200, **kwargs):
        started = time.monotonic()
        response = self.client.request(method, path, **kwargs)
        passed = response.status_code == expected
        self.cases.append(
            {
                "name": name,
                "method": method,
                "status": response.status_code,
                "expected_status": expected,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "passed": passed,
            }
        )
        require(passed, f"{name}: unexpected HTTP status {response.status_code}")
        return response

    def wait(self, identifier, auth):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/v1/runs/{identifier}", headers=auth)
            require(response.status_code == 200, "Run polling failed")
            run = response.json()
            if run["execution_status"] in {"succeeded", "failed", "cancelled", "awaiting_input"}:
                require(
                    run["execution_status"] in {"succeeded", "awaiting_input"},
                    "Demo run did not finish successfully",
                )
                return run
            time.sleep(0.1)
        raise AssertionError("Worker did not finish demo run within 30 seconds")


def verify(audit, reference, expected_build=None):
    # Refuse live deployments before session/asset/run mutations.
    response = audit.call("Read capabilities", "GET", "/api/v1/capabilities")
    capabilities = response.json()
    require(capabilities["model_mode"] == "demo", "Refusing a non-demo deployment")
    require(not capabilities["session_bootstrap_required"], "Operator-issued session required")
    require(capabilities.get("accuracy", {}).get("enabled"), "Evidence profile is not enabled")
    require(capabilities.get("features", {}).get("heritage_catalog"), "Catalog is not advertised")
    build = response.headers.get("x-backend-build")
    require(bool(build), "Backend build identity header is missing")
    if expected_build:
        require(build == expected_build, "Running image does not match the expected build")
    readiness = audit.call("Database and worker ready", "GET", "/health/ready").json()
    require(readiness["database"] and readiness["worker"], "Database/worker is not ready")
    specification = audit.call("Read deployed OpenAPI", "GET", "/openapi.json").json()
    deployed = openapi_operations(specification)
    reference_set, merged_set, baseline = route_baseline(reference)
    require(FEATURE_OPERATIONS <= deployed, "A feature endpoint is missing")
    require(reference_set <= deployed, "A reference backend operation is missing")
    require(deployed == merged_set, "Running OpenAPI differs from the merged source routes")

    # Import only wire models, not api.main or Settings.from_env().
    from api.schemas import ClarificationView, EvidenceView, ResultView, RunView
    from core.evidence import CheckedClaim, Evidence

    schemas = specification["components"]["schemas"]
    for field in ("location_hint", "focus_box", "heritage_id", "conversation_id"):
        require(field in schemas["RunCreate"]["properties"], f"RunCreate lacks {field}")
    for field in ("recognition", "evidence", "claims", "clarification", "result_schema_version"):
        require(field in schemas["ResultView"]["properties"], f"ResultView lacks {field}")

    public = audit.call("Read persisted public catalog", "GET", "/api/v1/heritages").json()
    require(public["total"] >= 7, "Seeded public heritage records are missing")
    media_count = 0
    for heritage in public["items"]:
        require(heritage["content_status"] == "published", "A draft escaped the public catalog")
        for media in heritage["media"]:
            image = audit.call("Decode public catalog image", "GET", media["url"])
            with Image.open(io.BytesIO(image.content)) as decoded:
                decoded.load()
                require(min(decoded.size) > 0, "Invalid catalog image")
            media_count += 1

    credentials = []
    summary = {
        "model_mode": capabilities["model_mode"],
        "api_version": capabilities["api_version"],
        "openapi_version": specification["info"]["version"],
        "backend_build": build,
        "config_hash": capabilities["config_hash"],
        "accuracy": capabilities["accuracy"],
        "profiles": capabilities["profiles"],
        "reference_operations": len(reference_set),
        "reference_baseline": baseline,
        "deployed_operations": len(deployed),
        "missing_reference_operations": sorted(reference_set - deployed),
        "source_openapi_match": deployed == merged_set,
        "published_heritages": public["total"],
        "catalog_images_decoded": media_count,
    }
    try:
        for label in ("evidence deployment owner", "evidence deployment other owner"):
            session = audit.call(
                "Create temporary guest", "POST", "/api/v1/sessions", 201, json={"label": label}
            ).json()
            credentials.append({"Authorization": "Bearer " + session["access_token"]})
        auth, other = credentials
        samples = audit.call("List sample images", "GET", "/api/v1/samples", headers=auth).json()
        require(bool(samples["items"]), "No sample is available")
        asset = audit.call(
            "Create owned sample asset",
            "POST",
            f"/api/v1/samples/{samples['items'][0]['sample_id']}/assets",
            201,
            headers=auth,
        ).json()
        body = {
            "asset_id": asset["asset_id"],
            "question": "Mô tả chi tiết nhìn thấy và đối chiếu tư liệu của công trình.",
            "focus_box": [0.1, 0.1, 0.8, 0.8],
            "location_hint": {"name": "Địa điểm thử nghiệm", "provenance": "user"},
        }
        key = "deploy-" + str(uuid4())
        headers = {**auth, "Idempotency-Key": key}
        created = audit.call(
            "Enqueue evidence-v2 run", "POST", "/api/v1/runs", 202, headers=headers, json=body
        ).json()
        RunView.model_validate(created)
        replay = audit.call(
            "Replay the same idempotent request",
            "POST",
            "/api/v1/runs",
            202,
            headers=headers,
            json=body,
        ).json()
        require(replay["run_id"] == created["run_id"], "Idempotency replay created another run")
        audit.call(
            "Reject changed request under same key",
            "POST",
            "/api/v1/runs",
            409,
            headers=headers,
            json={**body, "question": "Different request"},
        )
        identifier = created["run_id"]
        audit.wait(identifier, auth)
        base = f"/api/v1/runs/{identifier}"
        result = audit.call(
            "Read typed evidence result", "GET", base + "/result", headers=auth
        ).json()
        ResultView.model_validate(result)
        require(result["result_schema_version"] == 2, "Worker used the legacy workflow")
        require(
            result["location_hint"] == body["location_hint"], "Location hint provenance was lost"
        )
        evidence = audit.call(
            "Read typed evidence endpoint", "GET", base + "/evidence", headers=auth
        ).json()
        EvidenceView.model_validate(evidence)
        for field in ("recognition", "location_hint", "evidence", "claims", "regions"):
            expected = result[field]
            if field in {"evidence", "claims"}:
                model = Evidence if field == "evidence" else CheckedClaim
                expected = [model.model_validate(item).model_dump(mode="json") for item in expected]
            require(evidence[field] == expected, f"Evidence/result disagree on {field}")
        require(bool(evidence["evidence"]), "Evidence registry is empty")
        require(bool(evidence["regions"]), "Requested focus region is missing")
        region = evidence["regions"][0]["region_id"]
        region_path = base + f"/regions/{region}/image"
        crop = audit.call("Decode owned evidence crop", "GET", region_path, headers=auth)
        require(crop.headers["content-type"].startswith("image/png"), "Crop MIME is incorrect")
        with Image.open(io.BytesIO(crop.content)) as decoded:
            decoded.load()
            require(min(decoded.size) > 0, "Evidence crop is invalid")
        audit.call("Evidence needs authentication", "GET", base + "/evidence", 401)
        audit.call(
            "Other owner cannot read evidence", "GET", base + "/evidence", 404, headers=other
        )
        audit.call("Other owner cannot read crop", "GET", region_path, 404, headers=other)
        audit.call(
            "Unknown crop ID rejected", "GET", base + "/regions/unknown/image", 404, headers=auth
        )
        pending = audit.call(
            "Read clarification state", "GET", base + "/clarification", headers=auth
        ).json()
        ClarificationView.model_validate(pending)
        audit.call(
            "Other owner cannot read clarification",
            "GET",
            base + "/clarification",
            404,
            headers=other,
        )
        if pending["clarification"]:
            prompt = pending["clarification"]
            continuation = {
                "clarification_id": prompt["clarification_id"],
                "revision": prompt["revision"],
                "answer": "Thông tin bổ sung để kiểm tra luồng demo.",
            }
            continuation_headers = {**auth, "Idempotency-Key": "continue-" + str(uuid4())}
            child = audit.call(
                "Continue actual pending clarification",
                "POST",
                base + "/clarification",
                202,
                headers=continuation_headers,
                json=continuation,
            ).json()
            replay = audit.call(
                "Replay clarification submission",
                "POST",
                base + "/clarification",
                202,
                headers=continuation_headers,
                json=continuation,
            ).json()
            require(child["run_id"] == replay["run_id"], "Clarification replay was not idempotent")
            require(child["run_kind"] == "clarification", "Continuation has wrong run kind")
            audit.wait(child["run_id"], auth)
            summary["clarification_positive_http"] = True
        else:
            audit.call(
                "No pending clarification creates no child",
                "POST",
                base + "/clarification",
                409,
                headers={**auth, "Idempotency-Key": "not-pending-" + str(uuid4())},
                json={"clarification_id": "not-pending", "revision": 1, "answer": "QA"},
            )
            summary["clarification_positive_http"] = False
            summary["clarification_limit"] = (
                "Default demo answered; pending success is covered by isolated backend tests and a labelled UI fixture."
            )
        history = audit.call(
            "Read durable event history", "GET", base + "/events/history", headers=auth
        ).json()
        require(history["terminal"], "Completed segment is not terminal for SSE")
        cursor = history["items"][-1]["sequence"]
        sse = audit.call(
            "SSE replay after the final cursor closes",
            "GET",
            base + "/events",
            headers={**auth, "Last-Event-ID": str(cursor)},
        )
        require("data:" not in sse.text, "SSE replay duplicated already consumed events")
        metrics = audit.call(
            "Read per-attempt diagnostics", "GET", base + "/metrics", headers=auth
        ).json()
        require(
            all(call["actual_provider"] == "demo" for call in metrics["calls"]),
            "A non-demo provider was used",
        )
        audit.call("Read published sources", "GET", base + "/sources", headers=auth)
        audit.call("Read workflow steps", "GET", base + "/steps", headers=auth)
        for format_name in ("json", "markdown"):
            audit.call(
                "Export evidence result",
                "GET",
                base + "/export",
                headers=auth,
                params={"format": format_name},
            )
        for action in ("retry", "review"):
            child = audit.call(
                "Run " + action,
                "POST",
                base + "/" + action,
                202,
                headers={**auth, "Idempotency-Key": action + "-" + str(uuid4())},
            ).json()
            require(child["parent_run_id"] == identifier, "Parent link was lost")
            audit.wait(child["run_id"], auth)
            child_result = audit.call(
                "Read child evidence result",
                "GET",
                f"/api/v1/runs/{child['run_id']}/result",
                headers=auth,
            ).json()
            ResultView.model_validate(child_result)
        final = audit.call(
            "Parent result remains immutable", "GET", base + "/result", headers=auth
        ).json()
        require(final == result, "Review/retry mutated the parent result")
        summary.update(
            result_schema_version=result["result_schema_version"],
            answer_status=result["answer_status"],
            recognition_status=(result["recognition"] or {}).get("status"),
            evidence_count=len(result["evidence"]),
            region_count=len(result["regions"]),
            claims_count=len(result["claims"]),
            model_attempts=len(metrics["calls"]),
            parent_immutable=True,
        )
    finally:
        for auth in credentials:
            audit.call("Revoke temporary guest", "DELETE", "/api/v1/sessions/me", 204, headers=auth)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--expected-build")
    parser.add_argument(
        "--reference",
        type=Path,
        help="Optional baseline checkout; by default compare all current source routes without Git history",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".api-demo/reports/evidence-deployment.json"
    )
    args = parser.parse_args(argv)
    target = urlsplit(args.url)
    if (
        target.scheme != "http"
        or target.hostname not in {"127.0.0.1", "localhost"}
        or target.username
        or target.password
        or target.path not in {"", "/"}
        or target.query
        or target.fragment
    ):
        parser.error("Use an HTTP loopback origin without credentials")
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "paid_model_calls": False}
    with httpx.Client(base_url=args.url, timeout=35) as client:
        audit = Audit(client)
        try:
            result.update(verify(audit, args.reference, args.expected_build))
            result["passed"] = True
        except Exception as error:
            result["passed"] = False
            result["error_type"] = type(error).__name__
            if isinstance(error, AssertionError):
                result["error"] = str(error)
        result["http_cases"] = audit.cases
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "http_cases"}, ensure_ascii=True
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
