"""Human-controlled source publication, canonical bindings and catalog media."""

import time
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import requests
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import ValidationError

from api.content_schemas import (
    ArchivedHeritageView,
    AuditPage,
    EntityBindingWrite,
    HeritageContextView,
    MediaEditView,
    PublishedSourcesView,
    RevisionBody,
    SourceCreate,
    SourceIngest,
    SourcePage,
    SourceReview,
    SourceRevision,
    SourceView,
)
from api.content_store import ContentStore
from api.editorial_auth import editorial_dependency
from api.runtime import Runtime
from api.store import StoreError
from core.images import validate_image
from core.ingestion import fetch_source


def content_router(settings, *, runtime_dependency, principal_dependency, operations_security):
    router = APIRouter(prefix="/api/v1", tags=["Editorial"])
    runtime = Annotated[Runtime, Depends(runtime_dependency)]
    editor = Annotated[
        str,
        Depends(
            editorial_dependency(
                settings, runtime_dependency, principal_dependency, operations_security
            )
        ),
    ]

    @router.get("/operations/content-sources", response_model=SourcePage)
    def list_sources(
        rt: runtime,
        actor: editor,
        heritage_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return ContentStore(rt.db).list(heritage_id=heritage_id, limit=limit, offset=offset)

    @router.post("/operations/content-sources", response_model=SourceView, status_code=201)
    def create_source(body: SourceCreate, rt: runtime, actor: editor):
        _allowed_url(body.url, rt.config().accuracy.retrieval)
        return ContentStore(rt.db).create(body, actor)

    @router.post("/operations/content-sources/ingest", response_model=SourceView, status_code=201)
    def ingest_source(body: SourceIngest, rt: runtime, actor: editor):
        # Bounded operator action; downloaded content is ALWAYS a draft.
        with rt.db.session() as session:
            from api.content_store import _heritage

            _heritage(session, body.heritage_id)
        try:
            record = fetch_source(body.url, rt.config().accuracy.retrieval)
        except (ValueError, OSError, requests.RequestException):
            raise StoreError(
                422, "source_fetch_failed", "Source fetch failed validation or deadline"
            ) from None
        try:
            payload = SourceCreate(
                heritage_id=body.heritage_id,
                title=body.title or record["title"],
                url=record["url"],
                publisher=record.get("publisher") or "",
                text=record["snippet"],
            )
        except ValidationError:
            raise StoreError(
                422, "source_content_invalid", "Source text exceeds editorial limits"
            ) from None
        return ContentStore(rt.db).create(payload, actor, retrieved_at=time.time())

    @router.get("/operations/content-sources/{source_id}", response_model=SourceView)
    def get_source(source_id: str, rt: runtime, actor: editor):
        return ContentStore(rt.db).get(source_id)

    @router.post(
        "/operations/content-sources/{source_id}/versions",
        response_model=SourceView,
        status_code=201,
    )
    def add_version(source_id: str, body: SourceRevision, rt: runtime, actor: editor):
        return ContentStore(rt.db).add_version(source_id, body, actor)

    @router.post(
        "/operations/content-sources/{source_id}/versions/{version_id}/review",
        response_model=SourceView,
    )
    def review_version(
        source_id: str, version_id: str, body: SourceReview, rt: runtime, actor: editor
    ):
        return ContentStore(rt.db).transition(
            source_id, version_id, body.version, actor, "review", body.note
        )

    @router.post(
        "/operations/content-sources/{source_id}/versions/{version_id}/publish",
        response_model=SourceView,
    )
    def publish_version(
        source_id: str, version_id: str, body: RevisionBody, rt: runtime, actor: editor
    ):
        return ContentStore(rt.db).transition(source_id, version_id, body.version, actor, "publish")

    @router.post(
        "/operations/content-sources/{source_id}/versions/{version_id}/withdraw",
        response_model=SourceView,
    )
    def withdraw_version(
        source_id: str, version_id: str, body: RevisionBody, rt: runtime, actor: editor
    ):
        return ContentStore(rt.db).transition(
            source_id, version_id, body.version, actor, "withdraw"
        )

    @router.put(
        "/operations/heritages/{heritage_id}/entity-binding", response_model=HeritageContextView
    )
    def bind_entity(heritage_id: str, body: EntityBindingWrite, rt: runtime, actor: editor):
        return ContentStore(rt.db).bind_entity(
            heritage_id, body, actor, entity_catalog=rt.config().accuracy.entity_catalog
        )

    @router.get(
        "/heritages/{heritage_id}/context", response_model=HeritageContextView, tags=["Catalog"]
    )
    def heritage_context(heritage_id: str, rt: runtime):
        return ContentStore(rt.db).run_context(
            heritage_id, entity_catalog=rt.config().accuracy.entity_catalog
        )

    @router.get(
        "/heritages/{heritage_id}/sources", response_model=PublishedSourcesView, tags=["Catalog"]
    )
    def published_sources(heritage_id: str, rt: runtime):
        ContentStore(rt.db).run_context(heritage_id)
        records = ContentStore(rt.db).published_sources(heritage_id=heritage_id)
        # Public excerpts remain locatable in the immutable version.
        for record in records:
            record["snippet"] = record["snippet"][:4000]
            record["locator"] = f"chars:0:{len(record['snippet'])}"
        return {"items": records}

    @router.get("/operations/heritages/{heritage_id}/audit", response_model=AuditPage)
    def editorial_history(
        heritage_id: str,
        rt: runtime,
        actor: editor,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return ContentStore(rt.db).audit_log(heritage_id, limit=limit, offset=offset)

    async def upload(file, rt):
        raw = await file.read(min(settings.max_upload_bytes, rt.config().max_image_bytes) + 1)
        if len(raw) > min(settings.max_upload_bytes, rt.config().max_image_bytes):
            raise StoreError(413, "image_too_large", "Image exceeds upload limit")
        try:
            data = validate_image(raw, rt.config())
        except ValueError:
            raise StoreError(
                422, "image_invalid", "Upload a valid JPEG, PNG or WebP image"
            ) from None
        if len(data) > min(settings.max_upload_bytes, rt.config().max_image_bytes):
            raise StoreError(413, "image_too_large", "Normalized image exceeds upload limit")
        directory = settings.data_dir / "catalog-media"
        directory.mkdir(parents=True, exist_ok=True)
        key = "upload-" + str(uuid4()) + ".png"
        path = directory / key
        with path.open("xb") as target:
            target.write(data)
        return key, path

    @router.post(
        "/operations/heritages/{heritage_id}/media", response_model=MediaEditView, status_code=201
    )
    async def upload_media(
        heritage_id: str,
        rt: runtime,
        actor: editor,
        file: Annotated[UploadFile, File()],
        version: Annotated[int, Form(ge=1)],
        alt: Annotated[str, Form(max_length=500)] = "",
        caption: Annotated[str, Form(max_length=5000)] = "",
    ):
        key, path = await upload(file, rt)
        try:
            result = ContentStore(rt.db).add_media(
                heritage_id, version, key, actor, alt=alt, caption=caption
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return result

    @router.put(
        "/operations/heritages/{heritage_id}/media/{media_id}", response_model=MediaEditView
    )
    async def replace_media(
        heritage_id: str,
        media_id: str,
        rt: runtime,
        actor: editor,
        file: Annotated[UploadFile, File()],
        version: Annotated[int, Form(ge=1)],
        alt: Annotated[str, Form(max_length=500)] = "",
        caption: Annotated[str, Form(max_length=5000)] = "",
    ):
        key, path = await upload(file, rt)
        try:
            previous = ContentStore(rt.db).replace_media(
                heritage_id, media_id, version, key, actor, alt=alt, caption=caption
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        _remove_uploaded(previous, settings.data_dir / "catalog-media", rt.db)
        return {"media_id": media_id, "heritage_version": version + 1}

    @router.delete("/operations/heritages/{heritage_id}/media/{media_id}", status_code=204)
    def remove_media(
        heritage_id: str,
        media_id: str,
        version: Annotated[int, Query(ge=1)],
        rt: runtime,
        actor: editor,
    ):
        key = ContentStore(rt.db).remove_media(heritage_id, media_id, version, actor)
        _remove_uploaded(key, settings.data_dir / "catalog-media", rt.db)

    @router.post("/operations/heritages/{heritage_id}/archive", response_model=ArchivedHeritageView)
    def archive_heritage(heritage_id: str, body: RevisionBody, rt: runtime, actor: editor):
        return ContentStore(rt.db).archive_heritage(heritage_id, body.version, actor)

    return router


def _allowed_url(url, policy):
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    if not any(host == domain or host.endswith("." + domain) for domain in policy.allowed_domains):
        raise StoreError(422, "source_domain_disallowed", "Source domain is not allowlisted")


def _remove_uploaded(key, directory, database):
    from sqlalchemy import func, select

    from api.models import HeritageSiteMedia

    root = Path(directory).resolve()
    path = (root / key).resolve()
    if not key.startswith("upload-") or path.parent != root:
        return
    with database.session() as session:
        references = session.scalar(
            select(func.count())
            .select_from(HeritageSiteMedia)
            .where(HeritageSiteMedia.storage_key == key)
        )
    if not references:
        path.unlink(missing_ok=True)
