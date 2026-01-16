"""Phase 22b: Add encrypted_entity_map to raw_emails

Revision ID: ph22b_add_entity_map
Revises: ph22_sanitization_storage
Create Date: 2026-01-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'ph22b_add_entity_map'
down_revision = 'ph22_sanitization_storage'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Fügt encrypted_entity_map zur raw_emails Tabelle hinzu"""
    op.add_column('raw_emails',
        sa.Column('encrypted_entity_map', sa.Text, nullable=True)
    )

def downgrade() -> None:
    """Entfernt encrypted_entity_map aus raw_emails"""
    op.drop_column('raw_emails', 'encrypted_entity_map')
