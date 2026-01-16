"""Add index for trusted_senders (user_id, account_id) filtering

Revision ID: ph20_trusted_senders_index
Revises: ph19_trusted_senders_account_id
Create Date: 2026-01-07

Phase X Optimization: Improves performance for account-based filtering queries
"""
from alembic import op
import sqlalchemy as sa

revision = 'ph20_trusted_senders_index'
down_revision = 'ph19_trusted_senders_account_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add index for user_id + account_id filtering"""
    op.execute("""
        CREATE INDEX ix_trusted_senders_user_account 
        ON trusted_senders (user_id, account_id)
    """)
    print("✅ Migration ph20: Index (user_id, account_id) added for faster account filtering")


def downgrade() -> None:
    """Remove the index"""
    op.execute("DROP INDEX IF EXISTS ix_trusted_senders_user_account")
    print("⬇️ Rollback ph20: Index (user_id, account_id) removed")
