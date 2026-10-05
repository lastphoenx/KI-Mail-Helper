"""Add audit_exclude_folders to mail_accounts

Revision ID: a9b8c7d6e5f4
Revises: f1a2b3c4d5e6
Create Date: 2026-10-02

Ordner-Audit: pro Account Ordner vom Scan/Clustering ausschliessen (Archiv etc.).
"""
from alembic import op
import sqlalchemy as sa


revision = "a9b8c7d6e5f4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mail_accounts",
        sa.Column("audit_exclude_folders", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mail_accounts", "audit_exclude_folders")
