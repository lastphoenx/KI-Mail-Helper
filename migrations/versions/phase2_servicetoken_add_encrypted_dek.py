"""Phase 2: ServiceToken - Add encrypted_dek and last_verified_at columns

Revision ID: phase2_servicetoken_001
Revises: phG2_auto_rules
Create Date: 2026-01-08 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'phase2_servicetoken_001'
down_revision: Union[str, Sequence[str], None] = 'phG2_auto_rules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 2: ServiceToken Pattern (SQLite-compatible, idempotent)
    
    Changes:
    1. Add encrypted_dek column (if not exists)
    2. Copy data from master_key to encrypted_dek (if master_key exists)
    3. Drop master_key column (if exists)
    4. Add last_verified_at column (if not exists)
    
    This migration is idempotent - it checks if columns exist before adding them.
    """
    
    from sqlalchemy import inspect
    from alembic import context
    
    conn = context.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('service_tokens')]
    
    # Step 1: Add encrypted_dek column if it doesn't exist
    if 'encrypted_dek' not in columns:
        op.add_column(
            'service_tokens',
            sa.Column('encrypted_dek', sa.Text(), nullable=False, server_default='')
        )
        # Remove server_default after adding
        op.alter_column('service_tokens', 'encrypted_dek', server_default=None)
    
    # Step 2: Copy data from master_key to encrypted_dek (if master_key exists and encrypted_dek is empty)
    if 'master_key' in columns:
        op.execute("""
            UPDATE service_tokens 
            SET encrypted_dek = master_key 
            WHERE master_key IS NOT NULL AND master_key != '' AND (encrypted_dek IS NULL OR encrypted_dek = '')
        """)
        
        # Step 3: Drop old master_key column
        op.drop_column('service_tokens', 'master_key')
    
    # Step 4: Add last_verified_at column if it doesn't exist
    if 'last_verified_at' not in columns:
        op.add_column(
            'service_tokens',
            sa.Column('last_verified_at', sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade: Revert Phase 2 changes
    
    Restores:
    1. encrypted_dek → master_key
    2. Removes last_verified_at
    """
    
    # Step 1: Remove last_verified_at
    op.drop_column('service_tokens', 'last_verified_at')
    
    # Step 2: Add back master_key column
    op.add_column(
        'service_tokens',
        sa.Column('master_key', sa.String(length=255), nullable=True)
    )
    
    # Step 3: Copy data back from encrypted_dek to master_key
    op.execute("""
        UPDATE service_tokens 
        SET master_key = encrypted_dek 
        WHERE encrypted_dek IS NOT NULL
    """)
    
    # Step 4: Drop encrypted_dek column
    op.drop_column('service_tokens', 'encrypted_dek')
