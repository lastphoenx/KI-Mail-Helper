"""merge_phase2_and_p2_004

Revision ID: 25405a1758ce
Revises: 3b3c3e2a5279, phase2_servicetoken_001
Create Date: 2026-01-08 21:38:56.109216

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25405a1758ce'
down_revision: Union[str, Sequence[str], None] = ('3b3c3e2a5279', 'phase2_servicetoken_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
