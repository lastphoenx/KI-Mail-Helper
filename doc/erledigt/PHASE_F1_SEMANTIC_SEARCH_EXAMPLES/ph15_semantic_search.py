"""Phase 15: Semantic Search - Email Embeddings

Revision ID: ph15_semantic_search
Revises: ph14a_rfc_unique_key_uidvalidity
Create Date: 2026-01-02

Fügt Embedding-Felder zu raw_emails hinzu für semantische Suche.
Embeddings sind NICHT verschlüsselt (nicht reversibel zu Klartext).
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = 'ph15_semantic_search'
down_revision = 'ph14a_rfc_unique_key_uidvalidity'  # Anpassen falls andere Migration
branch_labels = None
depends_on = None


def upgrade():
    """Fügt Embedding-Spalten zu raw_emails hinzu."""
    
    # Email Embedding (384 floats × 4 bytes = 1536 bytes pro Email)
    # LargeBinary für numpy array als bytes
    op.execute("""
        ALTER TABLE raw_emails 
        ADD COLUMN email_embedding BLOB DEFAULT NULL;
    """)
    
    # Embedding-Metadaten
    op.execute("""
        ALTER TABLE raw_emails 
        ADD COLUMN embedding_model VARCHAR(50) DEFAULT NULL;
    """)
    
    op.execute("""
        ALTER TABLE raw_emails 
        ADD COLUMN embedding_generated_at DATETIME DEFAULT NULL;
    """)
    
    # Index für schnelle Filterung (nur Emails MIT Embedding)
    op.create_index(
        'ix_raw_emails_has_embedding',
        'raw_emails',
        ['embedding_generated_at'],
        if_not_exists=True
    )


def downgrade():
    """Entfernt Embedding-Spalten."""
    
    op.drop_index('ix_raw_emails_has_embedding', table_name='raw_emails')
    op.drop_column('raw_emails', 'embedding_generated_at')
    op.drop_column('raw_emails', 'embedding_model')
    op.drop_column('raw_emails', 'email_embedding')
