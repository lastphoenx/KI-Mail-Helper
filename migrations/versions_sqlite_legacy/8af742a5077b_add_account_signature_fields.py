"""add_account_signature_fields

Revision ID: 8af742a5077b
Revises: 28d68dd1186b
Create Date: 2026-01-06 20:47:54.814816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8af742a5077b'
down_revision: Union[str, Sequence[str], None] = '28d68dd1186b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add signature fields to mail_accounts table
    op.add_column('mail_accounts', sa.Column('signature_enabled', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('mail_accounts', sa.Column('encrypted_signature_text', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove signature fields from mail_accounts table
    op.drop_column('mail_accounts', 'encrypted_signature_text')
    op.drop_column('mail_accounts', 'signature_enabled')
