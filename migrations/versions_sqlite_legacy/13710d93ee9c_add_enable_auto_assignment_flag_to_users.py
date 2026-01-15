"""Add enable_auto_assignment flag to users

Revision ID: 13710d93ee9c
Revises: b6d112c59087
Create Date: 2026-01-06 12:37:31.258534

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13710d93ee9c'
down_revision: Union[str, Sequence[str], None] = 'b6d112c59087'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add enable_auto_assignment flag to users table
    op.add_column('users', 
        sa.Column('enable_auto_assignment', sa.Boolean(), 
                  nullable=False, server_default='0'))
    
    # Add auto_assigned flag to email_tag_assignments table
    op.add_column('email_tag_assignments',
        sa.Column('auto_assigned', sa.Boolean(),
                  nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove columns
    op.drop_column('email_tag_assignments', 'auto_assigned')
    op.drop_column('users', 'enable_auto_assignment')
