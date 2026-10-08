"""Eigene Absenderadressen für Ordner-Audit (pro Account, JSON).

Revision ID: d4e5f6a7b8c9
Revises: c2e3f4a5b6c7
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_accounts",
        sa.Column("audit_own_addresses", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("mail_accounts", "audit_own_addresses")
