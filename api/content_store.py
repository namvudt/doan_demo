"""Transactional publication with immutable source text and provenance."""

import hashlib
import time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from api.content_models import ContentDocument, ContentVersion, EditorialAudit, EntityBinding
from api.models import HeritageSite, HeritageSiteMedia
from api.store import StoreError
from api.views import timestamp
from core.entities import EntityCatalog, mentions
from core.evidence import normalized_text
from core.schemas import SourceRecord
from core.search import HeritageSearchEngine, relevant_passage


def _heritage(session, identifier, *, published=False):
    record = session.get(HeritageSite, identifier)
    if record is None or (published and record.content_status != "published"):
        raise StoreError(404, "heritage_not_found", "Heritage was not found")
    return record


def _document(session, identifier):
    record = session.get(ContentDocument, identifier)
    if record is None:
        raise StoreError(404, "source_not_found", "Content source was not found")
    return record


def _advance(session, document, expected):
    changed = session.execute(
        update(ContentDocument)
        .where(ContentDocument.id == document.id, ContentDocument.version == expected)
        .values(version=expected + 1, updated_at=time.time())
    )
    if not changed.rowcount:
        raise StoreError(409, "source_version_conflict", "Reload the source before editing")
    session.refresh(document)


def audit(session, heritage_id, actor, action, resource_id, **details):
    session.add(
        EditorialAudit(
            id=str(uuid4()),
            heritage_id=heritage_id,
            actor=actor,
            action=action,
            resource_id=resource_id,
            details=jsonable_encoder(details),
            created_at=time.time(),
        )
    )


def source_view(session, document, *, include_text=True, versions=None):
    if versions is None:
        query = (
            select(ContentVersion)
            .where(ContentVersion.document_id == document.id)
            .order_by(ContentVersion.revision.desc())
        )
        if not include_text:
            query = query.options(defer(ContentVersion.text))
        versions = list(session.scalars(query))
    return {
        "source_id": document.id,
        "heritage_id": document.heritage_id,
        "title": document.title,
        "url": document.url,
        "publisher": document.publisher,
        "version": document.version,
        "created_at": timestamp(document.created_at),
        "updated_at": timestamp(document.updated_at),
        "versions": [
            {
                "version_id": item.id,
                "revision": item.revision,
                "text": item.text if include_text else None,
                "content_hash": item.content_hash,
                "status": item.status,
                "created_by": item.created_by,
                "created_at": timestamp(item.created_at),
                "retrieved_at": timestamp(item.retrieved_at) if item.retrieved_at else None,
                "reviewer": item.reviewer,
                "review_note": item.review_note,
                "reviewed_at": timestamp(item.reviewed_at) if item.reviewed_at else None,
                "published_at": timestamp(item.published_at) if item.published_at else None,
            }
            for item in versions
        ],
    }


class ContentStore:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def _version(session, document, text, actor, *, retrieved_at=None):
        revision = (
            session.scalar(
                select(func.max(ContentVersion.revision)).where(
                    ContentVersion.document_id == document.id
                )
            )
            or 0
        ) + 1
        record = ContentVersion(
            id=str(uuid4()),
            document_id=document.id,
            revision=revision,
            text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            status="draft",
            created_by=actor,
            created_at=time.time(),
            retrieved_at=retrieved_at,
            review_note="",
        )
        session.add(record)
        session.flush()
        audit(session, document.heritage_id, actor, "source.draft_created", record.id)
        return record

    def create(self, body, actor, *, retrieved_at=None):
        with self.db.session() as session:
            _heritage(session, body.heritage_id)
            now = time.time()
            document = ContentDocument(
                id=str(uuid4()),
                heritage_id=body.heritage_id,
                title=body.title,
                url=body.url,
                publisher=body.publisher,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(document)
            session.flush()
            self._version(session, document, body.text, actor, retrieved_at=retrieved_at)
            return source_view(session, document)

    def list(self, *, heritage_id=None, limit=50, offset=0):
        conditions = [ContentDocument.heritage_id == heritage_id] if heritage_id else []
        with self.db.session() as session:
            total = session.scalar(
                select(func.count()).select_from(ContentDocument).where(*conditions)
            )
            records = list(
                session.scalars(
                    select(ContentDocument)
                    .where(*conditions)
                    .order_by(ContentDocument.created_at.desc(), ContentDocument.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            versions = defaultdict(list)
            for item in session.scalars(
                select(ContentVersion)
                .options(defer(ContentVersion.text))
                .where(ContentVersion.document_id.in_([record.id for record in records]))
                .order_by(ContentVersion.revision.desc())
            ):
                versions[item.document_id].append(item)
            return {
                "items": [
                    source_view(session, record, include_text=False, versions=versions[record.id])
                    for record in records
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            }

    def get(self, identifier):
        with self.db.session() as session:
            return source_view(session, _document(session, identifier))

    def add_version(self, identifier, body, actor):
        with self.db.session() as session:
            document = _document(session, identifier)
            _advance(session, document, body.version)
            self._version(session, document, body.text, actor)
            return source_view(session, document)

    def transition(self, identifier, version_id, expected, actor, action, note=""):
        with self.db.session() as session:
            document = _document(session, identifier)
            _advance(session, document, expected)
            version = session.get(ContentVersion, version_id)
            if version is None or version.document_id != identifier:
                raise StoreError(404, "source_version_not_found", "Source version was not found")
            if hashlib.sha256(version.text.encode()).hexdigest() != version.content_hash:
                raise StoreError(409, "source_hash_conflict", "Source content hash changed")
            if action == "review":
                if version.status != "draft":
                    raise StoreError(409, "source_state_conflict", "Only a draft can be reviewed")
                version.status, version.reviewer, version.review_note = "reviewed", actor, note
                version.reviewed_at = time.time()
            elif action == "publish":
                if version.status != "reviewed" or not version.reviewer or not version.reviewed_at:
                    raise StoreError(
                        409, "source_review_required", "A reviewed version is required"
                    )
                _heritage(session, document.heritage_id, published=True)
                # The document row's revision serializes all publishers. Exactly
                # one source revision is current, while older text stays intact.
                session.execute(
                    update(ContentVersion)
                    .where(
                        ContentVersion.document_id == identifier,
                        ContentVersion.status == "published",
                    )
                    .values(status="archived")
                )
                version.status, version.published_at = "published", time.time()
            elif action == "withdraw":
                if version.status != "published":
                    raise StoreError(
                        409, "source_state_conflict", "Only a publication can be withdrawn"
                    )
                version.status = "archived"
            else:
                raise ValueError("Unknown source transition")
            audit(session, document.heritage_id, actor, "source." + action, version_id)
            session.flush()
            return source_view(session, document)

    def bind_entity(self, heritage_id, body, actor, *, entity_catalog=None):
        catalog = EntityCatalog(entity_catalog) if entity_catalog else EntityCatalog()
        entity = catalog.entities.get(body.entity_id)
        if entity is None:
            raise StoreError(422, "entity_unknown", "Choose a registered canonical entity")
        try:
            with self.db.session() as session:
                site = _heritage(session, heritage_id)
                changed = session.execute(
                    update(HeritageSite)
                    .where(HeritageSite.id == heritage_id, HeritageSite.version == body.version)
                    .values(version=body.version + 1, updated_at=time.time())
                )
                if not changed.rowcount:
                    raise StoreError(
                        409, "heritage_version_conflict", "Reload heritage before editing"
                    )
                children = session.scalars(
                    select(EntityBinding).where(EntityBinding.parent_heritage_id == heritage_id)
                )
                if any(
                    catalog.entities.get(child.entity_id, {}).get("parent_id") != body.entity_id
                    for child in children
                ):
                    raise StoreError(
                        422, "entity_children_mismatch", "Rebinding would invalidate a component"
                    )
                if body.parent_heritage_id:
                    _heritage(session, body.parent_heritage_id)
                    parent = session.get(EntityBinding, body.parent_heritage_id)
                    if (
                        body.parent_heritage_id == heritage_id
                        or parent is None
                        or entity.get("parent_id") != parent.entity_id
                    ):
                        raise StoreError(
                            422, "entity_parent_mismatch", "Canonical parent binding differs"
                        )
                elif entity.get("parent_id"):
                    raise StoreError(
                        422, "entity_parent_required", "Bind the component's parent first"
                    )
                binding = session.get(EntityBinding, heritage_id)
                if binding is None:
                    binding = EntityBinding(heritage_id=heritage_id, version=0)
                    session.add(binding)
                binding.entity_id = body.entity_id
                binding.parent_heritage_id = body.parent_heritage_id
                binding.note, binding.updated_by = body.note, actor
                binding.updated_at, binding.version = time.time(), binding.version + 1
                audit(session, heritage_id, actor, "entity.bind", body.entity_id)
                session.flush()
                session.refresh(site)
                return self._context(site, binding, catalog)
        except IntegrityError:
            raise StoreError(
                409, "entity_binding_conflict", "Entity is bound to another heritage"
            ) from None

    @staticmethod
    def _context(site, binding, catalog):
        entity = catalog.entities.get(binding.entity_id, {}) if binding else {}
        return {
            "heritage_id": site.id,
            "heritage_version": site.version,
            "canonical_entity_id": binding.entity_id if binding else None,
            "parent_heritage_id": binding.parent_heritage_id if binding else None,
            "location_hint": {"name": entity.get("name", site.name), "provenance": "user"},
            "verification_note": "Catalog selection is unverified context, not image evidence.",
        }

    def run_context(self, heritage_id, *, entity_catalog=None):
        catalog = EntityCatalog(entity_catalog) if entity_catalog else EntityCatalog()
        with self.db.session() as session:
            site = _heritage(session, heritage_id, published=True)
            return self._context(site, session.get(EntityBinding, heritage_id), catalog)

    def published_sources(self, *, heritage_id=None):
        conditions = [
            ContentVersion.status == "published",
            ContentVersion.reviewer.is_not(None),
            ContentVersion.reviewed_at.is_not(None),
            HeritageSite.content_status == "published",
        ]
        if heritage_id:
            conditions.append(ContentDocument.heritage_id == heritage_id)
        with self.db.session() as session:
            pairs = session.execute(
                select(ContentDocument, ContentVersion)
                .join(ContentVersion, ContentVersion.document_id == ContentDocument.id)
                .join(HeritageSite, HeritageSite.id == ContentDocument.heritage_id)
                .where(*conditions)
                .order_by(ContentDocument.id)
            )
            records = []
            for document, version in pairs:
                if hashlib.sha256(version.text.encode()).hexdigest() != version.content_hash:
                    continue
                records.append(
                    SourceRecord(
                        source_id="db_" + version.id,
                        title=document.title,
                        url=document.url,
                        type="web",
                        snippet=version.text,
                        revision_id=version.id,
                        content_hash=version.content_hash,
                        locator=f"chars:0:{len(version.text)}",
                        publisher=document.publisher,
                        retrieved_at=datetime.fromtimestamp(
                            version.retrieved_at or version.created_at, timezone.utc
                        ).isoformat(),
                        annotation_status="reviewed",
                        reviewer=version.reviewer,
                        reviewed_at=datetime.fromtimestamp(
                            version.reviewed_at, timezone.utc
                        ).isoformat(),
                    ).model_dump(mode="json")
                )
            return records

    def retrieval_revision(self):
        with self.db.session() as session:
            documents = list(
                session.execute(
                    select(ContentDocument.id, ContentDocument.version, HeritageSite.version)
                    .join(HeritageSite, HeritageSite.id == ContentDocument.heritage_id)
                    .order_by(ContentDocument.id)
                )
            )
            bindings = list(
                session.execute(
                    select(EntityBinding.heritage_id, EntityBinding.version).order_by(
                        EntityBinding.heritage_id
                    )
                )
            )
            return hashlib.sha256(repr((documents, bindings)).encode()).hexdigest()

    def audit_log(self, heritage_id, *, limit=50, offset=0):
        with self.db.session() as session:
            _heritage(session, heritage_id)
            rows = session.scalars(
                select(EditorialAudit)
                .where(EditorialAudit.heritage_id == heritage_id)
                .order_by(EditorialAudit.created_at.desc(), EditorialAudit.id)
                .limit(limit)
                .offset(offset)
            )
            return {
                "items": [
                    {
                        "audit_id": row.id,
                        "actor": row.actor,
                        "action": row.action,
                        "resource_id": row.resource_id,
                        "details": row.details,
                        "created_at": timestamp(row.created_at),
                    }
                    for row in rows
                ],
                "limit": limit,
                "offset": offset,
            }

    def add_media(self, heritage_id, expected, storage_key, actor, *, alt="", caption=""):
        with self.db.session() as session:
            _heritage(session, heritage_id)
            changed = session.execute(
                update(HeritageSite)
                .where(HeritageSite.id == heritage_id, HeritageSite.version == expected)
                .values(version=expected + 1, updated_at=time.time())
            )
            if not changed.rowcount:
                raise StoreError(409, "heritage_version_conflict", "Reload heritage before editing")
            count = session.scalar(
                select(func.count())
                .select_from(HeritageSiteMedia)
                .where(HeritageSiteMedia.heritage_id == heritage_id)
            )
            if count >= 30:
                raise StoreError(
                    409, "heritage_media_limit", "A heritage can have at most 30 images"
                )
            position = session.scalar(
                select(func.max(HeritageSiteMedia.position)).where(
                    HeritageSiteMedia.heritage_id == heritage_id
                )
            )
            identifier = str(uuid4())
            session.add(
                HeritageSiteMedia(
                    id=identifier,
                    heritage_id=heritage_id,
                    storage_key=storage_key,
                    alt=alt,
                    caption=caption,
                    verified=False,
                    position=(position if position is not None else -1) + 1,
                )
            )
            audit(session, heritage_id, actor, "media.upload", identifier)
            return {"media_id": identifier, "heritage_version": expected + 1}

    def replace_media(
        self, heritage_id, media_id, expected, storage_key, actor, *, alt="", caption=""
    ):
        with self.db.session() as session:
            _heritage(session, heritage_id)
            changed = session.execute(
                update(HeritageSite)
                .where(HeritageSite.id == heritage_id, HeritageSite.version == expected)
                .values(version=expected + 1, updated_at=time.time())
            )
            if not changed.rowcount:
                raise StoreError(409, "heritage_version_conflict", "Reload heritage before editing")
            media = session.get(HeritageSiteMedia, media_id)
            if media is None or media.heritage_id != heritage_id:
                raise StoreError(404, "heritage_media_not_found", "Catalog image was not found")
            previous = media.storage_key
            media.storage_key, media.alt, media.caption = storage_key, alt, caption
            media.verified = False
            audit(session, heritage_id, actor, "media.replace", media_id)
            return previous

    def remove_media(self, heritage_id, media_id, expected, actor):
        with self.db.session() as session:
            _heritage(session, heritage_id)
            changed = session.execute(
                update(HeritageSite)
                .where(HeritageSite.id == heritage_id, HeritageSite.version == expected)
                .values(version=expected + 1, updated_at=time.time())
            )
            if not changed.rowcount:
                raise StoreError(409, "heritage_version_conflict", "Reload heritage before editing")
            media = session.get(HeritageSiteMedia, media_id)
            if media is None or media.heritage_id != heritage_id:
                raise StoreError(404, "heritage_media_not_found", "Catalog image was not found")
            key = media.storage_key
            session.delete(media)
            audit(session, heritage_id, actor, "media.remove", media_id)
            return key

    def archive_heritage(self, heritage_id, expected, actor):
        with self.db.session() as session:
            _heritage(session, heritage_id)
            changed = session.execute(
                update(HeritageSite)
                .where(HeritageSite.id == heritage_id, HeritageSite.version == expected)
                .values(version=expected + 1, content_status="draft", updated_at=time.time())
            )
            if not changed.rowcount:
                raise StoreError(409, "heritage_version_conflict", "Reload heritage before editing")
            audit(session, heritage_id, actor, "heritage.archive", heritage_id)
            return {"heritage_id": heritage_id, "version": expected + 1, "content_status": "draft"}


def database_search_factory(
    database, *, policy, entity_catalog=None, bound_heritage_id=None, **engine_options
):
    """A zero-argument factory compatible with RunService's search injection."""

    class DatabaseSearch(HeritageSearchEngine):
        def curated_sources(self, query, *, entity_terms=()):
            tokens = set(normalized_text(query).split())
            ranked = []
            for source in ContentStore(database).published_sources(heritage_id=bound_heritage_id):
                if entity_terms and not mentions(
                    source["title"] + " " + source["snippet"], entity_terms
                ):
                    continue
                overlap = len(
                    tokens & set(normalized_text(source["title"] + " " + source["snippet"]).split())
                )
                if not overlap:
                    continue
                passage, locator = relevant_passage(
                    source["snippet"],
                    query,
                    self.policy.max_source_chars,
                    required_terms=() if mentions(source["title"], entity_terms) else entity_terms,
                )
                ranked.append((overlap, {**source, "snippet": passage, "locator": locator}))
            local = [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)]
            return (local + super().curated_sources(query, entity_terms=entity_terms))[
                : self.policy.max_results
            ]

    return lambda: DatabaseSearch(policy=policy, entity_catalog=entity_catalog, **engine_options)
