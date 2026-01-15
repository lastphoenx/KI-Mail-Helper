"""Add embedding model settings (3 settings refactoring)

Revision ID: c4ab07bd3f10
Revises: phf2_tag_learning
Create Date: 2026-01-02 20:30:06.533874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4ab07bd3f10'
down_revision: Union[str, Sequence[str], None] = 'phf2_tag_learning'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add embedding model settings."""
    # Nur die wichtigen Änderungen: Neue Spalten für Embedding-Settings
    op.add_column('users', sa.Column('preferred_embedding_provider', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('preferred_embedding_model', sa.String(length=100), nullable=True))
    
    # Default-Werte setzen für bestehende User
    from sqlalchemy import table, column
    users_table = table('users',
        column('preferred_embedding_provider', sa.String),
        column('preferred_embedding_model', sa.String)
    )
    op.execute(users_table.update().values(
        preferred_embedding_provider='ollama',
        preferred_embedding_model='all-minilm:22m'
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'preferred_embedding_model')
    op.drop_column('users', 'preferred_embedding_provider')
    op.create_index(op.f('ix_email_tags_user_id'), 'email_tags', ['user_id'], unique=False)
    op.create_index(op.f('ix_email_tag_assignments_tag_id'), 'email_tag_assignments', ['tag_id'], unique=False)
    op.create_index(op.f('ix_email_tag_assignments_email_id'), 'email_tag_assignments', ['email_id'], unique=False)
    op.create_table('mail_provider_folder_templates',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('provider', sa.VARCHAR(length=50), nullable=False),
    sa.Column('folder_hierarchies', sa.TEXT(), nullable=False),
    sa.Column('special_use_folders', sa.TEXT(), nullable=True),
    sa.Column('confirmed_by_accounts', sa.INTEGER(), nullable=True),
    sa.Column('version', sa.INTEGER(), nullable=True),
    sa.Column('last_verified', sa.DATETIME(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mail_provider_folder_templates_provider'), 'mail_provider_folder_templates', ['provider'], unique=1)
    op.create_table('mail_provider_capabilities',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('provider', sa.VARCHAR(length=50), nullable=False),
    sa.Column('imap_host', sa.VARCHAR(length=255), nullable=True),
    sa.Column('imap_port', sa.INTEGER(), nullable=True),
    sa.Column('imap_encryption', sa.VARCHAR(length=20), nullable=True),
    sa.Column('supports_idle', sa.BOOLEAN(), nullable=True),
    sa.Column('supports_compress', sa.BOOLEAN(), nullable=True),
    sa.Column('supports_special_use', sa.BOOLEAN(), nullable=True),
    sa.Column('supports_gmail_labels', sa.BOOLEAN(), nullable=True),
    sa.Column('supports_oauth2', sa.BOOLEAN(), nullable=True),
    sa.Column('sasl_mechanisms', sa.TEXT(), nullable=True),
    sa.Column('capabilities_raw', sa.TEXT(), nullable=True),
    sa.Column('provider_metadata', sa.TEXT(), nullable=True),
    sa.Column('version', sa.INTEGER(), nullable=True),
    sa.Column('last_verified', sa.DATETIME(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mail_provider_capabilities_provider'), 'mail_provider_capabilities', ['provider'], unique=1)
    op.create_table('mail_account_sync_configs',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('mail_account_id', sa.INTEGER(), nullable=False),
    sa.Column('sync_mode', sa.VARCHAR(length=50), nullable=True),
    sa.Column('min_date', sa.DATETIME(), nullable=True),
    sa.Column('max_days_back', sa.INTEGER(), nullable=True),
    sa.Column('include_only_folders', sa.TEXT(), nullable=True),
    sa.Column('exclude_folders', sa.TEXT(), nullable=True),
    sa.Column('exclude_sender_patterns', sa.TEXT(), nullable=True),
    sa.Column('exclude_domains', sa.TEXT(), nullable=True),
    sa.Column('max_size_mb', sa.INTEGER(), nullable=True),
    sa.Column('max_attachments', sa.INTEGER(), nullable=True),
    sa.Column('high_priority_senders', sa.TEXT(), nullable=True),
    sa.Column('high_priority_keywords', sa.TEXT(), nullable=True),
    sa.Column('process_priority_first', sa.BOOLEAN(), nullable=True),
    sa.Column('full_sync_interval', sa.VARCHAR(length=50), nullable=True),
    sa.Column('incremental_sync_interval', sa.VARCHAR(length=50), nullable=True),
    sa.Column('idle_enabled', sa.BOOLEAN(), nullable=True),
    sa.Column('bandwidth_limit_kbps', sa.INTEGER(), nullable=True),
    sa.Column('last_full_sync', sa.DATETIME(), nullable=True),
    sa.Column('last_incremental_sync', sa.DATETIME(), nullable=True),
    sa.Column('next_scheduled_sync', sa.DATETIME(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['mail_account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mail_account_sync_configs_mail_account_id'), 'mail_account_sync_configs', ['mail_account_id'], unique=1)
    op.create_table('mail_provider_flag_mappings',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('provider', sa.VARCHAR(length=50), nullable=False),
    sa.Column('standard_flags', sa.TEXT(), nullable=False),
    sa.Column('custom_flags', sa.TEXT(), nullable=True),
    sa.Column('gmail_labels_support', sa.BOOLEAN(), nullable=True),
    sa.Column('outlook_categories_support', sa.BOOLEAN(), nullable=True),
    sa.Column('proton_flags_support', sa.BOOLEAN(), nullable=True),
    sa.Column('can_modify_flags', sa.BOOLEAN(), nullable=True),
    sa.Column('label_mapping', sa.TEXT(), nullable=True),
    sa.Column('version', sa.INTEGER(), nullable=True),
    sa.Column('last_verified', sa.DATETIME(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mail_provider_flag_mappings_provider'), 'mail_provider_flag_mappings', ['provider'], unique=1)
    op.create_table('mail_account_flag_mappings',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('mail_account_id', sa.INTEGER(), nullable=False),
    sa.Column('provider', sa.VARCHAR(length=50), nullable=False),
    sa.Column('imap_flag_name', sa.VARCHAR(length=100), nullable=False),
    sa.Column('user_friendly_name', sa.VARCHAR(length=100), nullable=True),
    sa.Column('bidirectional', sa.BOOLEAN(), nullable=True),
    sa.Column('detected_at', sa.DATETIME(), nullable=True),
    sa.Column('last_used_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['mail_account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('mail_account_id', 'imap_flag_name', name=op.f('uq_account_flag_name'))
    )
    op.create_index(op.f('ix_mail_account_flag_mappings_mail_account_id'), 'mail_account_flag_mappings', ['mail_account_id'], unique=False)
    # ### end Alembic commands ###
