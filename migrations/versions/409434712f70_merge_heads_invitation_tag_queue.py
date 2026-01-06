"""Merge heads: invitation+tag_queue

Revision ID: 409434712f70
Revises: ph_inv_001, ph_tag_queue
Create Date: 2026-01-06 11:23:43.440952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '409434712f70'
down_revision: Union[str, Sequence[str], None] = ('ph_inv_001', 'ph_tag_queue')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
