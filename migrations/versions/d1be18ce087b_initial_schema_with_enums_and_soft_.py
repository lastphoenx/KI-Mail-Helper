"""Initial schema with enums and soft-delete

Revision ID: d1be18ce087b
Revises: 
Create Date: 2025-12-24 14:16:04.952084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1be18ce087b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('salt', sa.String(length=32), nullable=True),
    sa.Column('encrypted_master_key', sa.Text(), nullable=True),
    sa.Column('encrypted_master_key_for_cron', sa.Text(), nullable=True),
    sa.Column('totp_secret', sa.String(length=32), nullable=True),
    sa.Column('totp_enabled', sa.Boolean(), nullable=True),
    sa.Column('preferred_ai_provider', sa.String(length=20), nullable=True),
    sa.Column('preferred_ai_model', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    op.create_table('mail_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('imap_server', sa.String(length=255), nullable=False),
    sa.Column('imap_port', sa.Integer(), nullable=True),
    sa.Column('imap_username', sa.String(length=255), nullable=False),
    sa.Column('encrypted_imap_password', sa.Text(), nullable=True),
    sa.Column('imap_encryption', sa.String(length=50), nullable=True),
    sa.Column('smtp_server', sa.String(length=255), nullable=True),
    sa.Column('smtp_port', sa.Integer(), nullable=True),
    sa.Column('smtp_username', sa.String(length=255), nullable=True),
    sa.Column('encrypted_smtp_password', sa.Text(), nullable=True),
    sa.Column('smtp_encryption', sa.String(length=50), nullable=True),
    sa.Column('oauth_provider', sa.String(length=20), nullable=True),
    sa.Column('encrypted_oauth_token', sa.Text(), nullable=True),
    sa.Column('encrypted_oauth_refresh_token', sa.Text(), nullable=True),
    sa.Column('oauth_expires_at', sa.DateTime(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('last_fetch_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('service_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    
    op.create_table('recovery_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=255), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    
    op.create_table('raw_emails',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('mail_account_id', sa.Integer(), nullable=False),
    sa.Column('uid', sa.String(length=255), nullable=False),
    sa.Column('sender', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('received_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_verm', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['mail_account_id'], ['mail_accounts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'mail_account_id', 'uid', name='uq_raw_emails_uid')
    )
    op.create_index(op.f('ix_raw_emails_mail_account_id'), 'raw_emails', ['mail_account_id'], unique=False)
    op.create_index(op.f('ix_raw_emails_user_id'), 'raw_emails', ['user_id'], unique=False)
    
    op.create_table('processed_emails',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('raw_email_id', sa.Integer(), nullable=False),
    sa.Column('dringlichkeit', sa.Integer(), nullable=True),
    sa.Column('wichtigkeit', sa.Integer(), nullable=True),
    sa.Column('kategorie_aktion', sa.String(length=50), nullable=True),
    sa.Column('tags', sa.String(length=500), nullable=True),
    sa.Column('spam_flag', sa.Boolean(), nullable=True),
    sa.Column('summary_de', sa.Text(), nullable=True),
    sa.Column('text_de', sa.Text(), nullable=True),
    sa.Column('score', sa.Integer(), nullable=True),
    sa.Column('matrix_x', sa.Integer(), nullable=True),
    sa.Column('matrix_y', sa.Integer(), nullable=True),
    sa.Column('farbe', sa.String(length=10), nullable=True),
    sa.Column('done', sa.Boolean(), nullable=True),
    sa.Column('done_at', sa.DateTime(), nullable=True),
    sa.Column('processed_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_verm', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['raw_email_id'], ['raw_emails.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('raw_email_id')
    )
    op.create_index(op.f('ix_processed_emails_raw_email_id'), 'processed_emails', ['raw_email_id'], unique=True)
    
    op.create_table('email_folders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('mail_account_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('imap_path', sa.String(length=500), nullable=False),
    sa.Column('unread_count', sa.Integer(), nullable=True),
    sa.Column('total_count', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['mail_account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'mail_account_id', 'imap_path', name='uq_email_folders_path')
    )
    op.create_index(op.f('ix_email_folders_mail_account_id'), 'email_folders', ['mail_account_id'], unique=False)
    op.create_index(op.f('ix_email_folders_user_id'), 'email_folders', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_email_folders_user_id'), table_name='email_folders')
    op.drop_index(op.f('ix_email_folders_mail_account_id'), table_name='email_folders')
    op.drop_table('email_folders')
    
    op.drop_index(op.f('ix_processed_emails_raw_email_id'), table_name='processed_emails')
    op.drop_table('processed_emails')
    
    op.drop_index(op.f('ix_raw_emails_user_id'), table_name='raw_emails')
    op.drop_index(op.f('ix_raw_emails_mail_account_id'), table_name='raw_emails')
    op.drop_table('raw_emails')
    
    op.drop_table('recovery_codes')
    op.drop_table('service_tokens')
    op.drop_table('mail_accounts')
    
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
