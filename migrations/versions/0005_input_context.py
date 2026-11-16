"""Persist typed continuation input separately from immutable parent results."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_input_context"
down_revision = "0004_review_runs"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL enforces VARCHAR length; SQLite stores strings without that limit.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("api_runs", "run_kind", existing_type=sa.String(10), type_=sa.String(20))
    op.add_column(
        "api_runs",
        sa.Column("input_context", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
    )


def downgrade():
    op.drop_column("api_runs", "input_context")
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("api_runs", "run_kind", existing_type=sa.String(20), type_=sa.String(10))
