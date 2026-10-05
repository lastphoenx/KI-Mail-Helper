"""Add calendar invite fields (is_calendar_invite, encrypted_calendar_data)

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-20 10:30:00.000000

Phase 25: Termineinladungen erkennen und anzeigen
- is_calendar_invite: Boolean-Flag für schnelle Filterung
- encrypted_calendar_data: Verschlüsseltes JSON mit Event-Details
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Phase 25: Kalenderdaten für Termineinladungen
    op.add_column('raw_emails', sa.Column('is_calendar_invite', sa.Boolean(), nullable=True, default=False))
    op.add_column('raw_emails', sa.Column('encrypted_calendar_data', sa.Text(), nullable=True))
    
    # Index für schnelle Filterung nach Termineinladungen
    op.create_index('ix_raw_emails_is_calendar_invite', 'raw_emails', ['is_calendar_invite'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_raw_emails_is_calendar_invite', table_name='raw_emails')
    op.drop_column('raw_emails', 'encrypted_calendar_data')
    op.drop_column('raw_emails', 'is_calendar_invite')
