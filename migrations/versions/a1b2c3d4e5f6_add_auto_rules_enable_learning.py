"""add auto_rules enable_learning

Revision ID: a1b2c3d4e5f6
Revises: 07f565a456dd
Create Date: 2026-01-18

Fügt enable_learning Spalte zur auto_rules Tabelle hinzu.
Wenn aktiviert, werden Tags dieser Regel als Lernbeispiele verwendet.
Default: False (sicherer Modus - Auto-Rules beeinflussen Tag-Learning nicht)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '07f565a456dd'
branch_labels = None
depends_on = None


def upgrade():
    # Add enable_learning column to auto_rules
    # Default: False - Auto-Rules beeinflussen Tag-Learning nicht
    op.add_column('auto_rules', sa.Column('enable_learning', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('auto_rules', 'enable_learning')
