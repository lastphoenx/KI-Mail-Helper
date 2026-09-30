"""add_processing_warnings_to_raw_emails

Revision ID: e8f7g8h9i0j1
Revises: 7e6b745cb05c
Create Date: 2026-01-24 01:40:00.000000

Fügt processing_warnings JSONB-Feld zu raw_emails hinzu.
Dieses Feld speichert nicht-fatale Warnungen (z.B. übersprungene Übersetzung),
während processing_error nur für fatale Fehler verwendet wird.

Struktur von processing_warnings:
[
  {
    "code": "TRANSLATION_UNAVAILABLE",
    "step": "translation",
    "language": "hy",
    "model": "Helsinki-NLP/opus-mt-hy-de",
    "message": "Translation model not available",
    "timestamp": "2026-01-24T01:34:09Z"
  }
]
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e8f7g8h9i0j1'
down_revision = '7e6b745cb05c'
branch_labels = None
depends_on = None


def upgrade():
    """Add processing_warnings JSONB column to raw_emails table."""
    # Add processing_warnings column
    op.add_column(
        'raw_emails',
        sa.Column(
            'processing_warnings',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Non-fatal warnings during processing (JSON array)'
        )
    )
    
    # Create GIN index for efficient JSONB queries
    op.create_index(
        'idx_raw_emails_processing_warnings',
        'raw_emails',
        ['processing_warnings'],
        postgresql_using='gin',
        if_not_exists=True
    )


def downgrade():
    """Remove processing_warnings column from raw_emails table."""
    op.drop_index('idx_raw_emails_processing_warnings', table_name='raw_emails')
    op.drop_column('raw_emails', 'processing_warnings')
