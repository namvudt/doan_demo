"""Send and read back a synthetic graph trace. Does not call an LLM provider."""

import argparse
import json
import os
import time
from uuid import uuid4

import requests
from dotenv import load_dotenv
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.graph import END, START, StateGraph

from core.observability import TraceSettings, trace_operation, tracing_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--content", action="store_true", help="Verify sanitized input/output content"
    )
    parser.add_argument("--summary-only", action="store_true", help="Verify content remains hidden")
    args = parser.parse_args()
    if args.content and args.summary_only:
        parser.error("Choose --content or --summary-only")
    load_dotenv()
    if args.content or args.summary_only:
        os.environ["LANGSMITH_CAPTURE_CONTENT"] = "true" if args.content else "false"
    settings = TraceSettings.from_env()
    if not settings.enabled:
        print("Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env first.")
        return 2
    run_id, graph_id = uuid4(), uuid4()
    marker = "SYNTHETIC_SMOKE_QUESTION"
    answer = "SYNTHETIC_SMOKE_ANSWER"
    secret = "synthetic-credential-" + uuid4().hex
    prior_secret = os.environ.get("LANGSMITH_SMOKE_SECRET")
    os.environ["LANGSMITH_SMOKE_SECRET"] = secret
    question = marker + " " + secret
    builder = StateGraph(dict)
    builder.add_node("smoke", lambda state: {"draft_response": answer})
    builder.add_edge(START, "smoke")
    builder.add_edge("smoke", END)
    headers = {"x-api-key": settings.api_key}
    if settings.workspace_id:
        headers["X-Tenant-Id"] = settings.workspace_id
    try:
        with trace_operation(
            "heritage-vqa.telemetry-smoke", run_id=run_id, inputs={"query": question}
        ) as span:
            builder.compile().invoke(
                {"query": question, "image_data": b"SYNTHETIC_BINARY_NOT_FOR_EXPORT"},
                config={"run_id": graph_id, "run_name": "telemetry.smoke.graph"},
            )
            span.outputs = {"status": "success", "final_response": answer}
        wait_for_all_tracers()
        tracing_client(settings).flush(timeout=10)
        # Ingestion is asynchronous. Retry only the expected brief 404 window.
        for identifier in (run_id, graph_id):
            for attempt in range(5):
                response = requests.get(
                    f"{settings.endpoint.rstrip('/')}/runs/{identifier}",
                    headers=headers,
                    timeout=5,
                )
                if response.status_code != 404 or attempt == 4:
                    break
                time.sleep(0.5)
            if response.status_code != 200:
                print({"trace_verified": False, "http_status": response.status_code})
                return 1
            payload = response.json()
            serialized = json.dumps(payload)
            if (
                secret in serialized
                or "SYNTHETIC_BINARY_NOT_FOR_EXPORT" in serialized
                or settings.api_key in serialized
            ):
                print({"trace_verified": False, "redaction_verified": False})
                return 1
            if settings.capture_content:
                if payload.get("inputs", {}).get("query") != marker + " [REDACTED]":
                    print({"trace_verified": False, "content_verified": False})
                    return 1
                expected_output = "final_response" if identifier == run_id else "draft_response"
                if payload.get("outputs", {}).get(expected_output) != answer:
                    print({"trace_verified": False, "output_verified": False})
                    return 1
            elif payload.get("inputs") or marker in serialized or answer in serialized:
                print({"trace_verified": False, "summary_mode_verified": False})
                return 1
        print(
            {
                "trace_verified": True,
                "redaction_verified": True,
                "content_verified": settings.capture_content,
                "project": settings.project,
                "run_id": str(run_id),
                "model_calls": 0,
            }
        )
        return 0
    except Exception as exc:
        # Do not print HTTP exception bodies/headers, which may contain credentials.
        print({"trace_verified": False, "error_type": type(exc).__name__})
        return 1
    finally:
        if prior_secret is None:
            os.environ.pop("LANGSMITH_SMOKE_SECRET", None)
        else:
            os.environ["LANGSMITH_SMOKE_SECRET"] = prior_secret


if __name__ == "__main__":
    raise SystemExit(main())
