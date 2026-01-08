"""Phase Y: spaCy Hybrid Pipeline Tables

Revision ID: ph_y_spacy_hybrid
Revises: ph15_add_rebase_timestamp
Create Date: 2026-01-08

F\u00fcgt 4 neue Tabellen f\u00fcr spaCy Hybrid Pipeline hinzu:
1. spacy_vip_senders - VIP-Absender mit Importance-Boost
2. spacy_keyword_sets - Konfigurierbare Keyword-Sets pro Account
3. spacy_scoring_config - Scoring-Thresholds und Weights
4. spacy_user_domains - Eigene Domains f\u00fcr intern/extern Erkennung
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = 'ph_y_spacy_hybrid'
down_revision = 'ph21_account_urgency_booster'  # Latest head
branch_labels = None
depends_on = None


def upgrade():
    """Create Phase Y tables"""
    
    # =================================================================
    # TABELLE 1: VIP-Absender f\u00fcr automatischen Importance-Boost
    # =================================================================
    op.create_table(
        'spacy_vip_senders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),  # NULL = global
        
        # Sender Pattern (wie TrustedSender)
        sa.Column('sender_pattern', sa.String(length=255), nullable=False),
        sa.Column('pattern_type', sa.String(length=20), nullable=False),  # 'exact', 'email_domain', 'domain'
        
        # VIP-Konfiguration
        sa.Column('label', sa.String(length=100), nullable=True),  # "Chef", "CEO", "Wichtiger Kunde"
        sa.Column('importance_boost', sa.Integer(), nullable=False, server_default='3'),  # +1 bis +5
        sa.Column('urgency_boost', sa.Integer(), nullable=False, server_default='0'),  # Optional
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'sender_pattern', 'account_id', name='uq_vip_user_pattern_account')
    )
    op.create_index('ix_spacy_vip_user_account', 'spacy_vip_senders', ['user_id', 'account_id'])
    
    # =================================================================
    # TABELLE 2: Konfigurierbare Keyword-Sets (pro Account)
    # =================================================================
    op.create_table(
        'spacy_keyword_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),  # NULL = global
        
        # Set-Identifikation
        sa.Column('set_type', sa.String(length=50), nullable=False),  # 'urgency_high', 'urgency_low', etc.
        
        # Keywords als JSON Array
        sa.Column('keywords_json', sa.Text(), nullable=False),  # ["dringend", "asap", "sofort"]
        
        # Scoring-Konfiguration
        sa.Column('points_per_match', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('max_points', sa.Integer(), nullable=False, server_default='4'),
        
        # Flags
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_custom', sa.Boolean(), nullable=False, server_default='0'),  # TRUE = User-definiert
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'account_id', 'set_type', name='uq_keywords_user_account_type')
    )
    op.create_index('ix_spacy_keywords_user_account', 'spacy_keyword_sets', ['user_id', 'account_id', 'set_type'])
    
    # =================================================================
    # TABELLE 3: Scoring-Konfiguration (Thresholds, Weights)
    # =================================================================
    op.create_table(
        'spacy_scoring_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),  # NULL = global
        
        # Thresholds f\u00fcr Priority-Mapping
        sa.Column('urgency_high_threshold', sa.Integer(), nullable=False, server_default='6'),
        sa.Column('importance_high_threshold', sa.Integer(), nullable=False, server_default='6'),
        
        # Deadline-Scoring
        sa.Column('deadline_critical_hours', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('deadline_urgent_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('deadline_soon_hours', sa.Integer(), nullable=False, server_default='72'),
        
        sa.Column('deadline_critical_points', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('deadline_urgent_points', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('deadline_soon_points', sa.Integer(), nullable=False, server_default='2'),
        
        # Absender-Kontext
        sa.Column('vip_default_importance', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('external_sender_importance', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('direct_to_importance', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('cc_only_importance', sa.Integer(), nullable=False, server_default='-1'),
        sa.Column('many_recipients_importance', sa.Integer(), nullable=False, server_default='-1'),
        
        # Negative Signale
        sa.Column('newsletter_urgency_penalty', sa.Integer(), nullable=False, server_default='-5'),
        sa.Column('newsletter_importance_penalty', sa.Integer(), nullable=False, server_default='-4'),
        sa.Column('auto_reply_penalty', sa.Integer(), nullable=False, server_default='-5'),
        sa.Column('fyi_penalty', sa.Integer(), nullable=False, server_default='-2'),
        
        # Flags
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'account_id', name='uq_scoring_user_account')
    )
    
    # =================================================================
    # TABELLE 4: User-eigene Domains (f\u00fcr intern/extern Erkennung)
    # =================================================================
    op.create_table(
        'spacy_user_domains',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        
        sa.Column('domain', sa.String(length=255), nullable=False),  # "meinefirma.de"
        sa.Column('is_internal', sa.Boolean(), nullable=False, server_default='1'),  # TRUE = intern
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'account_id', 'domain', name='uq_domain_user_account')
    )


def downgrade():
    """Drop Phase Y tables"""
    op.drop_table('spacy_user_domains')
    op.drop_table('spacy_scoring_config')
    op.drop_index('ix_spacy_keywords_user_account', 'spacy_keyword_sets')
    op.drop_table('spacy_keyword_sets')
    op.drop_index('ix_spacy_vip_user_account', 'spacy_vip_senders')
    op.drop_table('spacy_vip_senders')
