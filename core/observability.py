"""Private, optional LangSmith telemetry shared by graph and direct SDK calls.

Only operational summaries leave the process. The client boundary also strips
native LangGraph state, attachments, exception messages and serialized objects.
"""

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache

from langsmith import Client, trace, tracing_context
from langsmith.run_helpers import get_current_run_tree, get_tracing_context

from core.runtime_logging import context_fields, log_event

METADATA_KEYS = {
    "app_run_id",
    "request_id",
    "worker_id",
    "workflow_version",
    "config_hash",
    "audience",
    "benchmark",
    "agent_role",
    "actual_provider",
    "ls_provider",
    "ls_model_name",
    "ls_model_type",
    "attempt",
    "retry",
    "fallback_used",
    "result_status",
    "error_count",
    "node_status",
    "error_type",
    "langgraph_node",
    "langgraph_step",
}
SUMMARY_KEYS = {
    "status",
    "call_count",
    "error_count",
    "source_count",
    "duration",
    "error_type",
}


def safe_metadata(value):
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key in METADATA_KEYS and isinstance(item, (str, bool, int, float))
    }


def safe_outputs(value):
    if not isinstance(value, dict):
        return {}
    result = {
        key: item
        for key, item in value.items()
        if key in SUMMARY_KEYS and isinstance(item, (str, bool, int, float))
    }
    usage = value.get("usage_metadata")
    if isinstance(usage, dict):
        counts = {
            key: count
            for key, count in usage.items()
            if key in {"input_tokens", "output_tokens", "total_tokens"}
            and type(count) is int
            and count >= 0
        }
        if counts:
            result["usage_metadata"] = counts
    return result


def _private_payload(payload):
    payload = dict(payload)
    if "inputs" in payload:
        payload["inputs"] = {}
    if "outputs" in payload:
        payload["outputs"] = safe_outputs(payload["outputs"])
    for name in ("events", "attachments", "serialized"):
        payload.pop(name, None)
    extra = payload.get("extra") or {}
    payload["extra"] = {"metadata": safe_metadata(extra.get("metadata"))}
    if payload.get("error"):
        payload["error"] = "Operation failed (details hidden)"
    payload["dangerously_allow_filesystem"] = False
    return payload


class PrivateTracingClient(Client):
    """Redact before the SDK queues/serializes a native or custom run."""

    def create_run(self, name, inputs, run_type, **kwargs):
        try:
            return super().create_run(name, {}, run_type, **_private_payload(kwargs))
        except Exception:
            log_event("trace.enqueue_failed", level=logging.WARNING)

    def update_run(self, run_id, **kwargs):
        try:
            return super().update_run(run_id, **_private_payload(kwargs))
        except Exception:
            log_event("trace.update_failed", level=logging.WARNING)


@dataclass(frozen=True)
class TraceSettings:
    enabled: bool
    api_key: str = field(default="", repr=False)
    endpoint: str = "https://api.smith.langchain.com"
    project: str = "heritage-vqa-dev"
    workspace_id: str | None = None

    @classmethod
    def from_env(cls):
        key = os.getenv("LANGSMITH_API_KEY", "").strip()
        return cls(
            enabled=os.getenv("LANGSMITH_TRACING", "false").lower() == "true" and bool(key),
            api_key=key,
            endpoint=os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").strip(),
            project=os.getenv("LANGSMITH_PROJECT", "heritage-vqa-dev").strip(),
            workspace_id=os.getenv("LANGSMITH_WORKSPACE_ID") or None,
        )


@lru_cache(maxsize=4)
def tracing_client(settings):
    return PrivateTracingClient(
        api_key=settings.api_key,
        api_url=settings.endpoint,
        workspace_id=settings.workspace_id,
        timeout_ms=3000,
        omit_traced_runtime_info=True,
        hide_inputs=True,
        hide_outputs=safe_outputs,
        hide_metadata=safe_metadata,
    )


@dataclass
class Span:
    outputs: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    error: str | None = None


@contextmanager
def trace_operation(name, run_type="chain", *, metadata=None, run_id=None):
    """Never let a telemetry failure swallow or replace an application exception."""
    settings = TraceSettings.from_env()
    context = get_tracing_context()
    client = context.get("client")
    enabled = settings.enabled and context.get("enabled") is not False
    project = context.get("project_name") or settings.project
    if enabled and not isinstance(client, PrivateTracingClient):
        try:
            client = tracing_client(settings)
        except Exception:
            enabled = False
            log_event("trace.initialization_failed", level=logging.WARNING)
    span = Span()
    with tracing_context(enabled=enabled, client=client, project_name=project):
        if not enabled:
            yield span
            return
        try:
            manager = trace(
                name,
                run_type=run_type,
                inputs={},
                client=client,
                project_name=project,
                metadata=safe_metadata({**context_fields(), **(metadata or {})}),
                run_id=run_id,
                tags=["heritage-vqa"],
            )
            run = manager.__enter__()
        except Exception:
            log_event("trace.span_start_failed", level=logging.WARNING)
            with tracing_context(enabled=False):
                yield span
            return
        try:
            yield span
        except BaseException as exc:
            span.error = type(exc).__name__
            raise
        finally:
            try:
                run.add_metadata(safe_metadata(span.metadata))
                run.end(outputs=safe_outputs(span.outputs), error=span.error)
            except Exception:
                log_event("trace.span_end_failed", level=logging.WARNING)
            finally:
                # Do not pass raw exceptions/tracebacks to the tracing SDK.
                try:
                    manager.__exit__(None, None, None)
                except Exception:
                    log_event("trace.cleanup_failed", level=logging.WARNING)
                if context.get("parent") is None:
                    try:
                        client.flush(timeout=1)
                    except Exception:
                        log_event("trace.flush_failed", level=logging.WARNING)


def record_node_outcome(status, error_type=None):
    """Caught node failures must remain visible as failures in the trace."""
    run = get_current_run_tree()
    if run is not None:
        try:
            run.add_metadata(
                {"node_status": status, **({"error_type": error_type} if error_type else {})}
            )
            if error_type:
                run.error = error_type
        except Exception:
            log_event("trace.annotation_failed", level=logging.WARNING)


def token_usage(usage, provider):
    if not isinstance(usage, dict):
        return {}
    if any(key in usage for key in ("input_tokens", "output_tokens")):
        return safe_outputs({"usage_metadata": usage}).get("usage_metadata", {})
    if provider == "gemini":
        input_tokens = usage.get("prompt_token_count")
        output_tokens = usage.get("candidates_token_count")
        thoughts = usage.get("thoughts_token_count")
        if type(output_tokens) is int and type(thoughts) is int:
            output_tokens += thoughts
    else:
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_token_count" if provider == "gemini" else "total_tokens")
    return safe_outputs(
        {
            "usage_metadata": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
        }
    ).get("usage_metadata", {})
