"""add_imap_flags_tracking

Revision ID: f1a2b3c4d5e6
Revises: 86ca02f07586
Create Date: 2025-12-26 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '86ca02f07586'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add IMAP flags tracking to raw_emails and processed_emails."""
    
    with op.batch_alter_table('raw_emails') as batch_op:
        batch_op.add_column(sa.Column('imap_uid', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('imap_folder', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('imap_flags', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('imap_last_seen_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_raw_emails_imap_uid', ['imap_uid'])
    
    with op.batch_alter_table('processed_emails') as batch_op:
        batch_op.add_column(sa.Column('imap_flags_at_processing', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('was_seen_at_processing', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('was_answered_at_processing', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Remove IMAP flags tracking."""
    
    with op.batch_alter_table('processed_emails') as batch_op:
        batch_op.drop_column('was_answered_at_processing')
        batch_op.drop_column('was_seen_at_processing')
        batch_op.drop_column('imap_flags_at_processing')
    
    with op.batch_alter_table('raw_emails') as batch_op:
        batch_op.drop_index('ix_raw_emails_imap_uid')
        batch_op.drop_column('imap_last_seen_at')
        batch_op.drop_column('imap_flags')
        batch_op.drop_column('imap_folder')
        batch_op.drop_column('imap_uid')
