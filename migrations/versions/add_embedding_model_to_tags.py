"""Add embedding_model tracking to email_tags

Revision ID: add_embedding_model_to_tags
Revises: add_stable_identifier
Create Date: 2026-01-24

Fügt embedding_model Felder zu email_tags hinzu, um Modell-Kompatibilität
zwischen Tag-Embeddings und Email-Embeddings zu gewährleisten.

KRITISCH: Verhindert Dimensions-Mismatch beim Tag-Vergleich!
- Tags speichern jetzt, mit welchem Model ihr Embedding erstellt wurde
- Bei Model-Wechsel können Tags zurückgesetzt werden
- Runtime-Prüfung kann inkompatible Embeddings erkennen
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_embedding_model_to_tags'
down_revision = '7e6b745cb05c'  # add_processing_status_and_retry_tracking
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add embedding_model columns to email_tags."""
    
    # Model für learned_embedding (aggregiert aus assigned emails)
    op.add_column('email_tags', 
        sa.Column('learned_embedding_model', sa.String(length=50), nullable=True)
    )
    
    # Model für negative_embedding (aggregiert aus rejected emails)
    op.add_column('email_tags', 
        sa.Column('negative_embedding_model', sa.String(length=50), nullable=True)
    )
    
    # Erstelle Index für schnelle Model-Lookups
    op.create_index(
        'ix_email_tags_learned_embedding_model',
        'email_tags',
        ['learned_embedding_model'],
        unique=False
    )


def downgrade() -> None:
    """Remove embedding_model columns from email_tags."""
    
    op.drop_index('ix_email_tags_learned_embedding_model', table_name='email_tags')
    op.drop_column('email_tags', 'negative_embedding_model')
    op.drop_column('email_tags', 'learned_embedding_model')
