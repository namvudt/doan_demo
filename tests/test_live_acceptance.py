import httpx
import pytest

from core.evaluation import validate_manifest
from scripts.live_acceptance import LiveAcceptance, latency_report, safe_origin, select_cases


def capabilities(mode="live", limit=12):
    return {
        "model_mode": mode,
        "model_configured": True,
        "missing_roles": [],
        "accuracy": {"enabled": True, "budget": {"max_llm_calls": limit}},
    }


def test_live_admission_refuses_demo_and_unadvertised_or_over_budget_without_mutations():
    requests = []
    current = [capabilities("demo")]

    def respond(request):
        requests.append(request.method)
        return httpx.Response(
            200,
            json=current[0] if request.url.path.endswith("capabilities") else {"status": "ready"},
        )

    with httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)
    ) as client:
        runner = LiveAcceptance(client, max_model_calls=12)
        with pytest.raises(ValueError, match="non-live"):
            runner.inspect([object()])
        current[0] = capabilities()
        with pytest.raises(ValueError, match="ceiling"):
            runner.inspect([object(), object()])
        current[0] = capabilities(limit=None)
        with pytest.raises(ValueError, match="advertise"):
            runner.inspect([object()])
        current[0] = capabilities()
        assert runner.inspect([object()])["model_mode"] == "live"
    assert set(requests) == {"GET"}


def test_live_origin_and_metrics_have_explicit_limits():
    assert safe_origin("http://127.0.0.1:8002")
    for origin in [
        "https://example.org",
        "http://user:password@localhost",
        "http://127.0.0.1/other",
    ]:
        with pytest.raises(ValueError, match="loopback"):
            safe_origin(origin)
    metrics = latency_report(
        [
            {"total_seconds": 3, "queue_wait_seconds": 0.3, "node_seconds": {"visual": 1.5}},
            {"total_seconds": 5, "queue_wait_seconds": 0.1, "node_seconds": {"visual": 2.5}},
        ]
    )
    assert metrics["total"]["p95_seconds"] == 5
    assert metrics["queue_wait"]["p50_seconds"] == 0.1
    assert metrics["nodes"]["visual"]["p95_seconds"] == 2.5


def test_acceptance_covers_distinct_image_families_before_more_questions():
    cases = validate_manifest(
        [
            {
                "case_id": name,
                "image_path": "unused",
                "image_family": family,
                "entity_group": family,
                "question": "Describe?",
                "slots": [{"slot_id": "s", "question": "Describe?", "kind": "visual"}],
            }
            for name, family in [("a1", "a"), ("a2", "a"), ("b1", "b"), ("c1", "c")]
        ],
        allow_draft=True,
    )
    assert [case.case_id for case in select_cases(cases, 3)] == ["a1", "b1", "c1"]
    assert [case.case_id for case in select_cases(cases, 1, ["b1"])] == ["b1"]
    with pytest.raises(ValueError, match="absent"):
        select_cases(cases, 1, ["missing"])
    with pytest.raises(ValueError, match="max-cases"):
        select_cases(cases, 1, ["a1", "b1"])


def test_genuine_clarification_counts_child_cost_and_latency_without_rebinding_gold():
    parent = {
        "run_id": "parent",
        "clarification": {"clarification_id": "pending", "revision": 1},
    }
    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(202, json={"run_id": "child"})
        if request.url.path == "/api/v1/runs/child":
            return httpx.Response(
                200,
                json={
                    "run_id": "child",
                    "parent_run_id": "parent",
                    "execution_status": "succeeded",
                    "created_at": "2026-11-16T00:00:00Z",
                    "started_at": "2026-11-16T00:00:00.2Z",
                },
            )
        if request.url.path.endswith("/metrics"):
            return httpx.Response(200, json={"duration": 3, "calls": [{}, {}]})
        if request.url.path == "/api/v1/runs/child/result":
            return httpx.Response(
                200,
                json={
                    "result_schema_version": 2,
                    "intermediate": {
                        "stages": {"visual": {"duration": 1.5, "status": "completed"}}
                    },
                },
            )
        assert request.url.path == "/api/v1/runs/parent/result"
        return httpx.Response(200, json=parent)

    with httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)
    ) as client:
        runner = LiveAcceptance(client, max_model_calls=4)
        runner.per_run_limit = 4
        child = runner.continue_pending(parent, "No further context", {})

    assert child["model_attempts"] == runner.actual_calls == 2
    assert runner.predictions == []
    assert runner.active_runs == set()
    assert runner.timings[0]["case_id"] is None
    assert runner.timings[0]["sample_kind"] == "clarification_child"
    assert runner.timings[0]["parent_run_id"] == "parent"
    report = latency_report(runner.timings)
    assert report["runs"] == 1
    assert report["total"]["p95_seconds"] == 3
    assert report["queue_wait"]["p50_seconds"] == pytest.approx(0.2)
    assert report["nodes"]["visual"]["p95_seconds"] == 1.5
    assert requests.count(("POST", "/api/v1/runs/parent/clarification")) == 2


def test_failed_clarification_keeps_cost_latency_and_only_safe_failure_fields():
    def respond(request):
        if request.method == "POST":
            return httpx.Response(202, json={"run_id": "child"})
        if request.url.path.endswith("/metrics"):
            return httpx.Response(
                200,
                json={
                    "duration": 1.7,
                    "calls": [
                        {
                            "status": "error",
                            "provider_status_code": 429,
                            "error_code": "provider_unavailable",
                            "retryable": True,
                            "provider_body": "private provider body",
                            "api_key": "private key",
                        }
                    ],
                },
            )
        assert request.url.path == "/api/v1/runs/child"
        return httpx.Response(
            200,
            json={
                "run_id": "child",
                "parent_run_id": "parent",
                "execution_status": "failed",
                "created_at": "2026-11-16T00:00:00Z",
                "started_at": "2026-11-16T00:00:00.2Z",
            },
        )

    with httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)
    ) as client:
        runner = LiveAcceptance(client, max_model_calls=4)
        runner.per_run_limit = 4
        parent = {
            "run_id": "parent",
            "clarification": {"clarification_id": "pending", "revision": 1},
        }
        with pytest.raises(ValueError, match="child failed"):
            runner.continue_pending(parent, "No further context", {})

    assert runner.actual_calls == 1
    assert runner.active_runs == set()
    assert runner.predictions == []
    assert runner.timings[0]["parent_run_id"] == "parent"
    assert latency_report(runner.timings)["total"]["p95_seconds"] == 1.7
    assert runner.failures[0]["attempts"] == [
        {
            "status": "error",
            "provider_status_code": 429,
            "error_code": "provider_unavailable",
            "retryable": True,
        }
    ]
