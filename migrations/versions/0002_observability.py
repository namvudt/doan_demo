"""Request correlation and durable per-attempt telemetry (no prompts/credentials)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_observability"
down_revision = "0001_api_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("api_runs", sa.Column("request_id", sa.String(36)))
    op.create_table(
        "api_model_attempts",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("api_runs.id"), primary_key=True),
        sa.Column("attempt", sa.Integer(), primary_key=True),
        sa.Column("agent_role", sa.String(40), nullable=False),
        sa.Column("actual_provider", sa.String(40), nullable=False),
        sa.Column("model_used", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("retry", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float()),
        sa.Column("duration", sa.Float()),
        sa.Column("error_type", sa.String(80)),
        sa.Column("usage", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
    )


def downgrade():
    op.drop_table("api_model_attempts")
    op.drop_column("api_runs", "request_id")
