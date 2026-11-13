"""Bounded metadata probes. Cache keys use a process-local HMAC, never exported."""

import hashlib
import hmac
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor

from core.model_errors import failure_info
from core.runtime_logging import log_event

MANDATORY_ROLES = ("coordinator", "visual", "aggregator", "judge")
_salt = os.urandom(32)
_lock = threading.Lock()
_cache = OrderedDict()
_pending = {}


class PreflightFailed(RuntimeError):
    def __init__(self, report):
        self.report = report
        self.failures = [r for r in report["roles"] if not r["ready"]]
        self.error_code = self.failures[0]["error_code"]
        super().__init__("Required model role is unavailable")


def ensure_ready(manager, roles=None, force=False):
    report = manager.preflight(roles or MANDATORY_ROLES, force=force)
    if not report["ready"]:
        raise PreflightFailed(report)
    return report


def check_roles(manager, roles, force=False):
    roles = list(dict.fromkeys(roles))
    if any(role not in manager.config.roles for role in roles):
        raise ValueError("Unknown preflight role")

    def check(role):
        provider, model, credential, _ = manager._binding(role, "gemini")
        base = {"role": role, "provider": provider, "model": model}
        pc = manager.config.providers[provider]
        endpoint = manager._credentials.get(pc.base_url_env or "", "")
        if not credential or provider == "gpu" and not endpoint:
            return {
                **base,
                "ready": False,
                "cached": False,
                "checked_at": time.time(),
                "error_code": "model_not_configured",
                "error_category": "configuration",
                "retryable": False,
            }
        identity = hmac.new(_salt, (credential + "\0" + endpoint).encode(), hashlib.sha256).digest()
        key = (provider, model, identity)
        with _lock:
            cached = _cache.get(key)
            if (
                not force
                and manager.config.preflight_ttl_seconds > 0
                and cached
                and cached[0] > time.monotonic()
            ):
                _cache.move_to_end(key)
                return {**base, **cached[1], "cached": True}
            future = _pending.get(key)
            owner = future is None
            if owner:
                future = _pending[key] = Future()
        if not owner:
            try:
                result = future.result(timeout=manager.config.preflight_timeout_seconds + 2)
            except TimeoutError as error:
                result = {"ready": False, "checked_at": time.time(), **failure_info(error)}
            return {**base, **result, "cached": True}
        try:
            client = manager._client(provider, model, credential)
            timeout = manager.config.preflight_timeout_seconds
            if provider == "gemini":
                client.models.get(
                    model=model, config={"http_options": {"timeout": int(timeout * 1000)}}
                )
            else:
                models = client.models.list(timeout=timeout)
                if model not in {item.id for item in models.data}:
                    raise LookupError("Configured model is not listed")
            result = {
                "ready": True,
                "checked_at": time.time(),
                "error_code": None,
                "error_category": None,
                "retryable": False,
            }
        except Exception as error:
            result = {"ready": False, "checked_at": time.time(), **failure_info(error)}
            if isinstance(error, LookupError):
                result.update(error_code="model_not_found", error_category="configuration")
        with _lock:
            ttl = (
                manager.config.preflight_ttl_seconds
                if result["ready"]
                else min(15, manager.config.preflight_ttl_seconds)
            )
            _cache[key] = (time.monotonic() + ttl, result)
            _cache.move_to_end(key)
            while len(_cache) > 256:
                _cache.popitem(last=False)
            future.set_result(result)
            del _pending[key]
        log_event(
            "preflight.completed",
            agent_role=role,
            actual_provider=provider,
            status="ready" if result["ready"] else "failed",
            error_code=result.get("error_code"),
            error_category=result.get("error_category"),
            provider_reason=result.get("provider_reason"),
            provider_status_code=result.get("provider_status_code"),
        )
        return {**base, **result, "cached": False}

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(roles)))) as pool:
        records = list(pool.map(check, roles))
    return {
        "ready": all(r["ready"] for r in records),
        "roles": records,
        "scope": "model_metadata",
        "generation_verified": False,
    }
