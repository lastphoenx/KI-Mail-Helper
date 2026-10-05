"""brand official domains on audit_cluster_settings (user-level)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-03

"""
from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_cluster_settings",
        sa.Column("brand_official_domains_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "audit_cluster_settings",
        sa.Column("brand_source_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "audit_cluster_settings",
        sa.Column("brand_import_pending_json", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("audit_cluster_settings", "brand_import_pending_json")
    op.drop_column("audit_cluster_settings", "brand_source_url")
    op.drop_column("audit_cluster_settings", "brand_official_domains_json")
