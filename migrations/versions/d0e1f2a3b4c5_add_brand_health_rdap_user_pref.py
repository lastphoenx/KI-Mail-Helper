"""audit_cluster_settings.brand_health_rdap (pro Nutzer, Default aus)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_cluster_settings",
        sa.Column(
            "brand_health_rdap",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column(
        "audit_cluster_settings",
        "brand_health_rdap",
        server_default=None,
    )


def downgrade():
    op.drop_column("audit_cluster_settings", "brand_health_rdap")
