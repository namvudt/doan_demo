"""Persistent sessions, normalized assets, job queue, events and feedback."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_api_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    payload = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "api_workers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("heartbeat_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "api_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("last_seen", sa.Float(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "api_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("api_sessions.id"), nullable=False),
        sa.Column("storage_key", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_api_assets_owner_id", "api_assets", ["owner_id"])
    op.create_table(
        "api_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("api_sessions.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("api_assets.id"), nullable=False),
        sa.Column("parent_run_id", sa.String(36), sa.ForeignKey("api_runs.id")),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("profile", sa.String(30), nullable=False),
        sa.Column("model_mode", sa.String(10), nullable=False),
        sa.Column("execution_status", sa.String(25), nullable=False),
        sa.Column("result_status", sa.String(30)),
        sa.Column("config_snapshot", payload, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("result", payload),
        sa.Column("error_type", sa.String(80)),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("bookmarked", sa.Boolean(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("started_at", sa.Float()),
        sa.Column("finished_at", sa.Float()),
        sa.Column("worker_token", sa.String(36)),
        sa.Column("lease_expires_at", sa.Float()),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_run_owner_idempotency"),
    )
    op.create_index("ix_api_runs_owner_id", "api_runs", ["owner_id"])
    op.create_index("ix_api_runs_execution_status", "api_runs", ["execution_status"])
    op.create_index("ix_runs_queue", "api_runs", ["execution_status", "created_at"])
    op.create_table(
        "api_run_events",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("api_runs.id"), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("payload", payload, nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "api_feedback",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("api_runs.id"), primary_key=True),
        sa.Column("rating", sa.String(25), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )


def downgrade():
    for name in (
        "api_feedback",
        "api_run_events",
        "api_runs",
        "api_assets",
        "api_sessions",
        "api_workers",
    ):
        op.drop_table(name)
