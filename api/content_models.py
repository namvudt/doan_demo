"""Versioned editorial sources and explicit catalog/entity bindings."""

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base, Payload


class ContentDocument(Base):
    __tablename__ = "content_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    heritage_id: Mapped[str] = mapped_column(ForeignKey("heritage_sites.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(2048))
    publisher: Mapped[str] = mapped_column(String(240))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uq_content_document_revision"),
        CheckConstraint(
            "status IN ('draft','reviewed','published','archived')",
            name="ck_content_version_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("content_documents.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[float] = mapped_column(Float)
    retrieved_at: Mapped[float | None] = mapped_column(Float)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    review_note: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[float | None] = mapped_column(Float)
    published_at: Mapped[float | None] = mapped_column(Float)


class EntityBinding(Base):
    __tablename__ = "heritage_entity_bindings"
    heritage_id: Mapped[str] = mapped_column(ForeignKey("heritage_sites.id"), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(120), unique=True)
    parent_heritage_id: Mapped[str | None] = mapped_column(ForeignKey("heritage_sites.id"))
    note: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[float] = mapped_column(Float)


class EditorialAudit(Base):
    __tablename__ = "editorial_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    heritage_id: Mapped[str] = mapped_column(ForeignKey("heritage_sites.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(Payload)
    created_at: Mapped[float] = mapped_column(Float)
