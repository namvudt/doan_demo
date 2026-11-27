"""Editorial inputs never accept reviewer identity or automatically verified claims."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from api.catalog_schemas import Identifier
from api.schemas import Contract
from core.evidence import LocationHint
from core.schemas import SourceRecord


class SourceCreate(Contract):
    heritage_id: Identifier
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)
    publisher: str = Field(default="", max_length=240)
    text: str = Field(min_length=20, max_length=500000)

    @field_validator("url")
    @classmethod
    def https_url(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Source needs a public HTTPS URL without credentials")
        return value

    @field_validator("title", "text", mode="before")
    @classmethod
    def nonblank(cls, value):
        if not isinstance(value, str):
            return value
        if not value.strip():
            raise ValueError("Content must not be blank")
        return value.strip()


class SourceIngest(Contract):
    heritage_id: Identifier
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=300)


class RevisionBody(Contract):
    version: int = Field(ge=1)


class SourceRevision(RevisionBody):
    text: str = Field(min_length=20, max_length=500000)

    @field_validator("text", mode="before")
    @classmethod
    def nonblank(cls, value):
        if not isinstance(value, str):
            return value
        if not value.strip():
            raise ValueError("Content must not be blank")
        return value.strip()


class SourceReview(RevisionBody):
    attestation: Literal["reviewed_against_source"]
    note: str = Field(min_length=10, max_length=5000)

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value):
        return value.strip() if isinstance(value, str) else value


class EntityBindingWrite(RevisionBody):
    entity_id: str = Field(min_length=1, max_length=120)
    parent_heritage_id: Identifier | None = None
    note: str = Field(min_length=5, max_length=3000)

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value):
        return value.strip() if isinstance(value, str) else value


class SourceVersionView(Contract):
    version_id: str
    revision: int
    text: str | None
    content_hash: str
    status: Literal["draft", "reviewed", "published", "archived"]
    created_by: str
    created_at: datetime
    retrieved_at: datetime | None
    reviewer: str | None
    review_note: str
    reviewed_at: datetime | None
    published_at: datetime | None


class SourceView(Contract):
    source_id: str
    heritage_id: str
    title: str
    url: str
    publisher: str
    version: int
    created_at: datetime
    updated_at: datetime
    versions: list[SourceVersionView]


class SourcePage(Contract):
    items: list[SourceView]
    total: int
    limit: int
    offset: int
    has_more: bool


class HeritageContextView(Contract):
    heritage_id: str
    heritage_version: int
    canonical_entity_id: str | None
    parent_heritage_id: str | None
    location_hint: LocationHint
    verification_note: str


class PublishedSourcesView(Contract):
    items: list[SourceRecord]


class AuditEntry(Contract):
    audit_id: str
    actor: str
    action: str
    resource_id: str
    details: dict
    created_at: datetime


class AuditPage(Contract):
    items: list[AuditEntry]
    limit: int
    offset: int


class MediaEditView(Contract):
    media_id: str
    heritage_version: int


class ArchivedHeritageView(Contract):
    heritage_id: str
    version: int
    content_status: Literal["draft"]
