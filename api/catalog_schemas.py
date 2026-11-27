"""Public catalog metadata, deliberately separate from retrieved AI evidence."""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from api.schemas import Contract

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")]
ChildIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")]
Category = Literal["monument", "temple", "museum", "archaeology"]


class HeritageLocation(Contract):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    verification_status: Literal["illustrative", "unverified", "verified"] = "unverified"
    verification_note: str = Field(default="", max_length=3000)
    source_id: ChildIdentifier | None = None


class HeritageMediaWrite(Contract):
    media_id: ChildIdentifier
    kind: Literal["image"] = "image"
    storage_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.(?:jpg|jpeg|png|webp)$")
    alt: str = Field(default="", max_length=500)
    caption: str = Field(default="", max_length=5000)
    verified: bool = False


class HeritageMediaView(Contract):
    media_id: str
    kind: Literal["image"] = "image"
    url: str
    alt: str
    caption: str
    verified: bool


class HeritageInformationSource(Contract):
    source_id: ChildIdentifier
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(default="", max_length=240)
    url: str = Field(min_length=1, max_length=2048)
    kind: Literal["official", "unesco", "reference", "map"] = "reference"
    summary: str = Field(default="", max_length=10000)
    verified: bool = False
    verification_note: str = Field(default="", max_length=3000)
    index_status: Literal["not_indexed"] = "not_indexed"

    @field_validator("url")
    @classmethod
    def public_source_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
            raise ValueError("A source needs a public HTTP(S) URL without credentials")
        return value


class HeritageWrite(Contract):
    heritage_id: Identifier | None = None
    name: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    province: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=500)
    category: Category
    period: str = Field(default="", max_length=240)
    summary: str = Field(default="", max_length=10000)
    historical_information: str = Field(default="", max_length=50000)
    cultural_information: str = Field(default="", max_length=50000)
    tags: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=40
    )
    location: HeritageLocation | None = None
    media: list[HeritageMediaWrite] = Field(default_factory=list, max_length=30)
    information_sources: list[HeritageInformationSource] = Field(
        default_factory=list, max_length=100
    )
    content_status: Literal["draft", "published"] = "draft"
    illustrative: bool = False
    version: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def provenance_and_identifiers(self):
        for records, key in ((self.media, "media_id"), (self.information_sources, "source_id")):
            values = [getattr(record, key) for record in records]
            if len(set(values)) != len(values):
                raise ValueError("Child identifiers must be unique")
        if self.location and self.location.source_id:
            source = next(
                (
                    item
                    for item in self.information_sources
                    if item.source_id == self.location.source_id
                ),
                None,
            )
            if source is None:
                raise ValueError(
                    "Location provenance must reference an attached information source"
                )
        if self.location and self.location.verification_status == "verified":
            if self.illustrative or not self.location.verification_note.strip():
                raise ValueError("Verified coordinates require non-illustrative provenance")
            source = next(
                (
                    item
                    for item in self.information_sources
                    if item.source_id == self.location.source_id
                ),
                None,
            )
            if source is None or not source.verified:
                raise ValueError("Verified coordinates require a verified source")
        return self


class HeritageView(Contract):
    heritage_id: str
    name: str
    slug: str
    province: str
    address: str
    category: Category
    period: str
    summary: str
    historical_information: str
    cultural_information: str
    tags: list[str]
    location: HeritageLocation | None
    media: list[HeritageMediaView]
    information_sources: list[HeritageInformationSource]
    content_status: Literal["draft", "published"]
    illustrative: bool
    version: int
    created_at: datetime
    updated_at: datetime


class HeritagePage(Contract):
    items: list[HeritageView]
    total: int
    limit: int
    offset: int
    has_more: bool
