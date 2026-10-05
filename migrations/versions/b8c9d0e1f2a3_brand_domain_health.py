"""brand domain health + dbl block cache on audit_cluster_settings

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_cluster_settings",
        sa.Column("brand_domains_health_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "audit_cluster_settings",
        sa.Column("brand_domains_health_checked_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "audit_cluster_settings",
        sa.Column("brand_dbl_blocked_domains_json", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("audit_cluster_settings", "brand_dbl_blocked_domains_json")
    op.drop_column("audit_cluster_settings", "brand_domains_health_checked_at")
    op.drop_column("audit_cluster_settings", "brand_domains_health_json")
