"""add_processing_status_and_retry_tracking

Revision ID: 7e6b745cb05c
Revises: 6b293d67c016
Create Date: 2026-01-23 17:21:05.259037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e6b745cb05c'
down_revision: Union[str, Sequence[str], None] = '6b293d67c016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add processing status tracking to raw_emails."""
    # Phase 27: Processing State Machine
    # Ermöglicht Resume nach Crash/Timeout - keine doppelte Arbeit mehr!
    op.add_column('raw_emails', sa.Column('processing_status', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('raw_emails', sa.Column('processing_retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('raw_emails', sa.Column('processing_error', sa.Text(), nullable=True))
    op.add_column('raw_emails', sa.Column('processing_last_attempt_at', sa.DateTime(), nullable=True))
    
    # Index für Performance (Query: WHERE processing_status < 100)
    op.create_index('ix_raw_emails_processing_status', 'raw_emails', ['processing_status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_raw_emails_processing_status', 'raw_emails')
    op.drop_column('raw_emails', 'processing_last_attempt_at')
    op.drop_column('raw_emails', 'processing_error')
    op.drop_column('raw_emails', 'processing_retry_count')
    op.drop_column('raw_emails', 'processing_status')
