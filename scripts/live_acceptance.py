"""Bounded live HTTP acceptance and latency report; quality still needs human review."""

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import httpx

from core.evaluation import digest, validate_manifest
from core.retrieval_cache import percentiles
from scripts.evaluate import ROOT, prepare, read

SETTLED = {"succeeded", "failed", "cancelled", "awaiting_input"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_origin(value):
    parts = urlsplit(value)
    require(
        parts.scheme == "http"
        and parts.hostname in {"127.0.0.1", "localhost"}
        and not parts.username
        and not parts.password
        and parts.path in {"", "/"}
        and not parts.query
        and not parts.fragment,
        "Acceptance requires an HTTP loopback origin without credentials",
    )
    return value


def select_cases(cases, limit, case_ids=None):
    """First cover distinct image families; never infer labels from file names."""
    if case_ids:
        wanted = set(case_ids)
        require(
            wanted <= {case.case_id for case in cases}, "Requested case ID is absent from manifest"
        )
        require(len(wanted) <= limit, "Requested case IDs exceed max-cases")
        cases = [case for case in cases if case.case_id in wanted]
    picked, seen = [], set()
    for case in cases:
        if case.image_family not in seen:
            picked.append(case)
            seen.add(case.image_family)
        if len(picked) == limit:
            return picked
    return picked + [case for case in cases if case not in picked][: limit - len(picked)]


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() if value else None


def latency_report(records):
    nodes = defaultdict(list)
    for record in records:
        for node, seconds in record.get("node_seconds", {}).items():
            nodes[node].append(seconds)
    return {
        "runs": len(records),
        "total": percentiles(record.get("total_seconds") for record in records),
        "queue_wait": percentiles(record.get("queue_wait_seconds") for record in records),
        "nodes": {name: percentiles(values) for name, values in sorted(nodes.items())},
        "interpretation": "Small acceptance sample; these percentiles are not a production benchmark.",
    }


class LiveAcceptance:
    def __init__(self, client, *, max_model_calls, timeout_seconds=240, poll_seconds=0.5):
        self.client = client
        self.max_model_calls = max_model_calls
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self.actual_calls = 0
        self.attempts_by_run = {}
        self.predictions, self.timings, self.active_runs = [], [], set()
        self.failures = []
        self.per_run_limit = None

    def record_attempts(self, identifier, calls):
        self.attempts_by_run[identifier] = len(calls)
        self.actual_calls = sum(self.attempts_by_run.values())
        require(len(calls) <= self.per_run_limit, "Server exceeded advertised per-run model limit")
        require(self.actual_calls <= self.max_model_calls, "Observed model-call ceiling exceeded")

    def record_failure(self, case_id, run, metrics, *, parent_run_id=None):
        """Keep failed paid work observable without copying provider exception bodies."""
        self.record_timing(case_id, run, metrics, {}, parent_run_id=parent_run_id)
        self.failures.append(
            {
                "run_id": run["run_id"],
                "parent_run_id": parent_run_id,
                "case_id": case_id,
                "execution_status": run["execution_status"],
                "attempts": [
                    {
                        key: call[key]
                        for key in (
                            "status",
                            "agent_role",
                            "provider_status_code",
                            "error_code",
                            "error_category",
                            "retryable",
                        )
                        if key in call
                    }
                    for call in metrics["calls"]
                ],
            }
        )

    def record_timing(self, case_id, run, metrics, result, *, parent_run_id=None):
        stages = (result.get("intermediate") or {}).get("stages", {})
        timing = {
            "case_id": case_id,
            "run_id": run["run_id"],
            "parent_run_id": parent_run_id,
            "sample_kind": "clarification_child" if parent_run_id else "manifest_case",
            "total_seconds": metrics.get("duration"),
            "queue_wait_seconds": max(
                0, timestamp(run["started_at"]) - timestamp(run["created_at"])
            )
            if run.get("started_at")
            else None,
            "node_seconds": {
                name: stage["duration"]
                for name, stage in stages.items()
                if stage.get("duration") is not None and stage.get("status") != "skipped"
            },
            "model_attempts": len(metrics["calls"]),
            "shared_retrieval_cache_hits": sum(
                bool(call.get("shared_cache_hit")) for call in result.get("tool_calls", [])
            ),
            "execution_status": run["execution_status"],
            "answer_status": result.get("answer_status"),
            "recognition_status": (result.get("recognition") or {}).get("status"),
        }
        self.timings.append(timing)
        return timing

    def response(self, method, path, expected=200, **kwargs):
        response = self.client.request(method, path, **kwargs)
        require(
            response.status_code == expected,
            f"HTTP {method} {path.split('?')[0]} returned {response.status_code}",
        )
        return response

    def inspect(self, cases):
        response = self.response("GET", "/api/v1/capabilities")
        self.backend_build = response.headers.get("X-Backend-Build")
        capabilities = response.json()
        require(
            capabilities["model_mode"] == "live", "Refusing non-live backend for live acceptance"
        )
        require(capabilities.get("model_configured"), "Server models are not configured")
        require(not capabilities.get("missing_roles"), "Server is missing required roles")
        require(capabilities.get("accuracy", {}).get("enabled"), "Evidence profile is not enabled")
        budget = capabilities["accuracy"].get("budget", {})
        limit = budget.get("max_llm_calls")
        require(
            type(limit) is int and 1 <= limit <= 100,
            "Server must advertise enforced per-run max_llm_calls",
        )
        self.per_run_limit = limit
        require(
            len(cases) * limit <= self.max_model_calls,
            "Requested cases exceed the admitted model-call ceiling",
        )
        self.response("GET", "/health/ready")
        return capabilities

    def wait(self, identifier, auth):
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            run = self.response("GET", f"/api/v1/runs/{identifier}", headers=auth).json()
            if run["execution_status"] in SETTLED:
                self.active_runs.discard(identifier)
                return run
            time.sleep(self.poll_seconds)
        raise ValueError("Run exceeded acceptance timeout; cancellation will be requested")

    def execute(self, case, auth):
        require(
            self.actual_calls + self.per_run_limit <= self.max_model_calls,
            "Model-call ceiling reached before next run",
        )
        path = Path(case.image_path)
        content = (path if path.is_absolute() else ROOT / path).read_bytes()
        asset = self.response(
            "POST",
            "/api/v1/assets",
            201,
            headers=auth,
            files={"file": ("acceptance-image.jpg", content, "application/octet-stream")},
        ).json()
        body = {"asset_id": asset["asset_id"], "question": case.question, "audience": "tourist"}
        key = "live-acceptance-" + str(uuid4())
        created = self.response(
            "POST", "/api/v1/runs", 202, headers={**auth, "Idempotency-Key": key}, json=body
        ).json()
        identifier = created["run_id"]
        self.active_runs.add(identifier)
        self.attempts_by_run[identifier] = 0
        replay = self.response(
            "POST", "/api/v1/runs", 202, headers={**auth, "Idempotency-Key": key}, json=body
        ).json()
        require(replay["run_id"] == identifier, "Run replay lost idempotency")
        run = self.wait(identifier, auth)
        metrics = self.response("GET", f"/api/v1/runs/{identifier}/metrics", headers=auth).json()
        self.record_attempts(identifier, metrics["calls"])
        if run["execution_status"] in {"failed", "cancelled"}:
            self.record_failure(case.case_id, run, metrics)
        require(
            run["execution_status"] not in {"failed", "cancelled"},
            "Live workflow failed or was cancelled",
        )
        result = self.response(
            "GET", f"/api/v1/runs/{identifier}/result?include_intermediate=true", headers=auth
        ).json()
        require(result.get("result_schema_version") == 2, "Live result is not evidence schema2")
        evidence = self.response("GET", f"/api/v1/runs/{identifier}/evidence", headers=auth).json()
        require(evidence["run_id"] == identifier, "Evidence identity mismatch")
        events = self.response(
            "GET", f"/api/v1/runs/{identifier}/events/history?limit=500", headers=auth
        ).json()
        last = events["items"][-1]["sequence"] if events["items"] else 0
        replay_events = self.response(
            "GET", f"/api/v1/runs/{identifier}/events/history?after={last}", headers=auth
        ).json()
        require(not replay_events["items"], "Completed event cursor replay duplicated events")
        if last:
            resumed = self.response(
                "GET",
                f"/api/v1/runs/{identifier}/events?after={max(0, last - 1)}",
                headers={**auth, "Last-Event-ID": str(max(0, last - 1))},
            )
            require(
                "text/event-stream" in resumed.headers.get("content-type", "")
                and f"id: {last}" in resumed.text,
                "SSE reconnection did not replay the final persisted event",
            )
        timing = self.record_timing(case.case_id, run, metrics, result)
        prediction = {
            "case_id": case.case_id,
            "case_hash": digest(case.model_dump(mode="json")),
            "image_hash": hashlib.sha256(content).hexdigest(),
            "model_mode": "live",
            "result": result,
        }
        self.predictions.append(prediction)
        return result, timing

    def continue_pending(self, parent, answer, auth):
        pending = parent.get("clarification")
        if not pending or not answer:
            return None
        require(
            self.actual_calls + self.per_run_limit <= self.max_model_calls,
            "Insufficient ceiling for clarification child",
        )
        body = {
            "clarification_id": pending["clarification_id"],
            "revision": pending["revision"],
            "answer": answer,
        }
        key = "live-clarification-" + str(uuid4())
        path = f"/api/v1/runs/{parent['run_id']}/clarification"
        child = self.response(
            "POST", path, 202, headers={**auth, "Idempotency-Key": key}, json=body
        ).json()
        self.active_runs.add(child["run_id"])
        self.attempts_by_run[child["run_id"]] = 0
        replay = self.response(
            "POST", path, 202, headers={**auth, "Idempotency-Key": key}, json=body
        ).json()
        require(child["run_id"] == replay["run_id"], "Clarification idempotency failed")
        final = self.wait(child["run_id"], auth)
        metrics = self.response(
            "GET", f"/api/v1/runs/{child['run_id']}/metrics", headers=auth
        ).json()
        calls = len(metrics["calls"])
        self.record_attempts(child["run_id"], metrics["calls"])
        if final["execution_status"] in {"failed", "cancelled"}:
            self.record_failure(None, final, metrics, parent_run_id=parent["run_id"])
        require(
            final["execution_status"] not in {"failed", "cancelled"}, "Clarification child failed"
        )
        require(final["parent_run_id"] == parent["run_id"], "Clarification lineage mismatch")
        result = self.response(
            "GET",
            f"/api/v1/runs/{child['run_id']}/result?include_intermediate=true",
            headers=auth,
        ).json()
        require(
            result.get("result_schema_version") == 2, "Clarification result is not evidence schema2"
        )
        self.record_timing(None, final, metrics, result, parent_run_id=parent["run_id"])
        old = self.response(
            "GET", f"/api/v1/runs/{parent['run_id']}/result?include_intermediate=true", headers=auth
        ).json()
        require(old == parent, "Clarification mutated the parent result")
        return {
            "run_id": child["run_id"],
            "model_attempts": calls,
            "execution_status": final["execution_status"],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly authorize bounded configured server model calls",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--allow-draft", action="store_true", help="Smoke only; never produces accuracy scores"
    )
    parser.add_argument("--max-cases", type=int, default=2)
    parser.add_argument(
        "--case-id",
        action="append",
        help="Select an existing case without repeating earlier paid cases",
    )
    parser.add_argument("--max-model-calls", type=int, default=24)
    parser.add_argument("--max-clarifications", type=int, default=1)
    parser.add_argument(
        "--clarification-answer",
        help="Optional explicit unverified answer; used only if a real pending question arises",
    )
    parser.add_argument("--token-env", default="HERITAGE_ACCEPTANCE_TOKEN")
    parser.add_argument("--bootstrap-env", default="API_BOOTSTRAP_TOKEN")
    parser.add_argument("--output", type=Path, default=ROOT / ".api-demo/reports/live-acceptance")
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("Explicit --live is required before any server mutation")
    try:
        safe_origin(args.url)
        require(1 <= args.max_cases <= 3, "max-cases must be between1 and3")
        require(1 <= args.max_model_calls <= 100, "max-model-calls must be between1 and100")
        require(0 <= args.max_clarifications <= 2, "max-clarifications must be between0 and2")
        raw = (
            read(args.manifest)
            if args.manifest
            else prepare(read(ROOT / "config/evaluation/hanoi-pilot.json"))
        )
        cases = select_cases(
            validate_manifest(raw, allow_draft=args.allow_draft), args.max_cases, args.case_id
        )
        require(bool(cases), "No acceptance cases")
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Choose an empty output directory to preserve prior paid predictions/reviews")
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "quality_status": "pending_human_review",
        "passed": False,
        "live_requested": True,
    }
    with httpx.Client(base_url=args.url, timeout=30) as client:
        runner = LiveAcceptance(client, max_model_calls=args.max_model_calls)
        auth, created_session = {}, False
        try:
            capabilities = runner.inspect(cases)
            token = os.getenv(args.token_env, "")
            if not token:
                bootstrap = os.getenv(args.bootstrap_env, "")
                require(
                    not capabilities.get("session_bootstrap_required") or bool(bootstrap),
                    "Server requires an operator-issued session or bootstrap token",
                )
                session = runner.response(
                    "POST",
                    "/api/v1/sessions",
                    201,
                    headers={"X-Bootstrap-Token": bootstrap} if bootstrap else {},
                    json={"label": "bounded live acceptance"},
                ).json()
                token, created_session = session["access_token"], True
            auth = {"Authorization": "Bearer " + token}
            summary["workflow_profiles"] = capabilities["profiles"]
            summary["backend_build"] = runner.backend_build
            summary["case_ids"] = [case.case_id for case in cases]
            summary["server_per_run_call_ceiling"] = runner.per_run_limit
            summary["model_call_ceiling"] = args.max_model_calls
            continuations = []
            for case in cases:
                result, _ = runner.execute(case, auth)
                if (
                    result.get("clarification")
                    and args.clarification_answer
                    and len(continuations) < args.max_clarifications
                ):
                    continuation = runner.continue_pending(result, args.clarification_answer, auth)
                    if continuation:
                        continuations.append(continuation)
                (args.output / "predictions.json").write_text(
                    json.dumps(runner.predictions, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            summary.update(passed=True, clarification_children=continuations)
        except Exception as error:
            summary["error_type"] = type(error).__name__
            if isinstance(error, ValueError):
                summary["error"] = str(error)
        finally:
            for identifier in runner.active_runs:
                try:
                    client.post(f"/api/v1/runs/{identifier}/cancel", headers=auth)
                except httpx.HTTPError:
                    pass
            for identifier in runner.attempts_by_run:
                try:
                    metrics = client.get(f"/api/v1/runs/{identifier}/metrics", headers=auth)
                    if metrics.status_code == 200:
                        runner.record_attempts(identifier, metrics.json()["calls"])
                    else:
                        summary["attempt_count_complete"] = False
                except (httpx.HTTPError, KeyError):
                    summary["attempt_count_complete"] = False
                except ValueError:
                    summary.update(
                        passed=False,
                        error_type="ModelBudgetViolation",
                        attempt_count_complete=False,
                    )
            if created_session:
                try:
                    client.delete("/api/v1/sessions/me", headers=auth)
                except httpx.HTTPError:
                    pass
        summary.update(
            model_attempts=runner.actual_calls,
            attempt_count_complete=summary.get("attempt_count_complete", not runner.active_runs),
            latency=latency_report(runner.timings),
            cases=runner.timings,
            failures=runner.failures,
            pending_clarification_seen=any(
                item["execution_status"] == "awaiting_input" for item in runner.timings
            ),
            note="Results are unreviewed predictions. Test pass does not certify recognition or historical correctness.",
        )
        (args.output / "predictions.json").write_text(
            json.dumps(runner.predictions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
