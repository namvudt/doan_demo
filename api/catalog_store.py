"""Transactional catalog persistence, independent from guest/run ownership."""

import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from api.catalog_schemas import HeritageWrite
from api.models import (
    HeritageContentSource,
    HeritageSite,
    HeritageSiteInformation,
    HeritageSiteMedia,
)
from api.store import StoreError
from api.views import timestamp


def search_key(value):
    return unicodedata.normalize("NFC", value).casefold().strip()


def catalog_views(session, records):
    identifiers = [record.id for record in records]
    if not identifiers:
        return []
    information = {
        item.heritage_id: item
        for item in session.scalars(
            select(HeritageSiteInformation).where(
                HeritageSiteInformation.heritage_id.in_(identifiers)
            )
        )
    }
    media, sources = defaultdict(list), defaultdict(list)
    for item in session.scalars(
        select(HeritageSiteMedia)
        .where(HeritageSiteMedia.heritage_id.in_(identifiers))
        .order_by(HeritageSiteMedia.position, HeritageSiteMedia.id)
    ):
        media[item.heritage_id].append(
            {
                "media_id": item.id,
                "kind": "image",
                "url": f"/api/v1/heritages/{item.heritage_id}/media/{item.id}/content",
                "alt": item.alt,
                "caption": item.caption,
                "verified": item.verified,
            }
        )
    for item in session.scalars(
        select(HeritageContentSource)
        .where(HeritageContentSource.heritage_id.in_(identifiers))
        .order_by(HeritageContentSource.position, HeritageContentSource.id)
    ):
        sources[item.heritage_id].append(
            {
                "source_id": item.id,
                "title": item.title,
                "publisher": item.publisher,
                "url": item.url,
                "kind": item.kind,
                "summary": item.summary,
                "verified": item.verified,
                "verification_note": item.verification_note,
                "index_status": item.index_status,
            }
        )
    result = []
    for record in records:
        info = information.get(record.id)
        location = None
        if info and info.latitude is not None and info.longitude is not None:
            location = {
                "latitude": info.latitude,
                "longitude": info.longitude,
                "verification_status": info.verification_status,
                "verification_note": info.verification_note,
                "source_id": info.source_id,
            }
        result.append(
            {
                "heritage_id": record.id,
                "name": record.name,
                "slug": record.slug,
                "province": record.province,
                "address": record.address,
                "category": record.category,
                "period": record.period,
                "summary": record.summary,
                "historical_information": info.historical_information if info else "",
                "cultural_information": info.cultural_information if info else "",
                "tags": record.tags,
                "location": location,
                "media": media[record.id],
                "information_sources": sources[record.id],
                "content_status": record.content_status,
                "illustrative": record.illustrative,
                "version": record.version,
                "created_at": timestamp(record.created_at),
                "updated_at": timestamp(record.updated_at),
            }
        )
    return result


class CatalogStore:
    def __init__(self, database):
        self.db = database

    def list_public(
        self, *, q="", province=None, category=None, has_location=None, limit=100, offset=0
    ):
        conditions = [HeritageSite.content_status == "published"]
        if query := search_key(q):
            conditions.append(HeritageSite.search_text.contains(query, autoescape=True))
        if province:
            conditions.append(HeritageSite.province == province)
        if category:
            conditions.append(HeritageSite.category == category)
        if has_location is not None:
            located = select(HeritageSiteInformation.heritage_id).where(
                HeritageSiteInformation.latitude.is_not(None),
                HeritageSiteInformation.longitude.is_not(None),
            )
            conditions.append(
                HeritageSite.id.in_(located) if has_location else HeritageSite.id.not_in(located)
            )
        with self.db.session() as session:
            total = session.scalar(
                select(func.count()).select_from(HeritageSite).where(*conditions)
            )
            records = list(
                session.scalars(
                    select(HeritageSite)
                    .where(*conditions)
                    .order_by(HeritageSite.name, HeritageSite.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            items = catalog_views(session, records)
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }

    def get_public(self, identifier):
        with self.db.session() as session:
            record = session.get(HeritageSite, identifier)
            if record is None or record.content_status != "published":
                raise StoreError(404, "heritage_not_found", "Heritage was not found")
            return catalog_views(session, [record])[0]

    @staticmethod
    def _write(session, body, identifier, *, expected_version=None):
        now = time.time()
        values = {
            "name": body.name,
            "slug": body.slug,
            "province": body.province,
            "address": body.address,
            "category": body.category,
            "period": body.period,
            "summary": body.summary,
            "tags": body.tags,
            "search_text": search_key(
                " ".join([body.name, body.province, body.summary, *body.tags])
            ),
            "content_status": body.content_status,
            "illustrative": body.illustrative,
            "updated_at": now,
        }
        if expected_version is None:
            if session.get(HeritageSite, identifier) is not None:
                raise StoreError(409, "heritage_exists", "Heritage identifier already exists")
            record = HeritageSite(id=identifier, version=1, created_at=now, **values)
            session.add(record)
            session.flush()
        else:
            changed = session.execute(
                update(HeritageSite)
                .where(HeritageSite.id == identifier, HeritageSite.version == expected_version)
                .values(**values, version=expected_version + 1)
            )
            if not changed.rowcount:
                if session.get(HeritageSite, identifier) is None:
                    raise StoreError(404, "heritage_not_found", "Heritage was not found")
                raise StoreError(
                    409, "heritage_version_conflict", "Reload the current heritage before editing"
                )
            record = session.get(HeritageSite, identifier, populate_existing=True)
            for model in (HeritageSiteMedia, HeritageContentSource, HeritageSiteInformation):
                session.execute(delete(model).where(model.heritage_id == identifier))
            session.flush()
        location = body.location
        session.add(
            HeritageSiteInformation(
                heritage_id=identifier,
                historical_information=body.historical_information,
                cultural_information=body.cultural_information,
                latitude=location.latitude if location else None,
                longitude=location.longitude if location else None,
                verification_status=location.verification_status if location else None,
                verification_note=location.verification_note if location else "",
                source_id=location.source_id if location else None,
            )
        )
        for position, media in enumerate(body.media):
            session.add(
                HeritageSiteMedia(
                    id=media.media_id,
                    heritage_id=identifier,
                    storage_key=media.storage_key,
                    alt=media.alt,
                    caption=media.caption,
                    verified=media.verified,
                    position=position,
                )
            )
        for position, source in enumerate(body.information_sources):
            session.add(
                HeritageContentSource(
                    id=source.source_id,
                    heritage_id=identifier,
                    position=position,
                    **source.model_dump(exclude={"source_id"}),
                )
            )
        session.flush()
        return catalog_views(session, [record])[0]

    def create(self, body, *, actor="operations"):
        from api.content_store import audit

        try:
            with self.db.session() as session:
                result = self._write(session, body, body.heritage_id or str(uuid4()))
                audit(
                    session,
                    result["heritage_id"],
                    actor,
                    "heritage.create",
                    result["heritage_id"],
                    current=result,
                )
                return result
        except IntegrityError:
            raise StoreError(
                409, "heritage_conflict", "A catalog identifier or slug already exists"
            ) from None

    def replace(self, identifier, body, *, actor="operations"):
        from api.content_store import audit

        if body.heritage_id is not None and body.heritage_id != identifier:
            raise StoreError(
                409, "heritage_identifier_conflict", "Body and path identifiers must match"
            )
        if body.version is None:
            raise StoreError(
                428, "heritage_version_required", "Supply the version read before editing"
            )
        try:
            with self.db.session() as session:
                previous_record = session.get(HeritageSite, identifier)
                previous = catalog_views(session, [previous_record])[0] if previous_record else None
                result = self._write(session, body, identifier, expected_version=body.version)
                audit(
                    session,
                    identifier,
                    actor,
                    "heritage.replace",
                    identifier,
                    previous=previous,
                    current=result,
                )
                return result
        except IntegrityError:
            raise StoreError(
                409, "heritage_conflict", "A catalog identifier or slug already exists"
            ) from None

    def upsert_seed(self, payloads, *, replace=False):
        """Trusted CLI import: validate all records, skip existing IDs unless explicitly replaced."""
        bodies = [
            HeritageWrite.model_validate(
                {
                    key: value
                    for key, value in payload.items()
                    if key not in {"created_at", "updated_at"}
                }
            )
            for payload in payloads
        ]
        result = {"created": 0, "updated": 0, "skipped": 0}
        try:
            with self.db.session() as session:
                for body in bodies:
                    identifier = body.heritage_id
                    if not identifier:
                        raise ValueError("Seed records require stable heritage_id values")
                    existing = session.get(HeritageSite, identifier)
                    if existing is not None and not replace:
                        result["skipped"] += 1
                        continue
                    self._write(
                        session,
                        body,
                        identifier,
                        expected_version=existing.version if existing else None,
                    )
                    result["updated" if existing else "created"] += 1
        except IntegrityError:
            raise StoreError(
                409, "heritage_conflict", "Seed contains conflicting catalog identifiers or slugs"
            ) from None
        return result

    def media_path(self, identifier, media_id, directory, uploaded_directory=None):
        with self.db.session() as session:
            media = session.scalar(
                select(HeritageSiteMedia)
                .join(HeritageSite, HeritageSite.id == HeritageSiteMedia.heritage_id)
                .where(
                    HeritageSite.id == identifier,
                    HeritageSite.content_status == "published",
                    HeritageSiteMedia.id == media_id,
                )
            )
            if media is None:
                raise StoreError(404, "heritage_media_not_found", "Catalog image was not found")
            directories = [directory] + ([uploaded_directory] if uploaded_directory else [])
            for directory in directories:
                root = Path(directory).resolve()
                path = (root / media.storage_key).resolve()
                if path.parent == root and path.is_file():
                    return path
            raise StoreError(404, "heritage_media_not_found", "Catalog image was not found")
