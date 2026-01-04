"""Add rebase_at timestamp to ProcessedEmail

Revision ID: ph15_add_rebase_timestamp
Revises: ph14f_deprecate_uid_field
Create Date: 2026-01-02

===== PHASE 15: REBASE TIMESTAMP =====

Wenn eine Email verschoben wird (move_to_trash oder move_to_folder),
wird eine IMAP COPY+DELETE Operation durchgeführt (RFC 4315 MOVE).
Dies nennen wir einen "Rebase" - die Email erhält eine neue UID.

ÄNDERUNGEN:
1. ProcessedEmail.rebase_at Spalte hinzugefügt (DateTime, nullable)
2. Bei Rebase wird rebase_at aktualisiert
3. HTML zeigt rebase_at statt processed_at, wenn vorhanden
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ph15_add_rebase_timestamp'
down_revision: Union[str, Sequence[str], None] = 'ph14f_deprecate_uid_field'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add rebase_at column to processed_emails."""
    op.add_column('processed_emails', sa.Column('rebase_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove rebase_at column from processed_emails."""
    op.drop_column('processed_emails', 'rebase_at')
