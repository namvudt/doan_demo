"""Stable account principals, device sessions and conversation resources."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_accounts_product"
down_revision = "0006_merge_evidence_catalog"
branch_labels = None
depends_on = None


def upgrade():
    payload = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id", sa.String(36), sa.ForeignKey("api_sessions.id"), nullable=False, unique=True
        ),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.CheckConstraint("role IN ('user','editor','admin')", name="ck_account_role"),
    )
    op.create_table(
        "account_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("refresh_expires_at", sa.Float(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_account_sessions_account_id", "account_sessions", ["account_id"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_table(
        "product_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36)),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("metadata_json", payload, nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("api_sessions.id"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False),
        sa.Column("memory_cleared_at", sa.Float(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("next_turn", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_conversation_owner_updated", "chat_conversations", ["owner_id", "updated_at"]
    )
    op.create_table(
        "chat_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("api_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("conversation_id", "position", name="uq_conversation_turn_position"),
    )
    op.create_index("ix_chat_turns_conversation_id", "chat_turns", ["conversation_id"])
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "turn_id",
            sa.String(36),
            sa.ForeignKey("chat_turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provenance", payload, nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("turn_id", "role", name="uq_turn_message_role"),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_chat_message_role"),
    )
    op.create_index("ix_chat_messages_turn_id", "chat_messages", ["turn_id"])
    op.create_table(
        "heritage_favorites",
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("api_sessions.id"), primary_key=True),
        sa.Column(
            "heritage_id",
            sa.String(80),
            sa.ForeignKey("heritage_sites.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade():
    for name in (
        "heritage_favorites",
        "chat_messages",
        "chat_turns",
        "chat_conversations",
        "product_audit",
        "auth_rate_limits",
        "account_sessions",
        "accounts",
    ):
        op.drop_table(name)
