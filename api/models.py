"""Application records; worker claims and events are persisted in the same database."""

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Payload = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class SessionToken(Base):
    __tablename__ = "api_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    last_seen: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Asset(Base):
    __tablename__ = "api_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_sessions.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)


class Run(Base):
    __tablename__ = "api_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_run_owner_idempotency"),
        Index("ix_runs_queue", "execution_status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_sessions.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("api_assets.id"))
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("api_runs.id"))
    request_id: Mapped[str | None] = mapped_column(String(36))
    question: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(20))
    profile: Mapped[str] = mapped_column(String(30))
    model_mode: Mapped[str] = mapped_column(String(10))
    execution_status: Mapped[str] = mapped_column(String(25), index=True)
    result_status: Mapped[str | None] = mapped_column(String(30))
    config_snapshot: Mapped[dict] = mapped_column(Payload)
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[dict | None] = mapped_column(Payload)
    error_type: Mapped[str | None] = mapped_column(String(80))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float)
    started_at: Mapped[float | None] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    worker_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[float | None] = mapped_column(Float)


class RunEventRecord(Base):
    __tablename__ = "api_run_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("api_runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(Payload)
    created_at: Mapped[float] = mapped_column(Float)


class Feedback(Base):
    __tablename__ = "api_feedback"
    run_id: Mapped[str] = mapped_column(ForeignKey("api_runs.id"), primary_key=True)
    rating: Mapped[str] = mapped_column(String(25))
    note: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[float] = mapped_column(Float)


class WorkerHeartbeat(Base):
    __tablename__ = "api_workers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    heartbeat_at: Mapped[float] = mapped_column(Float)


class ModelAttempt(Base):
    __tablename__ = "api_model_attempts"
    run_id: Mapped[str] = mapped_column(ForeignKey("api_runs.id"), primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_role: Mapped[str] = mapped_column(String(40))
    actual_provider: Mapped[str] = mapped_column(String(40))
    model_used: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20))
    retry: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    duration: Mapped[float | None] = mapped_column(Float)
    error_type: Mapped[str | None] = mapped_column(String(80))
    usage: Mapped[dict | None] = mapped_column(Payload)
