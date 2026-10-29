"""Send and read back a synthetic graph trace. Does not call an LLM provider."""

import json
import time
from uuid import uuid4

import requests
from dotenv import load_dotenv
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.graph import END, START, StateGraph

from core.observability import TraceSettings, trace_operation, tracing_client


def main():
    load_dotenv()
    settings = TraceSettings.from_env()
    if not settings.enabled:
        print("Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env first.")
        return 2
    run_id, graph_id = uuid4(), uuid4()
    marker = "PRIVATE_SYNTHETIC_SMOKE_CONTENT"
    builder = StateGraph(dict)
    builder.add_node("smoke", lambda state: {"draft_response": marker})
    builder.add_edge(START, "smoke")
    builder.add_edge("smoke", END)
    headers = {"x-api-key": settings.api_key}
    if settings.workspace_id:
        headers["X-Tenant-Id"] = settings.workspace_id
    try:
        with trace_operation("heritage-vqa.telemetry-smoke", run_id=run_id) as span:
            builder.compile().invoke(
                {"query": marker, "image_data": marker.encode()},
                config={"run_id": graph_id, "run_name": "telemetry.smoke.graph"},
            )
            span.outputs = {"status": "success"}
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
            if marker in json.dumps(payload) or payload.get("inputs"):
                print({"trace_verified": False, "redaction_verified": False})
                return 1
        print(
            {
                "trace_verified": True,
                "redaction_verified": True,
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


if __name__ == "__main__":
    raise SystemExit(main())
