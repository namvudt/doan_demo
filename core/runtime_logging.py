"""Operational logs: bounded metadata only, never arbitrary messages or exception text."""

import json
import logging
import math
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_context = ContextVar("operational_log_context", default={})
_lock = threading.Lock()
FIELDS = {
    "request_id",
    "run_id",
    "trace_id",
    "worker_id",
    "parent_run_id",
    "method",
    "route",
    "status_code",
    "duration_ms",
    "node",
    "status",
    "error_type",
    "error_code",
    "sequence",
    "after",
    "events_sent",
    "reason",
    "agent_role",
    "actual_provider",
    "model_used",
    "attempt",
    "retry",
    "fallback_used",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "queue_wait_ms",
    "model_mode",
    "process_role",
    "stage_count",
    "frames",
}
IDENTIFIERS = {"request_id", "run_id", "trace_id", "worker_id", "parent_run_id"}


def safe_fields(values):
    result = {}
    for key, value in values.items():
        if key not in FIELDS or value is None:
            continue
        if key in IDENTIFIERS:
            if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9-]{36}", value):
                result[key] = value
        elif isinstance(value, (bool, int, float)):
            if not isinstance(value, float) or math.isfinite(value):
                result[key] = value
        elif isinstance(value, str) and len(value) <= 160:
            # Routes originate from route templates, never raw paths or query strings.
            if re.fullmatch(r"[a-zA-Z0-9_./{}:* -]+", value):
                result[key] = value
        elif key == "frames" and isinstance(value, list):
            result[key] = value[:12]
    return result


@contextmanager
def log_context(**fields):
    token = _context.set({**_context.get(), **safe_fields(fields)})
    try:
        yield
    finally:
        _context.reset(token)


def context_fields():
    return dict(_context.get())


def error_fields(error):
    # Frame locations only: no source lines, locals, exception values, or full paths.
    frames = []
    tb = error.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append(
            {"file": Path(code.co_filename).name, "function": code.co_name, "line": tb.tb_lineno}
        )
        tb = tb.tb_next
    return {"error_type": type(error).__name__, "frames": frames[-12:]}


def log_event(name, *, level=logging.INFO, error=None, **fields):
    values = {**_context.get(), **fields}
    if error is not None:
        values.update(error_fields(error))
    logging.getLogger("heritage").log(
        level, name, extra={"operational_event": name, "operational_fields": safe_fields(values)}
    )


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = getattr(record, "operational_event", "external.log")
        if not re.fullmatch(r"[a-z][a-z0-9_.]{0,79}", event):
            event = "external.log"
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event": event,
            "logger": record.name if re.fullmatch(r"[\w.]{1,100}", record.name) else "external",
            "pid": record.process,
            **safe_fields(getattr(record, "operational_fields", _context.get())),
        }
        if record.exc_info and record.exc_info[1]:
            payload.update(error_fields(record.exc_info[1]))
        # Deliberately never call record.getMessage(): third-party messages may carry URLs/keys.
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def configure_logging(settings, role="api"):
    """Idempotent per process. Keep testing/caller handlers, replace only owned handlers."""
    with _lock:
        root = logging.getLogger()
        for handler in list(root.handlers):
            if getattr(handler, "heritage_handler", False):
                root.removeHandler(handler)
                handler.close()
        formatter = JsonFormatter()
        handlers = [logging.StreamHandler(sys.stderr)]
        if settings.log_dir is not None:
            settings.log_dir.mkdir(parents=True, exist_ok=True)
            # Never rotate a file shared by multiple worker processes.
            target = settings.log_dir / f"{role}-{os.getpid()}.jsonl"
            handlers.append(
                RotatingFileHandler(
                    target,
                    maxBytes=settings.log_max_bytes,
                    backupCount=settings.log_backups,
                    encoding="utf-8",
                )
            )
        for handler in handlers:
            handler.heritage_handler = True
            handler.setFormatter(formatter)
            handler.setLevel(settings.log_level)
            root.addHandler(handler)
        root.setLevel(settings.log_level)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger = logging.getLogger(name)
            logger.handlers.clear()
            logger.propagate = True
        # Our ASGI middleware emits safe access logs, including stream completion.
        logging.getLogger("uvicorn.access").disabled = True
        log_event("process.logging_ready", process_role=role)


class RateLimitedLog:
    """Bound repeated outage warnings while retaining errors in worker health metrics."""

    def __init__(self, interval=30):
        self.interval, self.last = interval, {}
        self.lock = threading.Lock()

    def emit(self, event, **fields):
        with self.lock:
            now = time.monotonic()
            if now - self.last.get(event, -float("inf")) < self.interval:
                return
            self.last[event] = now
        log_event(event, level=logging.WARNING, **fields)
