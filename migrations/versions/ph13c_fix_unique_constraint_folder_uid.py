"""Fix UniqueConstraint for RawEmail: include imap_folder

Revision ID: ph13c_fix_unique_constraint_folder_uid
Revises: ph13_initial_sync_tracking
Create Date: 2026-01-01

CRITICAL FIX: IMAP UID ist nur eindeutig pro (account, folder, uid)!
- INBOX/UID=123 ≠ Archiv/UID=123 (verschiedene IMAP-Objekte)
- Alter Constraint: (user_id, mail_account_id, uid) ❌
- Neuer Constraint: (user_id, mail_account_id, imap_folder, imap_uid) ✅

Ohne diesen Fix: Mails in mehreren Ordnern überschreiben sich gegenseitig.
"""

from alembic import op
import sqlalchemy as sa


revision = 'ph13c_fix_unique_constraint_folder_uid'
down_revision = 'ph13_initial_sync_tracking'
branch_labels = None
depends_on = None


def upgrade():
    """Ersetzt alte UniqueConstraint durch korrekte (mit imap_folder)."""
    
    # 1. Drop old constraint (nur uid-based)
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.drop_constraint('uq_raw_emails_uid', type_='unique')
        
        # 2. Create new constraint (folder + uid)
        batch_op.create_unique_constraint(
            'uq_raw_emails_folder_uid',
            ['user_id', 'mail_account_id', 'imap_folder', 'imap_uid']
        )


def downgrade():
    """Reverts to old (incorrect) constraint."""
    
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.drop_constraint('uq_raw_emails_folder_uid', type_='unique')
        
        batch_op.create_unique_constraint(
            'uq_raw_emails_uid',
            ['user_id', 'mail_account_id', 'uid']
        )
