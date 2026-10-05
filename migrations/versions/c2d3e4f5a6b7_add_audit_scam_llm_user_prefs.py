"""Add audit scam LLM preferences to users

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-03

"""
from alembic import op
import sqlalchemy as sa


revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("audit_scam_llm_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("audit_scam_llm_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("audit_scam_llm_think", sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column("users", "audit_scam_llm_think")
    op.drop_column("users", "audit_scam_llm_model")
    op.drop_column("users", "audit_scam_llm_enabled")
