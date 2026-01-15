"""Phase F.2: Tag Learning & Descriptions

Revision ID: phf2_tag_learning
Revises: ph17_semantic_search
Create Date: 2026-01-02 19:15:00

Phase F.2 Enhanced Tag-Suggestions:
- description: Optional semantic description for better embeddings
- learned_embedding: Aggregated embedding from assigned emails
- embedding_updated_at: Timestamp for learned_embedding
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'phf2_tag_learning'
down_revision = 'ph17_semantic_search'
branch_labels = None
depends_on = None


def upgrade():
    """Fügt Tag-Description und Learning-Embedding zu email_tags hinzu."""
    
    # Semantische Tag-Beschreibung
    op.execute("""
        ALTER TABLE email_tags 
        ADD COLUMN description TEXT DEFAULT NULL;
    """)
    
    # Gelerntes Embedding (Mittelwert aller assigned email_embeddings)
    # Gleiche Dimension wie email_embedding (384 floats × 4 bytes = 1536 bytes)
    op.execute("""
        ALTER TABLE email_tags 
        ADD COLUMN learned_embedding BLOB DEFAULT NULL;
    """)
    
    # Timestamp wann learned_embedding zuletzt berechnet wurde
    op.execute("""
        ALTER TABLE email_tags 
        ADD COLUMN embedding_updated_at DATETIME DEFAULT NULL;
    """)


def downgrade():
    """Entfernt Tag-Description und Learning-Embedding."""
    
    with op.batch_alter_table('email_tags') as batch_op:
        batch_op.drop_column('description')
        batch_op.drop_column('learned_embedding')
        batch_op.drop_column('embedding_updated_at')
