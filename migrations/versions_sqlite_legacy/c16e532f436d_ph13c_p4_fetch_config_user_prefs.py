"""ph13c_p4_fetch_config_user_prefs

Revision ID: c16e532f436d
Revises: ph13c_fix_unique_constraint_folder_uid
Create Date: 2026-01-01 12:45:17.410996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c16e532f436d'
down_revision: Union[str, Sequence[str], None] = 'ph13c_fix_unique_constraint_folder_uid'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Phase 13C Part 4: User-steuerbare Fetch-Limits
    op.add_column('users', sa.Column('fetch_mails_per_folder', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('fetch_max_total', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('fetch_use_delta_sync', sa.Boolean(), nullable=True))
    
    # Setze Defaults für existierende User
    op.execute('UPDATE users SET fetch_mails_per_folder = 100 WHERE fetch_mails_per_folder IS NULL')
    op.execute('UPDATE users SET fetch_max_total = 0 WHERE fetch_max_total IS NULL')
    op.execute('UPDATE users SET fetch_use_delta_sync = 1 WHERE fetch_use_delta_sync IS NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'fetch_use_delta_sync')
    op.drop_column('users', 'fetch_max_total')
    op.drop_column('users', 'fetch_mails_per_folder')
