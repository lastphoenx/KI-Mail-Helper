"""Add initial_sync_done flag to MailAccount

Revision ID: ph13_initial_sync_tracking
Revises: ph12b_received_at_index
Create Date: 2025-12-31

Fügt initial_sync_done Flag zu mail_accounts hinzu um zwischen
Initialer Synchronisierung (500 Mails) und regelmäßigen Fetches (50 Mails)
zu unterscheiden. Wird nur 1x auf True gesetzt nach dem ersten erfolgreichen Fetch.
"""

from alembic import op
import sqlalchemy as sa


revision = 'ph13_initial_sync_tracking'
down_revision = 'ph12b_received_at_index'
branch_labels = None
depends_on = None


def upgrade():
    """Fügt initial_sync_done zu mail_accounts hinzu."""
    
    op.add_column('mail_accounts', 
        sa.Column('initial_sync_done', sa.Boolean(), 
                  nullable=False, server_default='0'))
    
    op.execute("""
        UPDATE mail_accounts 
        SET initial_sync_done = 1 
        WHERE last_fetch_at IS NOT NULL
    """)


def downgrade():
    """Entfernt initial_sync_done."""
    op.drop_column('mail_accounts', 'initial_sync_done')
