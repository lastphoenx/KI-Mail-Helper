"""Add two-pass optimization support

Revision ID: b899fc331a19
Revises: d1be18ce087b
Create Date: 2025-12-25 09:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b899fc331a19'
down_revision: Union[str, Sequence[str], None] = 'd1be18ce087b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for two-pass optimization."""
    # Add columns to users table for optimize-pass provider config
    op.add_column('users', sa.Column('preferred_ai_provider_optimize', sa.String(length=20), nullable=True, server_default='ollama'))
    op.add_column('users', sa.Column('preferred_ai_model_optimize', sa.String(length=100), nullable=True, server_default='all-minilm:22m'))
    
    # Add columns to processed_emails table for optimization tracking
    op.add_column('processed_emails', sa.Column('optimization_status', sa.String(length=20), nullable=True, server_default='pending'))
    op.add_column('processed_emails', sa.Column('optimization_tried_at', sa.DateTime(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimization_completed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove columns from processed_emails table
    op.drop_column('processed_emails', 'optimization_completed_at')
    op.drop_column('processed_emails', 'optimization_tried_at')
    op.drop_column('processed_emails', 'optimization_status')
    
    # Remove columns from users table
    op.drop_column('users', 'preferred_ai_model_optimize')
    op.drop_column('users', 'preferred_ai_provider_optimize')
