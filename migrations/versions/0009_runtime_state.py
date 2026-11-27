"""Private durable node snapshots and explicit run-retention state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_runtime_state"
down_revision = "0008_content_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("api_runs", sa.Column("deleted_at", sa.Float(), nullable=True))
    op.add_column(
        "api_runs", sa.Column("recovery_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_index("ix_api_runs_deleted_at", "api_runs", ["deleted_at"])
    op.create_table(
        "api_node_checkpoints",
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("api_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("node", sa.String(40), primary_key=True),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "api_recovery_requests",
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("api_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("recovery_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade():
    op.drop_table("api_recovery_requests")
    op.drop_table("api_node_checkpoints")
    op.drop_index("ix_api_runs_deleted_at", table_name="api_runs")
    op.drop_column("api_runs", "recovery_count")
    op.drop_column("api_runs", "deleted_at")
