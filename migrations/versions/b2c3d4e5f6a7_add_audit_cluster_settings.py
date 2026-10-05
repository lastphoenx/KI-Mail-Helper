"""add audit_cluster_settings

Revision ID: b2c3d4e5f6a7
Revises: a9b8c7d6e5f4
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_cluster_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("use_custom_bulk_merge_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bulk_merge_block_domains", sa.Text(), nullable=True),
        sa.Column("normalization_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "account_id", name="uq_audit_cluster_settings"),
    )
    op.create_index(
        "idx_audit_cluster_settings_user",
        "audit_cluster_settings",
        ["user_id", "account_id"],
    )


def downgrade():
    op.drop_index("idx_audit_cluster_settings_user", table_name="audit_cluster_settings")
    op.drop_table("audit_cluster_settings")
