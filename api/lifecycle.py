"""Owner deletion, bounded recovery, and conservative retention planning."""

import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import delete, func, or_, select, update

from api.models import Asset, Feedback, ModelAttempt, Run, RunEventRecord, SessionToken
from api.product_models import Account, AccountSession, AuthRateLimit
from api.recovery import checkpoint_nodes
from api.recovery_models import NodeCheckpoint, RecoveryRequest
from api.schemas import RunView
from api.store import ACTIVE, SEGMENT_END, StoreError, append_event, locked_run
from api.views import run_view


def lifecycle_router(settings, *, runtime_dependency, principal_dependency, operations_security):
    router = APIRouter(prefix="/api/v1", tags=["Lifecycle"])
    runtime = Annotated[object, Depends(runtime_dependency)]
    principal = Annotated[object, Depends(principal_dependency)]

    @router.delete("/runs/{run_id}", status_code=204)
    def remove_run(run_id: UUID, owner: principal, rt: runtime):
        with rt.db.session() as session:
            # Match create_run's owner -> run lock order so a concurrently
            # admitted child cannot appear after the descendant check.
            session.execute(
                update(SessionToken)
                .where(SessionToken.id == owner.id)
                .values(last_seen=SessionToken.last_seen)
            )
            run = session.get(Run, str(run_id))
            if run is None or run.owner_id != owner.id:
                raise StoreError(404, "not_found", "Resource not found")
            if run.deleted_at is not None:
                return Response(status_code=204)
            run = locked_run(session, str(run_id))
            if run.deleted_at is not None:
                return Response(status_code=204)
            if run.execution_status not in SEGMENT_END:
                raise StoreError(409, "run_active", "Cancel the active run before deleting it")
            if session.scalar(
                select(Run.id).where(Run.parent_run_id == run.id, Run.deleted_at.is_(None)).limit(1)
            ):
                raise StoreError(
                    409,
                    "run_has_children",
                    "Delete descendant runs first to preserve workflow lineage",
                )
            if run.execution_status == "awaiting_input":
                run.execution_status, run.cancel_requested = "cancelled", True
            run.deleted_at = time.time()
        return Response(status_code=204)

    @router.get("/runs/{run_id}/recovery")
    def recovery_status(run_id: UUID, owner: principal, rt: runtime):
        run = rt.store.get_run(run_id, owner.id)
        nodes = checkpoint_nodes(rt.db, str(run_id))
        return {
            "run_id": run.id,
            "completed_nodes": nodes,
            "recoveries": run.recovery_count,
            "max_recoveries": settings.max_recoveries,
            "can_resume": settings.durable_checkpoints
            and bool(nodes)
            and run.execution_status == "failed"
            and run.error_type == "WorkerLost"
            and run.recovery_count < settings.max_recoveries
            and not run.cancel_requested,
            "semantics": "Completed nodes are replayed; interrupted external calls may be retried within the original budget.",
        }

    @router.post("/runs/{run_id}/resume", response_model=RunView, status_code=202)
    def resume_run(
        run_id: UUID,
        owner: principal,
        rt: runtime,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    ):
        if not key.strip() or any(ord(c) < 32 or ord(c) == 127 for c in key):
            raise StoreError(422, "invalid_idempotency_key", "Provide a valid idempotency key")
        with rt.db.session() as session:
            session.execute(
                update(SessionToken)
                .where(SessionToken.id == owner.id)
                .values(last_seen=time.time())
            )
            run = locked_run(session, str(run_id))
            if run is None or run.owner_id != owner.id or run.deleted_at:
                raise StoreError(404, "not_found", "Resource not found")
            if run.model_mode != settings.model_mode:
                raise StoreError(409, "model_mode_mismatch", "Resume using the original model mode")
            if session.get(RecoveryRequest, (run.id, key)):
                return run_view(run)
            if not settings.durable_checkpoints or run.recovery_count >= settings.max_recoveries:
                raise StoreError(
                    409, "recovery_limit", "Recovery is unavailable or its limit was reached"
                )
            if (
                run.execution_status != "failed"
                or run.error_type != "WorkerLost"
                or run.cancel_requested
            ):
                raise StoreError(
                    409, "not_resumable", "Only interrupted worker runs can be resumed"
                )
            if not session.scalar(
                select(func.count())
                .select_from(NodeCheckpoint)
                .where(NodeCheckpoint.run_id == run.id)
            ):
                raise StoreError(409, "checkpoint_missing", "No completed node is available")
            active = session.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.owner_id == owner.id, Run.execution_status.in_(ACTIVE))
            )
            if active >= settings.max_active_per_owner:
                raise StoreError(429, "active_limit", "Active run limit reached")
            run.execution_status, run.error_type, run.finished_at = "queued", None, None
            run.worker_token, run.lease_expires_at = None, None
            run.recovery_count += 1
            session.add(
                RecoveryRequest(
                    run_id=run.id,
                    key=key,
                    recovery_count=run.recovery_count,
                    created_at=time.time(),
                )
            )
            append_event(
                session,
                run,
                "run.queued",
                {
                    "run_id": run.id,
                    "execution_status": "queued",
                    "recovery_count": run.recovery_count,
                },
            )
            return run_view(run)

    return router


def purge_data(runtime, *, apply=False, now=None):
    """Plan by default; retain accounts, active work, referenced assets and recent data."""
    from api.conversations import purge_owner_dependencies, purge_run_dependencies

    now = now or time.time()
    settings, database = runtime.settings, runtime.db
    deleted_cutoff = now - settings.deleted_run_retention_days * 86400
    guest_cutoff = now - settings.expired_guest_retention_days * 86400
    keys = []
    with database.session() as session:
        account_owners = select(Account.owner_id)
        guests = set(
            session.scalars(
                select(SessionToken.id).where(
                    SessionToken.id.not_in(account_owners),
                    or_(
                        SessionToken.expires_at < guest_cutoff,
                        (SessionToken.revoked.is_(True)) & (SessionToken.last_seen < guest_cutoff),
                    ),
                )
            )
        )
        active_owners = set(
            session.scalars(select(Run.owner_id).where(Run.execution_status.in_(ACTIVE)))
        )
        guests -= active_owners
        runs = set(
            session.scalars(
                select(Run.id).where(
                    Run.execution_status.not_in(ACTIVE),
                    or_(Run.deleted_at < deleted_cutoff, Run.owner_id.in_(guests)),
                )
            )
        )
        # Retained descendants keep their parent FK; never broaden a deletion silently.
        while runs:
            parents = set(
                session.scalars(
                    select(Run.parent_run_id).where(
                        Run.parent_run_id.in_(runs), Run.id.not_in(runs)
                    )
                )
            )
            if not parents:
                break
            runs -= parents
        candidate_assets = set(session.scalars(select(Run.asset_id).where(Run.id.in_(runs))))
        assets = list(
            session.scalars(
                select(Asset).where(
                    or_(Asset.owner_id.in_(guests), Asset.id.in_(candidate_assets)),
                    Asset.id.not_in(select(Run.asset_id).where(Run.id.not_in(runs))),
                )
            )
        )
        result = {
            "dry_run": not apply,
            "runs": len(runs),
            "assets": len(assets),
            "expired_guest_candidates": len(guests),
        }
        if not apply:
            return result
        session.execute(
            delete(AccountSession).where(AccountSession.refresh_expires_at < guest_cutoff)
        )
        session.execute(delete(AuthRateLimit).where(AuthRateLimit.started_at < now - 86400))
        if runs:
            purge_run_dependencies(session, runs)
            for model in (Feedback, ModelAttempt, RunEventRecord, NodeCheckpoint, RecoveryRequest):
                session.execute(delete(model).where(model.run_id.in_(runs)))
            session.execute(update(Run).where(Run.id.in_(runs)).values(parent_run_id=None))
            session.execute(delete(Run).where(Run.id.in_(runs)))
        for asset in assets:
            keys.append(asset.storage_key)
            session.delete(asset)
        session.flush()
        safe_guests = (
            guests
            - set(session.scalars(select(Run.owner_id)))
            - set(session.scalars(select(Asset.owner_id)))
        )
        if safe_guests:
            purge_owner_dependencies(session, safe_guests)
            session.execute(delete(SessionToken).where(SessionToken.id.in_(safe_guests)))
        result["guests_purged"] = len(safe_guests)
    removed = 0
    for key in keys:
        path = runtime.asset_path(key)
        if path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)
            removed += 1
    # Sweep old orphan files left by a previous process crash, with a grace period.
    with database.session() as session:
        referenced = set(session.scalars(select(Asset.storage_key)))
    for path in (settings.data_dir / "assets").iterdir():
        if (
            path.is_file()
            and not path.is_symlink()
            and path.name not in referenced
            and path.stat().st_mtime < deleted_cutoff
        ):
            path.unlink(missing_ok=True)
            removed += 1
    result["files_removed"] = removed
    return result
