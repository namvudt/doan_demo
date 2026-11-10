"""Durable database queue with atomic claims, leases and cooperative cancellation."""

import logging
import signal
import threading
import time
from uuid import uuid4

from sqlalchemy import select, update

from api.models import Asset, ModelAttempt, Run, SessionToken, WorkerHeartbeat
from api.settings import Settings
from api.store import TERMINAL, append_event, locked_run
from core.runtime_logging import RateLimitedLog, configure_logging, log_context, log_event
from workflow.service import RunCancelled


class Worker:
    def __init__(self, runtime):
        self.runtime = runtime
        self.id = str(uuid4())
        self.stop_event = threading.Event()
        self.thread = None
        self.heartbeat_thread = None
        self.active = None
        self.outage_logs = RateLimitedLog()

    def heartbeat(self):
        now = time.time()
        with self.runtime.db.session() as session:
            worker = session.get(WorkerHeartbeat, self.id)
            if worker:
                worker.heartbeat_at = now
            else:
                session.add(WorkerHeartbeat(id=self.id, heartbeat_at=now))
            active = self.active
            if active:
                run_id, token = active
                session.execute(
                    update(Run)
                    .where(
                        Run.id == run_id,
                        Run.worker_token == token,
                        Run.execution_status.in_(["running", "cancel_requested"]),
                    )
                    .values(lease_expires_at=now + self.runtime.settings.lease_seconds)
                )

    def heartbeat_loop(self):
        while not self.stop_event.wait(self.runtime.settings.heartbeat_seconds):
            try:
                self.heartbeat()
            except Exception as exc:
                self.outage_logs.emit("worker.heartbeat_failed", worker_id=self.id, error=exc)

    def recover_stale(self):
        with self.runtime.db.session() as session:
            stale = list(
                session.scalars(
                    select(Run.id).where(
                        Run.execution_status.in_(["running", "cancel_requested"]),
                        Run.lease_expires_at < time.time(),
                    )
                )
            )
        for identifier in stale:
            with self.runtime.db.session() as session:
                run = locked_run(session, identifier)
                if (
                    not run
                    or run.execution_status in TERMINAL
                    or (run.lease_expires_at or float("inf")) >= time.time()
                ):
                    continue
                run.execution_status = "cancelled" if run.cancel_requested else "failed"
                run.error_type = "WorkerLost"
                run.finished_at = time.time()
                run.worker_token = None
                append_event(
                    session,
                    run,
                    "run." + run.execution_status,
                    {
                        "run_id": run.id,
                        "execution_status": run.execution_status,
                        "error_type": "WorkerLost",
                    },
                )
                session.execute(
                    update(ModelAttempt)
                    .where(ModelAttempt.run_id == run.id, ModelAttempt.status == "running")
                    .values(status="interrupted", error_type="WorkerLost", finished_at=time.time())
                )
            log_event(
                "worker.lease_lost",
                level=logging.ERROR,
                run_id=identifier,
                trace_id=identifier,
                request_id=run.request_id,
                worker_id=self.id,
                error_type="WorkerLost",
            )

    def claim(self):
        self.recover_stale()
        with self.runtime.db.session() as session:
            ids = list(
                session.scalars(
                    select(Run.id)
                    .where(Run.execution_status == "queued", Run.cancel_requested.is_(False))
                    .order_by(Run.created_at)
                    .limit(10)
                )
            )
            for identifier in ids:
                token = str(uuid4())
                claimed = session.execute(
                    update(Run)
                    .where(
                        Run.id == identifier,
                        Run.execution_status == "queued",
                        Run.cancel_requested.is_(False),
                    )
                    .values(
                        execution_status="running",
                        worker_token=token,
                        started_at=time.time(),
                        lease_expires_at=time.time() + self.runtime.settings.lease_seconds,
                    )
                )
                if claimed.rowcount == 1:
                    run = session.get(Run, identifier, populate_existing=True)
                    append_event(
                        session,
                        run,
                        "run.running",
                        {"run_id": run.id, "execution_status": "running"},
                    )
                    return run, token
        return None

    def cancellation_check(self, identifier, token):
        with self.runtime.db.session() as session:
            run = session.get(Run, identifier)
            owner = session.get(SessionToken, run.owner_id) if run else None
            if (
                not run
                or not owner
                or owner.revoked
                or owner.expires_at <= time.time()
                or run.worker_token != token
                or run.cancel_requested
                or run.execution_status in TERMINAL
            ):
                raise RunCancelled("Run cancellation or lease loss")

    def persist(self, identifier, token, event):
        with self.runtime.db.session() as session:
            run = locked_run(session, identifier)
            if run.worker_token != token or run.execution_status in TERMINAL:
                raise RunCancelled("Lease lost")
            if run.cancel_requested:
                raise RunCancelled("Cancellation requested")
            if event.kind == "completed":
                run.result = event.result.model_dump(mode="json")
                run.result_status = event.result.status
                run.execution_status = "failed" if event.result.status == "failed" else "succeeded"
                run.error_type = "WorkflowFailed" if event.result.status == "failed" else None
                run.finished_at = time.time()
                append_event(
                    session,
                    run,
                    "run." + run.execution_status,
                    {
                        "run_id": run.id,
                        "execution_status": run.execution_status,
                        "result_status": run.result_status,
                        "result_url": f"/api/v1/runs/{run.id}/result",
                    },
                )
            else:
                append_event(
                    session,
                    run,
                    "stage." + event.status,
                    event.model_dump(mode="json", exclude={"result", "sequence"}),
                )
        if event.kind == "completed":
            # Reconcile completed calls for custom adapters as well as transient write failures.
            from api.telemetry import persist_attempt

            for record in event.result.calls:
                try:
                    persist_attempt(self.runtime.db, identifier, record)
                except Exception as exc:
                    self.outage_logs.emit("model.reconciliation_failed", error=exc)
            log_event(
                "run." + run.execution_status,
                status=run.execution_status,
                duration_ms=round(event.result.duration * 1000, 3),
                error_type=run.error_type,
            )

    def finish_error(self, identifier, token, error):
        with self.runtime.db.session() as session:
            run = locked_run(session, identifier)
            if run is None or run.worker_token != token or run.execution_status in TERMINAL:
                return
            run.execution_status = (
                "cancelled" if isinstance(error, RunCancelled) or run.cancel_requested else "failed"
            )
            run.error_type = (
                "Cancelled" if run.execution_status == "cancelled" else type(error).__name__
            )
            run.finished_at = time.time()
            append_event(
                session,
                run,
                "run." + run.execution_status,
                {
                    "run_id": run.id,
                    "execution_status": run.execution_status,
                    "error_type": run.error_type,
                },
            )
            session.execute(
                update(ModelAttempt)
                .where(ModelAttempt.run_id == identifier, ModelAttempt.status == "running")
                .values(status="interrupted", error_type=run.error_type, finished_at=time.time())
            )
        log_event(
            "run." + run.execution_status,
            level=logging.INFO if run.execution_status == "cancelled" else logging.ERROR,
            status=run.execution_status,
            error=error,
        )

    def process_one(self):
        claimed = self.claim()
        if not claimed:
            return False
        run, token = claimed
        with log_context(
            request_id=run.request_id, run_id=run.id, trace_id=run.id, worker_id=self.id
        ):
            log_event(
                "run.running",
                queue_wait_ms=round((time.time() - run.created_at) * 1000, 3),
                model_mode=run.model_mode,
            )
            self._process_run(run, token)
        return True

    def _process_run(self, run, token):
        self.active = (run.id, token)
        service = None
        try:
            self.cancellation_check(run.id, token)
            with self.runtime.db.session() as session:
                asset = session.get(Asset, run.asset_id)
                path = self.runtime.asset_path(asset.storage_key)
            service = self.runtime.service(run)
            with self.runtime.tracing_context(run.model_mode):
                stream = service.stream(
                    path.read_bytes(),
                    run.question,
                    run.audience,
                    run_id=run.id,
                    cancel_check=lambda: self.cancellation_check(run.id, token),
                )
                try:
                    for event in stream:
                        self.persist(run.id, token, event)
                finally:
                    stream.close()
            # A faulty adapter must not leave a permanently running job.
            with self.runtime.db.session() as session:
                current = session.get(Run, run.id)
                if current.execution_status not in TERMINAL:
                    raise RuntimeError("Missing workflow result")
        except Exception as exc:
            self.finish_error(run.id, token, exc)
        finally:
            if service:
                service.llm.close()
            self.active = None

    def loop(self):
        log_event("worker.started", worker_id=self.id)
        self.heartbeat()
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        while not self.stop_event.is_set():
            try:
                worked = self.process_one()
            except Exception as exc:
                self.outage_logs.emit("worker.poll_failed", worker_id=self.id, error=exc)
                worked = False
            if not worked:
                self.stop_event.wait(self.runtime.settings.poll_seconds)

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="heritage-worker", daemon=True)
        self.thread.start()

    def stop(self):
        log_event("worker.stopping", worker_id=self.id)
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
        with self.runtime.db.session() as session:
            record = session.get(WorkerHeartbeat, self.id)
            if record:
                session.delete(record)


def main():
    from api.runtime import Runtime

    settings = Settings.from_env()
    configure_logging(settings, role="worker")
    runtime = Runtime(settings)
    runtime.migrate()
    worker = Worker(runtime)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: worker.stop_event.set())
    try:
        worker.loop()
    finally:
        worker.stop()
        runtime.db.close()


if __name__ == "__main__":
    main()
