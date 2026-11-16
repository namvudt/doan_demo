"""Versioned reviewed sources, entity bindings and editorial audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_content_platform"
down_revision = "0007_accounts_product"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("heritage_id", sa.String(80), sa.ForeignKey("heritage_sites.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("publisher", sa.String(240), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_content_documents_heritage_id", "content_documents", ["heritage_id"])
    op.create_table(
        "content_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("content_documents.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("retrieved_at", sa.Float()),
        sa.Column("reviewer", sa.String(120)),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.Float()),
        sa.Column("published_at", sa.Float()),
        sa.UniqueConstraint("document_id", "revision", name="uq_content_document_revision"),
        sa.CheckConstraint(
            "status IN ('draft','reviewed','published','archived')",
            name="ck_content_version_status",
        ),
    )
    op.create_index("ix_content_versions_document_id", "content_versions", ["document_id"])
    op.create_index("ix_content_versions_status", "content_versions", ["status"])
    op.create_table(
        "heritage_entity_bindings",
        sa.Column(
            "heritage_id", sa.String(80), sa.ForeignKey("heritage_sites.id"), primary_key=True
        ),
        sa.Column("entity_id", sa.String(120), nullable=False, unique=True),
        sa.Column("parent_heritage_id", sa.String(80), sa.ForeignKey("heritage_sites.id")),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(120), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "editorial_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("heritage_id", sa.String(80), sa.ForeignKey("heritage_sites.id"), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column(
            "details", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_editorial_audit_heritage_id", "editorial_audit", ["heritage_id"])


def downgrade():
    op.drop_index("ix_editorial_audit_heritage_id", "editorial_audit")
    op.drop_table("editorial_audit")
    op.drop_table("heritage_entity_bindings")
    op.drop_index("ix_content_versions_status", "content_versions")
    op.drop_index("ix_content_versions_document_id", "content_versions")
    op.drop_table("content_versions")
    op.drop_index("ix_content_documents_heritage_id", "content_documents")
    op.drop_table("content_documents")
