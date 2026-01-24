"""merge_warnings_and_embedding_tags

Revision ID: de3d584b6293
Revises: add_embedding_model_to_tags, e8f7g8h9i0j1
Create Date: 2026-01-24 01:57:03.626456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de3d584b6293'
down_revision: Union[str, Sequence[str], None] = ('add_embedding_model_to_tags', 'e8f7g8h9i0j1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
