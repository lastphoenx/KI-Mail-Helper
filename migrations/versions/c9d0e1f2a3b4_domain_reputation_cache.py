"""domain_reputation_cache table

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "domain_reputation_cache",
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("dbl_status", sa.String(length=16), nullable=False),
        sa.Column("dbl_detail", sa.String(length=255), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("domain"),
    )


def downgrade():
    op.drop_table("domain_reputation_cache")
