import hashlib
import json
import secrets
import time
from uuid import uuid4

from sqlalchemy import func, or_, select, text, update

from api.models import Asset, ModelAttempt, Run, RunEventRecord, SessionToken
from core.config import AppConfig
from core.runtime_logging import context_fields

TERMINAL = {"succeeded", "failed", "cancelled"}
SEGMENT_END = TERMINAL | {"awaiting_input"}
ACTIVE = {"queued", "running", "cancel_requested"}


class StoreError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message = status, code, message
        self.details = details


def owned(session, model, identifier, owner):
    record = session.get(model, str(identifier))
    if (
        record is None
        or record.owner_id != owner
        or getattr(record, "deleted_at", None) is not None
    ):
        raise StoreError(404, "not_found", "Resource not found")
    return record


def append_event(session, run, name, payload):
    run.event_count += 1
    session.add(
        RunEventRecord(
            run_id=run.id,
            sequence=run.event_count,
            event=name,
            payload=payload,
            created_at=time.time(),
        )
    )


def locked_run(session, identifier):
    # Serialize writers on SQLite as well as PostgreSQL before reading the counter.
    session.execute(
        update(Run).where(Run.id == str(identifier)).values(event_count=Run.event_count)
    )
    return session.get(Run, str(identifier), populate_existing=True)


class Store:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings

    def create_session(self, label):
        token = secrets.token_urlsafe(40)
        now = time.time()
        with self.db.session() as session:
            count = session.scalar(
                select(func.count())
                .select_from(SessionToken)
                .where(SessionToken.expires_at > now, SessionToken.revoked.is_(False))
            )
            if count >= self.settings.max_sessions:
                raise StoreError(429, "session_limit", "Active session limit reached")
            record = SessionToken(
                id=str(uuid4()),
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                label=label,
                created_at=now,
                expires_at=now + self.settings.session_ttl_seconds,
                last_seen=now,
                revoked=False,
            )
            session.add(record)
        return record, token

    def authenticate(self, token):
        with self.db.session() as session:
            record = session.scalar(
                select(SessionToken).where(
                    SessionToken.token_hash == hashlib.sha256(token.encode()).hexdigest(),
                    SessionToken.expires_at > time.time(),
                    SessionToken.revoked.is_(False),
                )
            )
            if record is None:
                from api.accounts import AccountStore

                return AccountStore(self.db, self.settings).authenticate(token)
            return record

    def find_replay(self, owner, key, request_hash):
        if not key:
            return None
        with self.db.session() as session:
            record = session.scalar(
                select(Run).where(Run.owner_id == owner, Run.idempotency_key == key)
            )
            if record and record.request_hash != request_hash:
                raise StoreError(
                    409, "idempotency_conflict", "Key was already used for a different request"
                )
            return record

    @staticmethod
    def request_hash(body, run_kind="full", input_context=None):
        payload = body.model_dump(mode="json")
        if payload.get("focus_box") is None:
            payload.pop("focus_box", None)
        if payload.get("location_hint") is None:
            payload.pop("location_hint", None)
        for field in ("conversation_id", "heritage_id"):
            if payload.get(field) is None:
                payload.pop(field, None)
        if run_kind != "full":
            payload["run_kind"] = run_kind
        if input_context is not None:
            payload["input_context"] = input_context
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def create_run(
        self, owner, body, snapshot, mode, key=None, *, run_kind="full", input_context=None
    ):
        digest = self.request_hash(body, run_kind, input_context)
        with self.db.session() as session:
            if self.db.engine.dialect.name == "postgresql":
                session.execute(text("SELECT pg_advisory_xact_lock(714802004)"))
            # Lock owner before counting/admitting. SQLite acquires its write lock here.
            session.execute(
                update(SessionToken).where(SessionToken.id == owner).values(last_seen=time.time())
            )
            if key:
                existing = session.scalar(
                    select(Run).where(Run.owner_id == owner, Run.idempotency_key == key)
                )
                if existing:
                    if existing.request_hash != digest:
                        raise StoreError(
                            409, "idempotency_conflict", "Key was used with another request"
                        )
                    return existing
            owned(session, Asset, body.asset_id, owner)
            if body.parent_run_id:
                parent = owned(session, Run, body.parent_run_id, owner)
            if run_kind == "clarification":
                if not body.parent_run_id:
                    raise StoreError(409, "parent_required", "Clarification needs a parent run")
                parent = locked_run(session, body.parent_run_id)
                pending = (parent.result or {}).get("clarification") or {}
                if parent.execution_status != "awaiting_input" or parent.cancel_requested:
                    raise StoreError(
                        409,
                        "clarification_not_pending",
                        "The original run is not waiting for input",
                    )
                if pending.get("clarification_id") != input_context.get(
                    "clarification_id"
                ) or pending.get("revision") != input_context.get("revision"):
                    raise StoreError(409, "clarification_stale", "Reload the pending clarification")
                ttl = parent.config_snapshot.get("accuracy", {}).get(
                    "clarification_ttl_seconds", 86400
                )
                if time.time() - (parent.finished_at or parent.created_at) > ttl:
                    raise StoreError(410, "clarification_expired", "Start a new run")
            active = session.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.owner_id == owner, Run.execution_status.in_(ACTIVE))
            )
            daily = session.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.owner_id == owner, Run.created_at >= time.time() - 86400)
            )
            if daily >= self.settings.max_runs_per_day:
                raise StoreError(429, "daily_limit", "Daily run quota reached")
            pending = session.scalar(
                select(func.count()).select_from(Run).where(Run.execution_status.in_(ACTIVE))
            )
            if (
                active >= self.settings.max_active_per_owner
                or pending >= self.settings.max_pending_runs
            ):
                raise StoreError(
                    429,
                    "queue_limit",
                    "Too many active runs; retry after an existing run completes",
                )
            identifier = str(uuid4())
            run_input = dict(
                input_context or ({"focus_box": list(body.focus_box)} if body.focus_box else {})
            )
            heritage_fields = (
                "heritage_id",
                "heritage_version",
                "canonical_entity_id",
                "parent_heritage_id",
                "verification_note",
                "location_hint",
            )
            if body.parent_run_id:
                unchanged_identity = str(body.asset_id) == parent.asset_id and not run_input.get(
                    "selected_candidate"
                )
                if unchanged_identity:
                    run_input.update(
                        {
                            field: value
                            for field, value in (parent.input_context or {}).items()
                            if field in heritage_fields and field not in run_input
                        }
                    )
                else:
                    for field in heritage_fields:
                        run_input.pop(field, None)
            if body.location_hint:
                run_input["location_hint"] = body.location_hint.model_dump()
            if getattr(body, "heritage_id", None):
                from api.content_store import ContentStore

                context = ContentStore(self.db).run_context(
                    body.heritage_id,
                    entity_catalog=snapshot.get("accuracy", {}).get("entity_catalog"),
                )
                run_input.update(
                    {
                        field: value
                        for field, value in context.items()
                        if field != "location_hint" or not run_input.get("location_hint")
                    }
                )
            if snapshot.get("accuracy", {}).get("enabled"):
                root_id = (
                    (parent.input_context or {}).get("conversation_root_id", parent.id)
                    if body.parent_run_id
                    else identifier
                )
                limit = snapshot["accuracy"]["max_conversation_llm_calls"]
                committed = 0
                if body.parent_run_id:
                    root = owned(session, Run, root_id, owner)
                    limit = root.config_snapshot.get("accuracy", {}).get(
                        "max_conversation_llm_calls", limit
                    )
                    related = list(
                        session.scalars(
                            select(Run).where(
                                Run.owner_id == owner,
                                or_(
                                    Run.id == root_id,
                                    Run.input_context["conversation_root_id"].as_string()
                                    == root_id,
                                ),
                            )
                        )
                    )
                    ids = [r.id for r in related]
                    attempts = dict(
                        session.execute(
                            select(ModelAttempt.run_id, func.count())
                            .where(ModelAttempt.run_id.in_(ids))
                            .group_by(ModelAttempt.run_id)
                        ).all()
                    )
                    for related_run in related:
                        if related_run.execution_status in ACTIVE:
                            committed += (related_run.input_context or {}).get(
                                "conversation_reserved_calls",
                                related_run.config_snapshot["budget"]["max_llm_calls"],
                            )
                        else:
                            committed += max(
                                attempts.get(related_run.id, 0),
                                len((related_run.result or {}).get("calls", [])),
                            )
                reserved = min(snapshot["budget"]["max_llm_calls"], limit - committed)
                if reserved < 1:
                    raise StoreError(
                        409,
                        "conversation_budget",
                        "Conversation budget is spent or reserved by active runs",
                    )
                config_data = {
                    key: value for key, value in snapshot.items() if key != "config_hash"
                }
                config_data["budget"] = {**config_data["budget"], "max_llm_calls": reserved}
                snapshot = AppConfig.model_validate(config_data).snapshot()
                run_input.update(conversation_root_id=root_id, conversation_reserved_calls=reserved)
            run = Run(
                id=identifier,
                owner_id=owner,
                asset_id=str(body.asset_id),
                parent_run_id=str(body.parent_run_id) if body.parent_run_id else None,
                request_id=context_fields().get("request_id"),
                question=body.question,
                audience=body.audience,
                profile=body.profile,
                model_mode=mode,
                run_kind=run_kind,
                execution_status="queued",
                config_snapshot=snapshot,
                input_context=run_input,
                request_hash=digest,
                idempotency_key=key,
                cancel_requested=False,
                bookmarked=False,
                event_count=0,
                created_at=time.time(),
            )
            session.add(run)
            session.flush()
            from api.conversations import bind_conversation_run

            bind_conversation_run(session, owner, body, run)
            if run_kind == "clarification":
                parent.execution_status = "succeeded"
                parent.input_context = {
                    **(parent.input_context or {}),
                    "continuation_run_id": run.id,
                }
                append_event(
                    session, parent, "run.continued", {"run_id": parent.id, "child_run_id": run.id}
                )
            append_event(
                session, run, "run.queued", {"run_id": run.id, "execution_status": "queued"}
            )
            return run

    def get_run(self, identifier, owner):
        with self.db.session() as session:
            return owned(session, Run, identifier, owner)

    def events(self, identifier, after=0, limit=100):
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(RunEventRecord)
                    .where(
                        RunEventRecord.run_id == str(identifier),
                        RunEventRecord.sequence > after,
                    )
                    .order_by(RunEventRecord.sequence)
                    .limit(limit)
                )
            )

    def cancel(self, identifier, owner):
        with self.db.session() as session:
            run = locked_run(session, identifier)
            if run is None or run.owner_id != owner:
                raise StoreError(404, "not_found", "Resource not found")
            if run.execution_status in TERMINAL or run.cancel_requested:
                return run
            run.cancel_requested = True
            if run.execution_status in {"queued", "awaiting_input"}:
                run.execution_status = "cancelled"
                run.finished_at = time.time()
            else:
                run.execution_status = "cancel_requested"
            append_event(
                session,
                run,
                "run." + run.execution_status,
                {"run_id": run.id, "execution_status": run.execution_status},
            )
            return run
