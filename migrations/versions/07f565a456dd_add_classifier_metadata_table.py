"""Add classifier_metadata table and hybrid score-learning columns

Revision ID: 07f565a456dd
Revises: df80ed2daa74
Create Date: 2026-01-17 16:00:00.000000

Hybrid Score-Learning Migration:
- Neue Tabelle: classifier_metadata (Metadata für trainierte ML-Modelle)
- Neue Spalte: users.prefer_personal_classifier (User-Präferenz: Global vs. Personal)
- Neue Spalte: processed_emails.used_model_source (Tracking welches Modell genutzt wurde)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07f565a456dd'
down_revision: Union[str, Sequence[str], None] = 'df80ed2daa74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ==========================================================================
    # 1. Neue Tabelle: classifier_metadata
    # ==========================================================================
    op.create_table('classifier_metadata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('classifier_type', sa.String(length=50), nullable=False),
        sa.Column('model_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('training_samples', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_trained_at', sa.DateTime(), nullable=True),
        sa.Column('accuracy_score', sa.Float(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'classifier_type', name='uq_classifier_metadata'),
        sa.CheckConstraint(
            "classifier_type IN ('dringlichkeit', 'wichtigkeit', 'spam', 'kategorie')",
            name='ck_classifier_type_valid'
        ),
    )
    op.create_index('idx_classifier_metadata_user_type', 'classifier_metadata', ['user_id', 'classifier_type'], unique=False)
    op.create_index('ix_classifier_metadata_user_id', 'classifier_metadata', ['user_id'], unique=False)

    # ==========================================================================
    # 2. User-Tabelle: prefer_personal_classifier hinzufügen
    # ==========================================================================
    op.add_column('users', sa.Column(
        'prefer_personal_classifier', 
        sa.Boolean(), 
        nullable=False, 
        server_default='false'
    ))

    # ==========================================================================
    # 3. ProcessedEmail-Tabelle: used_model_source hinzufügen
    # ==========================================================================
    op.add_column('processed_emails', sa.Column(
        'used_model_source', 
        sa.String(length=20), 
        nullable=False,
        server_default='global'
    ))


def downgrade() -> None:
    """Downgrade schema."""
    # 3. ProcessedEmail-Spalte entfernen
    op.drop_column('processed_emails', 'used_model_source')
    
    # 2. User-Spalte entfernen
    op.drop_column('users', 'prefer_personal_classifier')
    
    # 1. classifier_metadata Tabelle löschen
    op.drop_index('ix_classifier_metadata_user_id', table_name='classifier_metadata')
    op.drop_index('idx_classifier_metadata_user_type', table_name='classifier_metadata')
    op.drop_table('classifier_metadata')
