"""DNS/RDAP-Hinweis im Ordner-Audit, Cache und Schwellen pro Account.

Revision ID: b1d2e3f4a5b6
Revises: a9c0d1e2f3a4
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa


revision = "b1d2e3f4a5b6"
down_revision = "a9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_accounts",
        sa.Column("audit_domain_intel_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("audit_domain_young_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("audit_domain_caution_days", sa.Integer(), nullable=True),
    )
    op.create_table(
        "audit_domain_intel_cache",
        sa.Column("domain", sa.String(length=253), primary_key=True),
        sa.Column("dns_status", sa.String(length=16), nullable=False),
        sa.Column("age_days", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("audit_domain_intel_cache")
    op.drop_column("mail_accounts", "audit_domain_caution_days")
    op.drop_column("mail_accounts", "audit_domain_young_days")
    op.drop_column("mail_accounts", "audit_domain_intel_enabled")
