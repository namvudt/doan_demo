"""Account identity and product conversations, separate from workflow run ancestry."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base, Payload


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("role IN ('user','editor','admin')", name="ck_account_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_sessions.id"), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    disabled: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class AccountSession(Base):
    __tablename__ = "account_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    refresh_expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(Boolean)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[float] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer)


class ProductAudit(Base):
    __tablename__ = "product_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[dict] = mapped_column(Payload)
    created_at: Mapped[float] = mapped_column(Float)


class Conversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (Index("ix_conversation_owner_updated", "owner_id", "updated_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_sessions.id"))
    title: Mapped[str] = mapped_column(String(160))
    memory_enabled: Mapped[bool] = mapped_column(Boolean)
    memory_cleared_at: Mapped[float] = mapped_column(Float)
    archived: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer)
    next_turn: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class ConversationTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_conversation_turn_position"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("api_runs.id", ondelete="CASCADE"), unique=True)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)


class ConversationMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("turn_id", "role", name="uq_turn_message_role"),
        CheckConstraint("role IN ('user','assistant')", name="ck_chat_message_role"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("chat_turns.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(Payload)
    created_at: Mapped[float] = mapped_column(Float)


class HeritageFavorite(Base):
    __tablename__ = "heritage_favorites"
    owner_id: Mapped[str] = mapped_column(ForeignKey("api_sessions.id"), primary_key=True)
    heritage_id: Mapped[str] = mapped_column(
        ForeignKey("heritage_sites.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[float] = mapped_column(Float)
