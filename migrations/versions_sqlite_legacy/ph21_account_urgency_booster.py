"""Add account-level urgency_booster_enabled setting

Revision ID: ph21_account_urgency_booster
Revises: ph20_trusted_senders_index
Create Date: 2026-01-07

Adds account-level control for UrgencyBooster feature instead of global-only setting.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ph21_account_urgency_booster'
down_revision = 'ph20_trusted_senders_index'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add urgency_booster_enabled to mail_accounts table"""
    op.execute("""
        ALTER TABLE mail_accounts 
        ADD COLUMN urgency_booster_enabled BOOLEAN NOT NULL DEFAULT 1
    """)
    print("✅ Migration ph21: Column urgency_booster_enabled added to mail_accounts")


def downgrade() -> None:
    """Remove the column"""
    op.execute("""
        ALTER TABLE mail_accounts 
        DROP COLUMN urgency_booster_enabled
    """)
    print("⬇️ Rollback ph21: Column urgency_booster_enabled removed from mail_accounts")
