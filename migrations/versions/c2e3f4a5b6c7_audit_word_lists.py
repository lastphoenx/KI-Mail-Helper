"""Eigene Wortlisten für Ordner-Audit (pro Account, JSON).

Revision ID: c2e3f4a5b6c7
Revises: b1d2e3f4a5b6
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa


revision = "c2e3f4a5b6c7"
down_revision = "b1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_accounts",
        sa.Column("audit_word_lists_json", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("mail_accounts", "audit_word_lists_json")
