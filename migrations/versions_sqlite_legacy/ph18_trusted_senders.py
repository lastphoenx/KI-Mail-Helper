"""Add trusted_senders table and urgency_booster_enabled setting

Revision ID: ph18_trusted_senders
Revises: 8af742a5077b
Create Date: 2026-01-07

Phase X: Trusted Sender Whitelist + UrgencyBooster

Neue Tabelle: trusted_senders (User-definierte vertrauenswürdige Absender)
Neue User-Spalte: urgency_booster_enabled (Global aktivieren/deaktivieren)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ph18_trusted_senders'
down_revision = '8af742a5077b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add trusted_senders table and user setting"""
    
    # 1. Add urgency_booster_enabled to users table
    op.add_column(
        'users',
        sa.Column(
            'urgency_booster_enabled',
            sa.Boolean(),
            nullable=False,
            server_default='1'
        )
    )
    
    # 2. Create trusted_senders table
    op.create_table(
        'trusted_senders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_pattern', sa.String(255), nullable=False),
        sa.Column('pattern_type', sa.String(20), nullable=False),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('use_urgency_booster', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('email_count', sa.Integer(), nullable=False, server_default='0'),
        
        sa.UniqueConstraint('user_id', 'sender_pattern', name='uq_user_sender')
    )
    
    # 3. Create indexes (Composite index für Performance)
    op.create_index('ix_trusted_senders_user_pattern', 'trusted_senders', 
                    ['user_id', 'sender_pattern'])
    
    print("✅ Migration ph18: trusted_senders table created")
    print("✅ Migration ph18: urgency_booster_enabled added to users")


def downgrade() -> None:
    """Rollback changes"""
    op.drop_table('trusted_senders')
    op.drop_column('users', 'urgency_booster_enabled')
    print("⬇️ Rollback ph18: Changes reverted")
