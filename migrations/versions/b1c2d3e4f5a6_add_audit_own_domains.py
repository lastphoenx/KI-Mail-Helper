"""Add audit_own_domains to mail_accounts

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_accounts",
        sa.Column("audit_own_domains", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("mail_accounts", "audit_own_domains")
