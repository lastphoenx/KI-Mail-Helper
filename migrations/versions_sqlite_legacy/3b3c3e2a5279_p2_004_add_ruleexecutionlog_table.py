"""P2-004: Add RuleExecutionLog table

Revision ID: 3b3c3e2a5279
Revises: p1_002_remove_deleted_verm
Create Date: 2026-01-08 20:10:15.468837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b3c3e2a5279'
down_revision: Union[str, Sequence[str], None] = 'p1_002_remove_deleted_verm'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rule_execution_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('mail_account_id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('processed_email_id', sa.Integer(), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mail_account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['auto_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processed_email_id'], ['processed_emails.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indices für Performance
    op.create_index(
        'idx_rule_exec_account_time',
        'rule_execution_logs',
        ['mail_account_id', 'executed_at']
    )
    op.create_index(
        'idx_rule_exec_rule',
        'rule_execution_logs',
        ['rule_id']
    )
    op.create_index(
        'idx_rule_exec_email',
        'rule_execution_logs',
        ['processed_email_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_rule_exec_email', 'rule_execution_logs')
    op.drop_index('idx_rule_exec_rule', 'rule_execution_logs')
    op.drop_index('idx_rule_exec_account_time', 'rule_execution_logs')
    op.drop_table('rule_execution_logs')
