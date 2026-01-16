"""Phase INV: Invite Whitelist + IMAP Diagnostics Access

Revision ID: ph_inv_001
Revises: phH_smtp_sender
Create Date: 2026-01-04

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, UTC


# revision identifiers, used by Alembic.
revision = 'ph_inv_001'
down_revision = 'ph13c_p6_move_filters'  # Current DB version
branch_labels = None
depends_on = None


def upgrade():
    # Add imap_diagnostics_enabled to users table
    op.add_column('users', sa.Column('imap_diagnostics_enabled', sa.Boolean(), nullable=False, server_default='0'))
    
    # Create invited_emails table
    op.create_table('invited_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('invited_at', sa.DateTime(), nullable=False),
        sa.Column('invited_by', sa.String(length=255), nullable=True),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_invited_emails_email', 'invited_emails', ['email'], unique=True)


def downgrade():
    op.drop_index('ix_invited_emails_email', table_name='invited_emails')
    op.drop_table('invited_emails')
    op.drop_column('users', 'imap_diagnostics_enabled')
