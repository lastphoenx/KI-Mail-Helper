"""Phase 13C Part 5: Extended Fetch Filters

Revision ID: ph13c_p5_fetch_filters
Revises: phG2_auto_rules
Create Date: 2026-01-03

Phase 13C Part 5: Erweiterte Fetch-Filter
- SINCE Datum (nur Mails ab diesem Datum)
- Nur ungelesene (UNSEEN)
- Ordner Include/Exclude Listen
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ph13c_p5_fetch_filters'
down_revision: Union[str, Sequence[str], None] = 'phG2_auto_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Phase 13C Part 5: Erweiterte Fetch-Filter für Initial-Sync"""
    
    # SINCE-Datum: Nur Mails nach diesem Datum fetchen
    op.add_column('users', sa.Column('fetch_since_date', sa.Date(), nullable=True))
    
    # Nur ungelesene Mails
    op.add_column('users', sa.Column('fetch_unseen_only', sa.Boolean(), nullable=True))
    
    # Ordner-Filter (JSON-Array als Text)
    # Include: Nur diese Ordner fetchen (Whitelist)
    op.add_column('users', sa.Column('fetch_include_folders', sa.Text(), nullable=True))
    # Exclude: Diese Ordner ignorieren (Blacklist)  
    op.add_column('users', sa.Column('fetch_exclude_folders', sa.Text(), nullable=True))
    
    # Setze Defaults
    op.execute('UPDATE users SET fetch_unseen_only = 0 WHERE fetch_unseen_only IS NULL')
    # fetch_include_folders = NULL bedeutet "alle Ordner"
    # fetch_exclude_folders = NULL bedeutet "keine Ausschlüsse"


def downgrade() -> None:
    """Rollback"""
    op.drop_column('users', 'fetch_exclude_folders')
    op.drop_column('users', 'fetch_include_folders')
    op.drop_column('users', 'fetch_unseen_only')
    op.drop_column('users', 'fetch_since_date')
