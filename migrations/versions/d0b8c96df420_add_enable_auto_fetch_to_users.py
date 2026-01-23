"""add_enable_auto_fetch_to_users

Revision ID: d0b8c96df420
Revises: c3d4e5f6g7h8
Create Date: 2026-01-22 12:26:35.538617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0b8c96df420'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enable_auto_fetch column to users table."""
    op.add_column('users', sa.Column('enable_auto_fetch', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Remove enable_auto_fetch column from users table."""
    op.drop_column('users', 'enable_auto_fetch')
