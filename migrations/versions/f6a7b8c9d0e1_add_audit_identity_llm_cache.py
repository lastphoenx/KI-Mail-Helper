"""Add audit_identity_llm_cache table

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_identity_llm_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_audit_identity_llm_cache_cache_key",
        "audit_identity_llm_cache",
        ["cache_key"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_audit_identity_llm_cache_cache_key", table_name="audit_identity_llm_cache")
    op.drop_table("audit_identity_llm_cache")
