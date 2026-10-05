"""add cluster mode overrides json

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_cluster_settings",
        sa.Column("mode_overrides_json", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("audit_cluster_settings", "mode_overrides_json")
