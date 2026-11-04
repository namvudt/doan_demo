"""Run: uv run uvicorn api.main:app --host 127.0.0.1 --port 8000"""

import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Header, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text, update
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from api.models import Asset, Feedback, Run, SessionToken, WorkerHeartbeat
from api.runtime import Runtime
from api.schemas import (
    AssetView,
    BookmarkBody,
    CapabilitiesView,
    ErrorResponse,
    EventPage,
    FeedbackBody,
    MetricsView,
    ResultView,
    RunCreate,
    RunPage,
    RunView,
    SamplesView,
    SessionCreate,
    SessionCreated,
    SessionView,
    SourcesView,
    StepsView,
    WorkflowView,
)
from api.settings import ROOT, Settings
from api.store import TERMINAL, StoreError, owned
from api.views import asset_view, public_event, result_view, run_view, timestamp
from api.worker import Worker
from core.presentation import collect_sources, markdown_report, stage_snapshots, usage_summary

logger = logging.getLogger(__name__)

bearer = HTTPBearer(
    auto_error=False, description="Token từ POST /api/v1/sessions. Dán access_token vào Authorize."
)
bootstrap_header = APIKeyHeader(
    name="X-Bootstrap-Token",
    auto_error=False,
    description="Chỉ dùng để cấp session khi server có API_BOOTSTRAP_TOKEN.",
)


def runtime(request: Request):
    return request.app.state.runtime


def principal(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise StoreError(
            401,
            "authentication_required",
            "Create a session, then use Authorize with its access_token",
        )
    return runtime(request).store.authenticate(credentials.credentials)


Owner = Annotated[SessionToken, Depends(principal)]
RuntimeDependency = Annotated[Runtime, Depends(runtime)]


def completed_run(rt, identifier, owner):
    run = rt.store.get_run(identifier, owner)
    if run.result is None:
        if run.execution_status in TERMINAL:
            raise StoreError(
                409,
                "result_unavailable",
                "Run ended without an answer; inspect events and error_type",
            )
        raise StoreError(
            409, "run_not_finished", "Run has not finished; inspect status or subscribe to events"
        )
    return run


class RequestEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.request_id = str(uuid4())
        max_body = request.app.state.settings.max_upload_bytes + 1_000_000

        def reject(status, code, message):
            return JSONResponse(
                status_code=status,
                content={
                    "error": {
                        "code": code,
                        "message": message,
                        "request_id": request.state.request_id,
                    }
                },
                headers={"X-Request-ID": request.state.request_id},
            )

        try:
            if int(request.headers.get("content-length", "0")) > max_body:
                return reject(413, "body_too_large", "Request body exceeds upload limit")
        except ValueError:
            return reject(400, "invalid_content_length", "Invalid Content-Length")
        receive = request._receive
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > max_body:
                request.state.body_too_large = True
                raise HTTPException(status_code=413)
            return message

        request._receive = limited_receive
        try:
            response = await call_next(request)
        except Exception as exc:
            if getattr(request.state, "body_too_large", False):
                return reject(413, "body_too_large", "Request body exceeds upload limit")
            logger.error(
                "API request failed request_id=%s error_type=%s",
                request.state.request_id,
                type(exc).__name__,
            )
            return reject(
                500, "internal_error", "Internal error; use X-Request-ID for investigation"
            )
        if getattr(request.state, "body_too_large", False):
            return reject(413, "body_too_large", "Request body exceeds upload limit")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response


def create_app(settings=None, *, manager_factory=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        rt = Runtime(settings, manager_factory=manager_factory)
        rt.config()
        rt.migrate()
        app.state.runtime = rt
        worker = Worker(rt) if settings.embedded_worker else None
        if worker:
            # Readiness should work immediately after lifespan startup.
            worker.heartbeat()
            worker.start()
        try:
            yield
        finally:
            if worker:
                worker.stop()
            rt.db.close()

    app = FastAPI(
        title="Heritage VQA API",
        version="1.0.0",
        lifespan=lifespan,
        description="""## Thử nhanh trên Swagger
1. `POST /api/v1/sessions` → sao chép `access_token`.
2. Nhấn **Authorize**, nhập token trong **HTTPBearer**.
3. `POST /api/v1/assets` để upload ảnh, hoặc `POST /api/v1/samples/{sample_id}/assets`.
4. `POST /api/v1/runs` với `asset_id` và `question` → nhận `run_id` (202).
5. `GET /runs/{run_id}` và `GET /runs/{run_id}/events/history` để quan sát từng bước.
6. `GET /runs/{run_id}/result` khi xong; `include_intermediate=true` để xem bản nháp.

`/events` là SSE cho frontend; `/events/history` là JSON thuận tiện thử trên Swagger.
**live** gọi provider thật và có thể phát sinh phí. **demo** chạy đầy đủ graph với dữ liệu mô phỏng.
Kiểm tra mode tại `/api/v1/capabilities` trước khi tạo run.
""",
        swagger_ui_parameters={
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "docExpansion": "none",
            "defaultModelsExpandDepth": 0,
        },
        openapi_tags=[
            {"name": name, "description": description}
            for name, description in [
                ("Health", "Liveness, database/worker readiness."),
                ("Sessions", "Cấp token phiên và thu hồi; quyền sở hữu theo session."),
                ("Configuration", "Mode, giới hạn, profile và workflow công khai."),
                ("Assets", "Ảnh chuẩn hóa PNG, ownership và samples."),
                ("Runs", "Hàng đợi bền vững, lịch sử, hủy và retry chủ động."),
                ("Events", "SSE và lịch sử sự kiện JSON có cursor."),
                ("Results", "Câu trả lời, nguồn, các bước và báo cáo."),
                ("Feedback", "Đánh dấu và phản hồi cá nhân theo run."),
            ]
        ],
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503)
        },
    )
    app.state.settings = settings
    app.add_middleware(RequestEnvelopeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "X-Bootstrap-Token",
        ],
        expose_headers=["X-Request-ID", "Location"],
        allow_credentials=False,
    )

    def error_response(request, status, code, message):
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", str(uuid4())),
                }
            },
            headers=headers,
        )

    @app.exception_handler(StoreError)
    async def store_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # ValidationError.input can contain bearer tokens, private questions or bytes.
        fields = [".".join(map(str, e["loc"])) for e in exc.errors()]
        return error_response(
            request, 422, "validation_error", "Check request fields: " + ", ".join(fields)
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(
            request, exc.status_code, "http_error", "Request could not be processed"
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return error_response(
            request, 500, "internal_error", "Internal error; use X-Request-ID for investigation"
        )

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse("/docs")

    @app.get("/health/live", tags=["Health"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["Health"])
    def ready(rt: RuntimeDependency, response: Response):
        try:
            with rt.db.session() as session:
                session.execute(text("SELECT 1"))
                worker = session.scalar(select(func.max(WorkerHeartbeat.heartbeat_at)))
            worker_ready = worker is not None and worker > time.time() - settings.lease_seconds
            response.status_code = 200 if worker_ready else 503
            return {
                "status": "ready" if worker_ready else "worker_unavailable",
                "database": True,
                "worker": worker_ready,
                "model_mode": settings.model_mode,
            }
        except Exception:
            response.status_code = 503
            return {"status": "database_unavailable", "database": False, "worker": False}

    @app.post("/api/v1/sessions", tags=["Sessions"], response_model=SessionCreated, status_code=201)
    def create_session(
        body: SessionCreate,
        rt: RuntimeDependency,
        bootstrap: Annotated[str | None, Depends(bootstrap_header)],
    ):
        expected = settings.bootstrap_token.get_secret_value()
        if expected and not hmac.compare_digest(expected, bootstrap or ""):
            raise StoreError(
                403,
                "bootstrap_required",
                "A valid X-Bootstrap-Token is required to create sessions",
            )
        record, token = rt.store.create_session(body.label)
        return SessionCreated(
            session_id=record.id, access_token=token, expires_at=timestamp(record.expires_at)
        )

    @app.get("/api/v1/sessions/me", tags=["Sessions"], response_model=SessionView)
    def me(owner: Owner):
        return SessionView(
            session_id=owner.id, label=owner.label, expires_at=timestamp(owner.expires_at)
        )

    @app.delete("/api/v1/sessions/me", tags=["Sessions"], status_code=204)
    def revoke(owner: Owner, rt: RuntimeDependency):
        with rt.db.session() as session:
            session.get(SessionToken, owner.id).revoked = True
            identifiers = list(
                session.scalars(
                    select(Run.id).where(
                        Run.owner_id == owner.id, Run.execution_status.in_(["queued", "running"])
                    )
                )
            )
        for identifier in identifiers:
            rt.store.cancel(identifier, owner.id)
        return Response(status_code=204)

    @app.get("/api/v1/capabilities", tags=["Configuration"], response_model=CapabilitiesView)
    def capabilities(rt: RuntimeDependency):
        config = rt.config()
        manager = rt.manager(config)
        try:
            status = manager.get_status()
        finally:
            manager.close()
        return {
            "api_version": "v1",
            "config_hash": config.snapshot()["config_hash"],
            "model_mode": settings.model_mode,
            "model_configured": status["ready"],
            "missing_roles": status["missing_roles"],
            "max_upload_bytes": min(settings.max_upload_bytes, config.max_image_bytes),
            "max_image_pixels": config.max_image_pixels,
            "max_question_characters": 4000,
            "profiles": [
                {
                    "id": "default",
                    "workflow_version": config.workflow_version,
                    "generation_enabled": config.enable_generation,
                }
            ],
            "session_bootstrap_required": bool(settings.bootstrap_token.get_secret_value()),
        }

    @app.get("/api/v1/workflow", tags=["Configuration"], response_model=WorkflowView)
    def workflow(owner: Owner, rt: RuntimeDependency):
        from core.presentation import STAGES

        return {
            "version": rt.config().workflow_version,
            "stages": [
                {"id": name, "title": info[1], "description": info[2]}
                for name, info in STAGES.items()
            ],
            "diagram": (ROOT / "docs/langgraph.mmd").read_text(encoding="utf-8"),
        }

    @app.post("/api/v1/assets", tags=["Assets"], response_model=AssetView, status_code=201)
    async def upload(
        owner: Owner,
        rt: RuntimeDependency,
        file: Annotated[
            UploadFile, File(description="JPEG, PNG hoặc WebP; kiểm tra nội dung thực.")
        ],
    ):
        try:
            data = await file.read(min(settings.max_upload_bytes, rt.config().max_image_bytes) + 1)
        finally:
            await file.close()
        return asset_view(await run_in_threadpool(rt.save_asset, owner.id, data))

    @app.get("/api/v1/assets", tags=["Assets"], response_model=list[AssetView])
    def assets(
        owner: Owner,
        rt: RuntimeDependency,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with rt.db.session() as session:
            records = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.owner_id == owner.id)
                    .order_by(Asset.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
        return [asset_view(item) for item in records]

    @app.get("/api/v1/assets/{asset_id}", tags=["Assets"], response_model=AssetView)
    def asset_info(asset_id: UUID, owner: Owner, rt: RuntimeDependency):
        with rt.db.session() as session:
            return asset_view(owned(session, Asset, asset_id, owner.id))

    @app.get(
        "/api/v1/assets/{asset_id}/content",
        tags=["Assets"],
        response_class=FileResponse,
        responses={200: {"content": {"image/png": {}}}},
    )
    def asset_content(asset_id: UUID, owner: Owner, rt: RuntimeDependency):
        with rt.db.session() as session:
            asset = owned(session, Asset, asset_id, owner.id)
        path = rt.asset_path(asset.storage_key)
        if not path.is_file():
            raise StoreError(404, "asset_missing", "Stored image was not found")
        return FileResponse(path, media_type="image/png", filename=f"{asset.id}.png")

    @app.delete("/api/v1/assets/{asset_id}", tags=["Assets"], status_code=204)
    def delete_asset(asset_id: UUID, owner: Owner, rt: RuntimeDependency):
        rt.delete_asset(asset_id, owner.id)
        return Response(status_code=204)

    samples = {
        p.stem: p
        for p in (ROOT / "samples").glob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    }

    @app.get("/api/v1/samples", tags=["Assets"], response_model=SamplesView)
    def sample_list():
        return {
            "items": [{"sample_id": key, "title": key.replace("_", " ")} for key in sorted(samples)]
        }

    @app.post(
        "/api/v1/samples/{sample_id}/assets",
        tags=["Assets"],
        response_model=AssetView,
        status_code=201,
    )
    def use_sample(sample_id: str, owner: Owner, rt: RuntimeDependency):
        path = samples.get(sample_id)
        if path is None:
            raise StoreError(404, "sample_not_found", "Select a sample_id from GET /samples")
        return asset_view(rt.save_asset(owner.id, path.read_bytes()))

    @app.post("/api/v1/runs", tags=["Runs"], response_model=RunView, status_code=202)
    def create_run(
        body: RunCreate,
        owner: Owner,
        rt: RuntimeDependency,
        response: Response,
        key: Annotated[
            str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)
        ] = None,
    ):
        existing = rt.store.find_replay(owner.id, key, rt.store.request_hash(body))
        if existing:
            response.headers["Location"] = f"/api/v1/runs/{existing.id}"
            return run_view(existing)
        rt.check_model_ready()
        record = rt.store.create_run(
            owner.id, body, rt.config().snapshot(), settings.model_mode, key
        )
        response.headers["Location"] = f"/api/v1/runs/{record.id}"
        return run_view(record)

    @app.get("/api/v1/runs", tags=["Runs"], response_model=RunPage)
    def list_runs(
        owner: Owner,
        rt: RuntimeDependency,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        saved_only: bool = False,
        execution_status: str | None = Query(
            None, pattern="^(queued|running|cancel_requested|succeeded|failed|cancelled)$"
        ),
    ):
        conditions = [Run.owner_id == owner.id]
        if saved_only:
            conditions.append(Run.bookmarked.is_(True))
        if execution_status:
            conditions.append(Run.execution_status == execution_status)
        with rt.db.session() as session:
            total = session.scalar(select(func.count()).select_from(Run).where(*conditions))
            records = list(
                session.scalars(
                    select(Run)
                    .where(*conditions)
                    .order_by(Run.created_at.desc(), Run.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
        return RunPage(
            items=[run_view(item) for item in records], total=total, limit=limit, offset=offset
        )

    @app.get("/api/v1/runs/{run_id}", tags=["Runs"], response_model=RunView)
    def get_run(run_id: UUID, owner: Owner, rt: RuntimeDependency):
        return run_view(rt.store.get_run(run_id, owner.id))

    @app.post("/api/v1/runs/{run_id}/cancel", tags=["Runs"], response_model=RunView)
    def cancel(run_id: UUID, owner: Owner, rt: RuntimeDependency):
        return run_view(rt.store.cancel(run_id, owner.id))

    @app.post("/api/v1/runs/{run_id}/retry", tags=["Runs"], response_model=RunView, status_code=202)
    def retry(
        run_id: UUID,
        owner: Owner,
        rt: RuntimeDependency,
        response: Response,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    ):
        parent = rt.store.get_run(run_id, owner.id)
        if parent.execution_status not in TERMINAL:
            raise StoreError(409, "run_active", "Cancel or finish the original run before retrying")
        body = RunCreate(
            asset_id=parent.asset_id,
            question=parent.question,
            audience=parent.audience,
            parent_run_id=parent.id,
        )
        return create_run(body, owner, rt, response, key)

    @app.get("/api/v1/runs/{run_id}/events/history", tags=["Events"], response_model=EventPage)
    def history(
        run_id: UUID,
        owner: Owner,
        rt: RuntimeDependency,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        include_draft: bool = False,
    ):
        run = rt.store.get_run(run_id, owner.id)
        records = rt.store.events(run_id, after, limit)
        return EventPage(
            run_id=run_id,
            items=[public_event(e, include_draft) for e in records],
            next_after=records[-1].sequence if records else after,
            terminal=run.execution_status in TERMINAL,
        )

    @app.get(
        "/api/v1/runs/{run_id}/events",
        tags=["Events"],
        response_class=StreamingResponse,
        responses={
            200: {
                "content": {"text/event-stream": {}},
                "description": "SSE; dùng /events/history nếu Swagger chờ stream không kết thúc.",
            }
        },
    )
    async def stream_events(
        run_id: UUID,
        request: Request,
        owner: Owner,
        rt: RuntimeDependency,
        after: int = Query(0, ge=0),
        include_draft: bool = False,
        last_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
    ):
        await run_in_threadpool(rt.store.get_run, run_id, owner.id)
        cursor = max(after, last_id or 0)

        async def stream():
            position = cursor
            heartbeat_at = 0.0
            while not await request.is_disconnected():
                # Recheck expiry/revocation on long-lived connections.
                try:
                    auth = request.headers.get("authorization", "").split(" ", 1)[-1]
                    await run_in_threadpool(rt.store.authenticate, auth)
                except StoreError:
                    yield "event: session.expired\ndata: {}\n\n"
                    return
                records = await run_in_threadpool(rt.store.events, run_id, position, 100)
                for record in records:
                    payload = public_event(record, include_draft).model_dump(mode="json")
                    yield f"id: {record.sequence}\nevent: {record.event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    position = record.sequence
                current = await run_in_threadpool(rt.store.get_run, run_id, owner.id)
                if current.execution_status in TERMINAL and position >= current.event_count:
                    return
                if time.monotonic() - heartbeat_at >= 10:
                    yield ": heartbeat\n\n"
                    heartbeat_at = time.monotonic()
                await asyncio.sleep(settings.poll_seconds)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/runs/{run_id}/result", tags=["Results"], response_model=ResultView)
    def result(
        run_id: UUID, owner: Owner, rt: RuntimeDependency, include_intermediate: bool = False
    ):
        return result_view(completed_run(rt, run_id, owner.id), include_intermediate)

    @app.get("/api/v1/runs/{run_id}/sources", tags=["Results"], response_model=SourcesView)
    def sources(run_id: UUID, owner: Owner, rt: RuntimeDependency):
        run = rt.store.get_run(run_id, owner.id)
        records = rt.store.events(run_id, 0, 500)
        events = [e.payload for e in records if e.event.startswith("stage.")]
        payload = {**(run.result or {}), "events": events}
        return {"run_id": run.id, "items": collect_sources(payload)}

    @app.get("/api/v1/runs/{run_id}/steps", tags=["Results"], response_model=StepsView)
    def steps(run_id: UUID, owner: Owner, rt: RuntimeDependency, include_draft: bool = False):
        rt.store.get_run(run_id, owner.id)
        records = rt.store.events(run_id, 0, 500)
        events = [
            public_event(e, include_draft).data for e in records if e.event.startswith("stage.")
        ]
        return {"run_id": str(run_id), "items": stage_snapshots(events)}

    @app.get("/api/v1/runs/{run_id}/metrics", tags=["Results"], response_model=MetricsView)
    def metrics(run_id: UUID, owner: Owner, rt: RuntimeDependency):
        run = rt.store.get_run(run_id, owner.id)
        payload = run.result or {}
        return {
            "run_id": run.id,
            "model_mode": run.model_mode,
            "duration": payload.get("duration"),
            "usage": usage_summary(payload.get("calls", [])),
            "calls": payload.get("calls", []),
            "workflow_version": run.config_snapshot.get("workflow_version"),
            "config_hash": run.config_snapshot.get("config_hash"),
        }

    @app.get("/api/v1/runs/{run_id}/export", tags=["Results"])
    def export(
        run_id: UUID,
        owner: Owner,
        rt: RuntimeDependency,
        format: Annotated[str, Query(pattern="^(json|markdown)$")] = "json",
        include_intermediate: bool = False,
    ):
        run = completed_run(rt, run_id, owner.id)
        if format == "markdown":
            payload, media_type, extension = (
                markdown_report(run.result, include_intermediate=include_intermediate),
                "text/markdown",
                "md",
            )
            payload = f"Mode: {run.model_mode}\n\n" + payload
        else:
            payload = json.dumps(
                result_view(run, include_intermediate).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            media_type, extension = "application/json", "json"
        return Response(
            payload,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="heritage-{run.id}.{extension}"'
            },
        )

    @app.put("/api/v1/runs/{run_id}/bookmark", tags=["Feedback"], response_model=RunView)
    def bookmark(run_id: UUID, body: BookmarkBody, owner: Owner, rt: RuntimeDependency):
        with rt.db.session() as session:
            owned(session, Run, run_id, owner.id)
            session.execute(update(Run).where(Run.id == str(run_id)).values(bookmarked=body.saved))
        return run_view(rt.store.get_run(run_id, owner.id))

    @app.put("/api/v1/runs/{run_id}/feedback", tags=["Feedback"], response_model=FeedbackBody)
    @app.post("/api/v1/runs/{run_id}/feedback", tags=["Feedback"], response_model=FeedbackBody)
    def feedback(run_id: UUID, body: FeedbackBody, owner: Owner, rt: RuntimeDependency):
        with rt.db.session() as session:
            # Lock run to serialize concurrent upserts of its feedback.
            owned(session, Run, run_id, owner.id)
            session.execute(
                update(Run).where(Run.id == str(run_id)).values(bookmarked=Run.bookmarked)
            )
            record = session.get(Feedback, str(run_id))
            if record:
                record.rating, record.note, record.updated_at = body.rating, body.note, time.time()
            else:
                session.add(
                    Feedback(
                        run_id=str(run_id),
                        rating=body.rating,
                        note=body.note,
                        updated_at=time.time(),
                    )
                )
        return body

    @app.get("/api/v1/runs/{run_id}/feedback", tags=["Feedback"], response_model=FeedbackBody)
    def get_feedback(run_id: UUID, owner: Owner, rt: RuntimeDependency):
        with rt.db.session() as session:
            owned(session, Run, run_id, owner.id)
            record = session.get(Feedback, str(run_id))
            return (
                FeedbackBody(rating=record.rating, note=record.note) if record else FeedbackBody()
            )

    return app


app = create_app()
