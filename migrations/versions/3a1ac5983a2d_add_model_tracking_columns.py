"""Add model tracking columns

Revision ID: 3a1ac5983a2d
Revises: b899fc331a19
Create Date: 2025-12-25 14:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a1ac5983a2d'
down_revision: Union[str, Sequence[str], None] = 'b899fc331a19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = 'processed_emails'


def _get_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col['name'] for col in inspector.get_columns(TABLE)}


def upgrade() -> None:
    existing = _get_columns()

    if 'base_provider' not in existing:
        op.add_column(TABLE, sa.Column('base_provider', sa.String(length=50), nullable=True))
    if 'base_model' not in existing:
        op.add_column(TABLE, sa.Column('base_model', sa.String(length=100), nullable=True))
    if 'optimize_provider' not in existing:
        op.add_column(TABLE, sa.Column('optimize_provider', sa.String(length=50), nullable=True))
    if 'optimize_model' not in existing:
        op.add_column(TABLE, sa.Column('optimize_model', sa.String(length=100), nullable=True))


def downgrade() -> None:
    existing = _get_columns()

    if 'optimize_model' in existing:
        op.drop_column(TABLE, 'optimize_model')
    if 'optimize_provider' in existing:
        op.drop_column(TABLE, 'optimize_provider')
    if 'base_model' in existing:
        op.drop_column(TABLE, 'base_model')
    if 'base_provider' in existing:
        op.drop_column(TABLE, 'base_provider')
