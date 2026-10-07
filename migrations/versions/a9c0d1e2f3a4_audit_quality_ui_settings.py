"""Ordner-Muster und Altersschwellen für Ordner-Audit (pro Account).

Revision ID: a9c0d1e2f3a4
Revises: f8a9b0c1d2e3
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa


revision = "a9c0d1e2f3a4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_accounts",
        sa.Column("audit_curated_folder_patterns", sa.Text(), nullable=True),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("audit_success_safe_after_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("audit_transaction_safe_after_days", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("mail_accounts", "audit_transaction_safe_after_days")
    op.drop_column("mail_accounts", "audit_success_safe_after_days")
    op.drop_column("mail_accounts", "audit_curated_folder_patterns")
