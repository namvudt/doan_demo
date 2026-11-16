"""Durable node-boundary replay, with lease, input, source and budget checks."""

import hashlib
import json
import os
import time
from contextlib import nullcontext
from copy import deepcopy

from sqlalchemy import select

from api.models import ModelAttempt, Run
from api.recovery_models import NodeCheckpoint
from api.store import locked_run
from workflow.service import RunCancelled

CALL_FIELDS = {
    "attempt",
    "agent_role",
    "actual_provider",
    "model_used",
    "status",
    "retry",
    "fallback_used",
    "started_at",
    "finished_at",
    "duration",
    "error_type",
    "usage",
    "diagnostics",
}
ACCURACY_FIELDS = {
    "scope": ("quality",),
    "coordinate": ("slots", "candidates"),
    "visual": (
        "candidates",
        "evidence",
        "identity_resolved",
        "visual_readability",
        "candidate_support",
        "reused_nodes",
    ),
    "judge": (
        "slots",
        "candidates",
        "evidence",
        "claims",
        "quality",
        "identity_resolved",
        "clarification",
        "answer_status",
        "recognition",
        "candidate_support",
        "visual_readability",
        "reused_nodes",
    ),
}


def calls_only(items):
    return [{key: value for key, value in item.items() if key in CALL_FIELDS} for item in items]


def capture_accuracy(node, accuracy):
    if accuracy is None:
        return None
    result = {key: deepcopy(getattr(accuracy, key)) for key in ACCURACY_FIELDS.get(node, ())}
    with accuracy.tools.lock:
        result["tool_calls"] = deepcopy(accuracy.tools.calls)
    if node in {"visual", "judge"}:
        result["tool_regions"] = deepcopy(accuracy.tools.regions)
        result["tool_evidence"] = deepcopy(accuracy.tools.evidence)
    return result


def restore_accuracy(accuracy, values):
    if accuracy is None or not values:
        return
    for key, value in values.items():
        if not key.startswith("tool_"):
            setattr(accuracy, key, deepcopy(value))
    with accuracy.tools.lock:
        existing = {item["call_id"]: item for item in accuracy.tools.calls}
        for item in values.get("tool_calls", []):
            previous = existing.get(item["call_id"])
            if previous is None:
                existing[item["call_id"]] = deepcopy(item)
            elif item.get("status") != "running" or previous.get("status") == "running":
                existing[item["call_id"]] = {**previous, **deepcopy(item)}
        accuracy.tools.calls = list(existing.values())
        if "tool_regions" in values:
            accuracy.tools.regions = deepcopy(values["tool_regions"])
            accuracy.tools.evidence = deepcopy(values.get("tool_evidence", []))


class NodeRecovery:
    """Replay completed nodes only; an interrupted external call may need another attempt."""

    def __init__(self, database, run, *, revision_provider=None):
        self.db, self.run_id, self.token = database, run.id, run.worker_token
        self.config_hash = run.config_snapshot.get("config_hash", "")
        self.revision_provider = revision_provider or (lambda: "")
        self.resuming = run.recovery_count > 0
        self.elapsed = (
            max(0, time.time() - run.started_at) if self.resuming and run.started_at else 0
        )

    def signature(self, node, state):
        relevant = {key: value for key, value in state.items() if key != "node_metadata"}
        if "image_data" in relevant:
            relevant["image_data"] = hashlib.sha256(relevant["image_data"]).hexdigest()
        value = {
            "checkpoint_schema": 1,
            "backend_build": os.getenv("HERITAGE_BUILD_REVISION", "development"),
            "node": node,
            "state": relevant,
            "config": self.config_hash,
            "sources": self.revision_provider(),
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

    def load(self, node, signature, accuracy):
        if not self.resuming:
            return None
        with self.db.session() as session:
            run = session.get(Run, self.run_id)
            if (
                run is None
                or run.worker_token != self.token
                or run.execution_status != "running"
                or run.cancel_requested
                or run.deleted_at
                or (run.lease_expires_at or 0) <= time.time()
            ):
                raise RunCancelled("Checkpoint lease is no longer active")
            record = session.get(NodeCheckpoint, (self.run_id, node))
            if record is None or record.signature != signature:
                return None
            payload = deepcopy(record.payload)
        restore_accuracy(accuracy, payload.get("accuracy"))
        update = payload["update"]
        update.setdefault("_meta", {}).update(checkpoint_reused=True, reused=True)
        return update

    def save(self, node, signature, update, accuracy, llm):
        if update.get("errors") or update.get("fatal"):
            return
        with getattr(llm, "_lock", getattr(llm, "lock", nullcontext())):
            calls = calls_only(llm.calls)
        payload = {
            "update": deepcopy(update),
            "accuracy": capture_accuracy(node, accuracy),
            "calls": calls,
        }
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 4_000_000:
            raise ValueError("Checkpoint exceeds the node storage limit")
        with self.db.session() as session:
            run = locked_run(session, self.run_id)
            if (
                run is None
                or run.worker_token != self.token
                or run.cancel_requested
                or run.deleted_at
                or run.execution_status != "running"
                or (run.lease_expires_at or 0) <= time.time()
            ):
                raise RunCancelled("Checkpoint lease is no longer active")
            record = session.get(NodeCheckpoint, (self.run_id, node))
            if record is None:
                record = NodeCheckpoint(run_id=self.run_id, node=node)
                session.add(record)
            record.signature, record.payload, record.updated_at = signature, payload, time.time()

    def prior_calls(self):
        if not self.resuming:
            return []
        calls = {}
        with self.db.session() as session:
            for checkpoint in session.scalars(
                select(NodeCheckpoint).where(NodeCheckpoint.run_id == self.run_id)
            ):
                for item in checkpoint.payload.get("calls", []):
                    calls[item["attempt"]] = item
            for record in session.scalars(
                select(ModelAttempt).where(ModelAttempt.run_id == self.run_id)
            ):
                calls[record.attempt] = {key: getattr(record, key, None) for key in CALL_FIELDS}
        return [calls[key] for key in sorted(calls)]


def checkpoint_nodes(database, identifier):
    with database.session() as session:
        return list(
            session.scalars(select(NodeCheckpoint.node).where(NodeCheckpoint.run_id == identifier))
        )
