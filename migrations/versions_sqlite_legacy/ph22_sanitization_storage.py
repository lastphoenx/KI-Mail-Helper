"""Phase 22: Sanitization Storage für raw_emails

Revision ID: ph22_sanitization_storage
Revises: 25405a1758ce, ph_y_spacy_hybrid
Create Date: 2026-01-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'ph22_sanitization_storage'
down_revision = ('25405a1758ce', 'ph_y_spacy_hybrid')
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Fügt Anonymisierungs-Spalten zu raw_emails hinzu"""
    
    # Pseudonymisierte Inhalte (verschlüsselt wie Original)
    op.add_column('raw_emails',
        sa.Column('encrypted_subject_sanitized', sa.Text, nullable=True)
    )
    op.add_column('raw_emails',
        sa.Column('encrypted_body_sanitized', sa.Text, nullable=True)
    )
    
    # Sanitization Metadata (für Audit + Performance)
    op.add_column('raw_emails',
        sa.Column('sanitization_level', sa.Integer, nullable=True)
    )
    # 1=Regex only, 2=spaCy-Light (PER), 3=spaCy-Full (PER+ORG+GPE+LOC)
    
    op.add_column('raw_emails',
        sa.Column('sanitization_time_ms', sa.Float, nullable=True)
    )
    
    op.add_column('raw_emails',
        sa.Column('sanitization_entities_count', sa.Integer, nullable=True)
    )
    # Total gefundene Entities (PER + ORG + GPE + LOC)
    
    # Index für "welche Emails haben sanitized content"
    # SQLite-kompatibel: kein postgresql_where
    op.create_index(
        'idx_raw_emails_has_sanitized',
        'raw_emails',
        ['encrypted_subject_sanitized'],
        unique=False
    )

def downgrade() -> None:
    """Rollback: Entfernt Anonymisierungs-Spalten"""
    op.drop_index('idx_raw_emails_has_sanitized', table_name='raw_emails')
    op.drop_column('raw_emails', 'sanitization_entities_count')
    op.drop_column('raw_emails', 'sanitization_time_ms')
    op.drop_column('raw_emails', 'sanitization_level')
    op.drop_column('raw_emails', 'encrypted_body_sanitized')
    op.drop_column('raw_emails', 'encrypted_subject_sanitized')
