"""add_auth_type_and_pop3_support

Revision ID: 86ca02f07586
Revises: 3a1ac5983a2d
Create Date: 2025-12-25 23:37:09.114212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86ca02f07586'
down_revision: Union[str, Sequence[str], None] = '3a1ac5983a2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add auth_type and POP3 support to mail_accounts."""
    
    # 1. Add new columns
    with op.batch_alter_table('mail_accounts') as batch_op:
        # Add auth_type column (default: 'imap')
        batch_op.add_column(sa.Column('auth_type', sa.String(length=20), nullable=False, server_default='imap'))
        
        # Make IMAP fields nullable (für OAuth/POP3 Accounts)
        batch_op.alter_column('imap_server', existing_type=sa.String(length=255), nullable=True)
        batch_op.alter_column('imap_username', existing_type=sa.String(length=255), nullable=True)
        
        # Add POP3-specific fields
        batch_op.add_column(sa.Column('pop3_server', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('pop3_port', sa.Integer(), nullable=True, server_default='995'))
        batch_op.add_column(sa.Column('pop3_username', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('encrypted_pop3_password', sa.Text(), nullable=True))
    
    # 2. Set auth_type based on existing data
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE mail_accounts 
        SET auth_type = CASE 
            WHEN oauth_provider IS NOT NULL THEN 'oauth'
            ELSE 'imap'
        END
    """))


def downgrade() -> None:
    """Downgrade schema: Remove auth_type and POP3 support."""
    
    with op.batch_alter_table('mail_accounts') as batch_op:
        # Remove POP3 columns
        batch_op.drop_column('encrypted_pop3_password')
        batch_op.drop_column('pop3_username')
        batch_op.drop_column('pop3_port')
        batch_op.drop_column('pop3_server')
        
        # Remove auth_type
        batch_op.drop_column('auth_type')
        
        # Restore IMAP fields to NOT NULL (optional, kann Fehler verursachen bei OAuth Accounts)
        # batch_op.alter_column('imap_server', existing_type=sa.String(length=255), nullable=False)
        # batch_op.alter_column('imap_username', existing_type=sa.String(length=255), nullable=False)
