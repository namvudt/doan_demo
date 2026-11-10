import hashlib
import json
import secrets
import time
from uuid import uuid4

from sqlalchemy import func, select, text, update

from api.models import Asset, Run, RunEventRecord, SessionToken
from core.runtime_logging import context_fields

TERMINAL = {"succeeded", "failed", "cancelled"}
ACTIVE = {"queued", "running", "cancel_requested"}


class StoreError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def owned(session, model, identifier, owner):
    record = session.get(model, str(identifier))
    if record is None or record.owner_id != owner:
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
                raise StoreError(401, "invalid_token", "Session token is invalid or expired")
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
    def request_hash(body):
        return hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()

    def create_run(self, owner, body, snapshot, mode, key=None):
        digest = self.request_hash(body)
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
                owned(session, Run, body.parent_run_id, owner)
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
            run = Run(
                id=str(uuid4()),
                owner_id=owner,
                asset_id=str(body.asset_id),
                parent_run_id=str(body.parent_run_id) if body.parent_run_id else None,
                request_id=context_fields().get("request_id"),
                question=body.question,
                audience=body.audience,
                profile=body.profile,
                model_mode=mode,
                execution_status="queued",
                config_snapshot=snapshot,
                request_hash=digest,
                idempotency_key=key,
                cancel_requested=False,
                bookmarked=False,
                event_count=0,
                created_at=time.time(),
            )
            session.add(run)
            session.flush()
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
            if run.execution_status == "queued":
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
