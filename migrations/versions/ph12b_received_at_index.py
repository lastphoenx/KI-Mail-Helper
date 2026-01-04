"""Phase 12b: Received_at Index für Performance-Optimierung

Revision ID: ph12b_received_at_index
Revises: ph12_metadata_enrichment
Create Date: 2025-12-31

Fügt Index auf received_at Spalte für schnellere Thread-Queries hinzu.
Dies ist essentiell für:
- Sortierung nach Empfangsdatum
- Thread-Grouping-Operationen
- Range-Queries bei Email-Filtering
"""

from alembic import op
import sqlalchemy as sa


revision = 'ph12b_received_at_index'
down_revision = 'ph12_metadata_enrichment'
branch_labels = None
depends_on = None


def upgrade():
    """Fügt Index auf received_at hinzu."""
    op.create_index(
        'ix_raw_emails_received_at',
        'raw_emails',
        ['received_at'],
        if_not_exists=True
    )


def downgrade():
    """Entfernt den Index."""
    op.drop_index('ix_raw_emails_received_at', table_name='raw_emails')
