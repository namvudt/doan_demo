"""Safe ASGI access logs, bounded process metrics and shared database telemetry."""

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import case, func, select

from api.models import ModelAttempt, Run, WorkerHeartbeat
from core.model_errors import response_diagnostics
from core.observability import token_usage
from core.runtime_logging import log_context, log_event

BUCKETS = (0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 180, 600)
HELP = {
    "heritage_http_requests_total": "Completed HTTP requests in this API process.",
    "heritage_http_request_duration_seconds": "HTTP response duration including streaming in this API process.",
    "heritage_sse_active": "Open event streams in this API process.",
    "heritage_sse_events_total": "Run events sent by this API process.",
    "heritage_sse_connections_total": "Event streams opened in this API process.",
    "heritage_runs": "Stored runs by execution status in the shared database.",
    "heritage_workers_alive": "Workers with an unexpired heartbeat in the shared database.",
    "heritage_oldest_queued_seconds": "Age of the oldest queued run in the shared database.",
    "heritage_model_attempts": "Stored model attempts by current status in the shared database.",
    "heritage_model_tokens_observed": "Known token counts in the shared database; excludes unknown usage.",
    "heritage_model_attempts_unknown_usage": "Stored model attempts with unknown total token usage.",
    "heritage_worker_lost_runs": "Stored runs that lost their worker lease.",
}


def prometheus_text(lines):
    result = []
    for line in lines:
        if line.startswith("# TYPE "):
            name = line.split()[2]
            result.append(f"# HELP {name} {HELP[name]}")
        result.append(line)
    return "\n".join(result) + "\n"


class ProcessMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = defaultdict(lambda: [0, 0.0, *[0 for _ in BUCKETS]])
        self.sse_active = 0
        self.sse_events = 0
        self.sse_connections = 0

    def request(self, method, route, status, duration):
        with self.lock:
            entry = self.requests[(method, route, str(status))]
            entry[0] += 1
            entry[1] += duration
            for i, bound in enumerate(BUCKETS):
                entry[2 + i] += duration <= bound

    def stream(self, active=0, events=0, connections=0):
        with self.lock:
            self.sse_active += active
            self.sse_events += events
            self.sse_connections += connections

    def render(self):
        with self.lock:
            lines = [
                "# TYPE heritage_http_requests_total counter",
                "# TYPE heritage_http_request_duration_seconds histogram",
            ]
            for (method, route, status), (count, total, *buckets) in sorted(self.requests.items()):
                labels = f"method={json.dumps(method)},route={json.dumps(route)},status={json.dumps(status)}"
                lines.extend(
                    [
                        f"heritage_http_requests_total{{{labels}}} {count}",
                        f"heritage_http_request_duration_seconds_sum{{{labels}}} {total}",
                        f"heritage_http_request_duration_seconds_count{{{labels}}} {count}",
                    ]
                )
                for bound, value in zip(BUCKETS, buckets):
                    lines.append(
                        f'heritage_http_request_duration_seconds_bucket{{{labels},le="{bound}"}} {value}'
                    )
                lines.append(
                    f'heritage_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {count}'
                )
            lines.extend(
                [
                    "# TYPE heritage_sse_active gauge",
                    f"heritage_sse_active {self.sse_active}",
                    "# TYPE heritage_sse_events_total counter",
                    f"heritage_sse_events_total {self.sse_events}",
                    "# TYPE heritage_sse_connections_total counter",
                    f"heritage_sse_connections_total {self.sse_connections}",
                ]
            )
        return lines


class RequestEnvelopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        settings = scope["app"].state.settings
        maximum = settings.max_upload_bytes + 1_000_000
        started, received, response_started = time.monotonic(), 0, False
        status, reason = 500, "completed"
        headers = dict(scope.get("headers", []))

        async def reject(code, name, message):
            nonlocal status
            status = code
            body = json.dumps(
                {"error": {"code": name, "message": message, "request_id": request_id}}
            ).encode()
            await safe_send(
                {
                    "type": "http.response.start",
                    "status": code,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await safe_send({"type": "http.response.body", "body": body})

        async def safe_receive():
            nonlocal received, reason
            message = await receive()
            if message["type"] == "http.disconnect":
                reason = "disconnected"
            received += len(message.get("body", b""))
            if received > maximum:
                state["body_too_large"] = True
                raise HTTPException(status_code=413)
            return message

        async def safe_send(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                response_headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in {b"x-request-id", b"x-content-type-options"}
                ]
                response_headers.extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                if not any(k.lower() == b"cache-control" for k, _ in response_headers):
                    response_headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": response_headers}
            await send(message)

        with log_context(request_id=request_id):
            try:
                try:
                    size = int(headers.get(b"content-length", b"0"))
                    if size < 0:
                        raise ValueError
                except ValueError:
                    return await reject(400, "invalid_content_length", "Invalid Content-Length")
                if size > maximum:
                    return await reject(413, "body_too_large", "Request body exceeds upload limit")
                await self.app(scope, safe_receive, safe_send)
            except asyncio.CancelledError:
                reason = "disconnected"
                raise
            except Exception as exc:
                reason = "error"
                log_event("http.error", level=logging.ERROR, error=exc)
                if response_started:
                    raise
                await reject(
                    500, "internal_error", "Internal error; use X-Request-ID for investigation"
                )
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                run_id = state.get("run_id")
                if not run_id and scope.get("path_params", {}).get("run_id"):
                    try:
                        run_id = str(UUID(str(scope["path_params"]["run_id"])))
                    except ValueError:
                        pass
                method = (
                    scope["method"]
                    if scope["method"]
                    in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                    else "OTHER"
                )
                duration = time.monotonic() - started
                scope["app"].state.process_metrics.request(method, route, status, duration)
                log_event(
                    "http.completed",
                    method=method,
                    route=route,
                    status_code=status,
                    duration_ms=round(duration * 1000, 3),
                    reason=reason,
                    run_id=run_id,
                    trace_id=run_id,
                )


def attempt_record(row):
    return {
        **(row.diagnostics or {}),
        **{
            key: getattr(row, key)
            for key in (
                "attempt",
                "agent_role",
                "actual_provider",
                "model_used",
                "status",
                "retry",
                "fallback_used",
                "duration",
                "error_type",
                "usage",
                "started_at",
                "finished_at",
            )
        },
    }


def persist_attempt(db, run_id, record):
    # Called synchronously before a billable request and after each completed attempt.
    with db.session() as session:
        row = session.get(ModelAttempt, (run_id, record["attempt"]))
        if row is None:
            row = ModelAttempt(run_id=run_id, attempt=record["attempt"])
            session.add(row)
        for name, default in (
            ("agent_role", "general"),
            ("actual_provider", "unknown"),
            ("model_used", "unknown"),
            ("status", "running"),
            ("retry", 0),
            ("fallback_used", False),
        ):
            setattr(row, name, record.get(name, default))
        row.started_at = record.get("started_at") or row.started_at or time.time()
        for name in ("duration", "error_type", "finished_at"):
            if name in record:
                setattr(row, name, record[name])
        if record.get("usage") is not None:
            # Only numeric token counts; SDK response dictionaries are never stored here.
            row.usage = token_usage(record["usage"], record.get("actual_provider"))
        row.diagnostics = {**(row.diagnostics or {}), **response_diagnostics(record)}


def database_metrics(rt):
    lines = [
        "# TYPE heritage_runs gauge",
        "# TYPE heritage_workers_alive gauge",
        "# TYPE heritage_oldest_queued_seconds gauge",
        "# TYPE heritage_model_attempts gauge",
        "# TYPE heritage_model_tokens_observed gauge",
        "# TYPE heritage_model_attempts_unknown_usage gauge",
    ]
    now = time.time()
    with rt.db.session() as session:
        statuses = dict(
            session.execute(
                select(Run.execution_status, func.count()).group_by(Run.execution_status)
            ).all()
        )
        for status in ("queued", "running", "cancel_requested", "succeeded", "failed", "cancelled"):
            lines.append(f'heritage_runs{{status="{status}"}} {statuses.get(status, 0)}')
        oldest = session.scalar(
            select(func.min(Run.created_at)).where(Run.execution_status == "queued")
        )
        alive = session.scalar(
            select(func.count())
            .select_from(WorkerHeartbeat)
            .where(WorkerHeartbeat.heartbeat_at >= now - rt.settings.lease_seconds)
        )
        lines.extend(
            [
                f"heritage_workers_alive {alive}",
                f"heritage_oldest_queued_seconds {max(0, now - oldest) if oldest else 0}",
            ]
        )
        attempts = dict(
            session.execute(
                select(ModelAttempt.status, func.count()).group_by(ModelAttempt.status)
            ).all()
        )
        for status in ("running", "success", "error", "interrupted", "cancelled"):
            lines.append(f'heritage_model_attempts{{status="{status}"}} {attempts.get(status, 0)}')
        # One SQL scan for all token totals and unknown usage; bounded API memory.
        names = ("input_tokens", "output_tokens", "total_tokens")
        unknown = ModelAttempt.usage.is_(None) | ModelAttempt.usage[
            "total_tokens"
        ].as_integer().is_(None)
        totals = session.execute(
            select(
                *[func.sum(ModelAttempt.usage[name].as_integer()) for name in names],
                func.sum(case((unknown, 1), else_=0)),
            )
        ).one()
        for name, value in zip(names, totals[:3]):
            lines.append(f'heritage_model_tokens_observed{{kind="{name}"}} {value or 0}')
        missing = totals[3] or 0
        lines.append(f"heritage_model_attempts_unknown_usage {missing}")
        lost = session.scalar(
            select(func.count()).select_from(Run).where(Run.error_type == "WorkerLost")
        )
        lines.extend(
            ["# TYPE heritage_worker_lost_runs gauge", f"heritage_worker_lost_runs {lost}"]
        )
    return lines
