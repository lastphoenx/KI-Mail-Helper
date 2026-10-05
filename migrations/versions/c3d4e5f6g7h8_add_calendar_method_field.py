"""Add calendar_method field for list view differentiation

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-18 19:30:00.000000

Phase 25b: Unverschlüsseltes Feld für Kalender-Methode
- calendar_method: REQUEST, REPLY, CANCEL (für Listen-Badges ohne Entschlüsselung)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('raw_emails', sa.Column('calendar_method', sa.String(20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('raw_emails', 'calendar_method')
