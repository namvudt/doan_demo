"""Distinguish judge-only child runs from full workflow runs."""

import sqlalchemy as sa
from alembic import op

revision = "0004_review_runs"
down_revision = "0003_response_diagnostics"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "api_runs", sa.Column("run_kind", sa.String(10), nullable=False, server_default="full")
    )


def downgrade():
    op.drop_column("api_runs", "run_kind")
