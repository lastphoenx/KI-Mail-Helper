"""Add audit_scam_llm_provider to users

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-03

"""
from alembic import op
import sqlalchemy as sa


revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("audit_scam_llm_provider", sa.String(length=20), nullable=True),
    )


def downgrade():
    op.drop_column("users", "audit_scam_llm_provider")
