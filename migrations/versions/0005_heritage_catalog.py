"""Durable heritage catalog, local media, and provenance-aware location metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_heritage_catalog"
down_revision = "0004_review_runs"
branch_labels = None
depends_on = None


def upgrade():
    payload = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "heritage_sites",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False, unique=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("province", sa.String(120), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("period", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags", payload, nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("content_status", sa.String(20), nullable=False),
        sa.Column("illustrative", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.CheckConstraint("content_status IN ('draft', 'published')", name="ck_heritage_status"),
        sa.CheckConstraint("version > 0", name="ck_heritage_version"),
    )
    op.create_index(
        "ix_heritage_catalog_public", "heritage_sites", ["content_status", "province", "category"]
    )
    op.create_table(
        "heritage_site_information",
        sa.Column(
            "heritage_id",
            sa.String(80),
            sa.ForeignKey("heritage_sites.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("historical_information", sa.Text(), nullable=False),
        sa.Column("cultural_information", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("verification_status", sa.String(20), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=True),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL AND verification_status IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 "
            "AND longitude BETWEEN -180 AND 180 AND verification_status IS NOT NULL AND verification_status "
            "IN ('illustrative', 'unverified', 'verified'))",
            name="ck_heritage_location",
        ),
    )
    op.create_table(
        "heritage_site_media",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "heritage_id",
            sa.String(80),
            sa.ForeignKey("heritage_sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(220), nullable=False),
        sa.Column("alt", sa.String(500), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_heritage_site_media_heritage_id", "heritage_site_media", ["heritage_id"])
    op.create_table(
        "heritage_content_sources",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "heritage_id",
            sa.String(80),
            sa.ForeignKey("heritage_sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("publisher", sa.String(240), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("verification_note", sa.Text(), nullable=False),
        sa.Column("index_status", sa.String(20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("index_status = 'not_indexed'", name="ck_catalog_source_not_ingested"),
    )
    op.create_index(
        "ix_heritage_content_sources_heritage_id", "heritage_content_sources", ["heritage_id"]
    )


def downgrade():
    op.drop_index("ix_heritage_content_sources_heritage_id", "heritage_content_sources")
    op.drop_table("heritage_content_sources")
    op.drop_index("ix_heritage_site_media_heritage_id", "heritage_site_media")
    op.drop_table("heritage_site_media")
    op.drop_table("heritage_site_information")
    op.drop_index("ix_heritage_catalog_public", "heritage_sites")
    op.drop_table("heritage_sites")
