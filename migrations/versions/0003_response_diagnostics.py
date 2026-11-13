"""Persist finish reason and response diagnostics independently of model text."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_response_diagnostics"
down_revision = "0002_observability"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "api_model_attempts",
        sa.Column("diagnostics", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
    )


def downgrade():
    op.drop_column("api_model_attempts", "diagnostics")
