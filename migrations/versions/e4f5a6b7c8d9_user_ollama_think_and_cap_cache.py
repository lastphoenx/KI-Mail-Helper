"""Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-03

User think prefs (Base/Optimize) + Ollama capability cache.
"""
from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("preferred_ai_think_base", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("preferred_ai_think_optimize", sa.Boolean(), nullable=True),
    )
    op.create_table(
        "ollama_model_capability_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("think_mode", sa.String(length=20), nullable=False),
        sa.Column("model_digest", sa.String(length=128), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "base_url", "model_name", name="uq_ollama_cap_base_model"
        ),
    )


def downgrade():
    op.drop_table("ollama_model_capability_cache")
    op.drop_column("users", "preferred_ai_think_optimize")
    op.drop_column("users", "preferred_ai_think_base")
