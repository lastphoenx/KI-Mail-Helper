"""Phase G.2: Auto-Action Rules Engine - Database Migration

Revision ID: phG2_auto_rules
Revises: c16e532f436d
Create Date: 2026-01-03 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, UTC

# revision identifiers, used by Alembic.
revision = 'phG2_auto_rules'
down_revision = 'c4ab07bd3f10'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create auto_rules table for Phase G.2 Auto-Action Rules Engine
    
    Features:
    - Conditional matching (sender, subject, body, attachments, etc.)
    - Actions (move, flag, mark read, apply tags, etc.)
    - Priority-based execution order
    - Statistics tracking (times triggered, last triggered)
    """
    
    op.create_table(
        'auto_rules',
        
        # Primary Key
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        
        # Foreign Key to User
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        
        # Rule Metadata
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('priority', sa.Integer(), default=100, nullable=False),  # Lower = higher priority
        
        # Conditions (JSON-encoded)
        # Example: {
        #   "match_mode": "all",  # "all" (AND) or "any" (OR)
        #   "sender_contains": "newsletter",
        #   "subject_regex": "\\[SPAM\\].*",
        #   "has_attachment": true
        # }
        sa.Column('conditions_json', sa.Text(), nullable=False, default='{}'),
        
        # Actions (JSON-encoded)
        # Example: {
        #   "move_to_folder": "Archive",
        #   "mark_as_read": true,
        #   "apply_tag": "Newsletter",
        #   "stop_processing": false
        # }
        sa.Column('actions_json', sa.Text(), nullable=False, default='{}'),
        
        # Statistics
        sa.Column('times_triggered', sa.Integer(), default=0, nullable=False),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), default=datetime.now(UTC), nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.now(UTC), onupdate=datetime.now(UTC), nullable=False),
    )
    
    # Indices for performance
    op.create_index('ix_auto_rules_user_id', 'auto_rules', ['user_id'])
    op.create_index('ix_auto_rules_is_active', 'auto_rules', ['is_active'])
    op.create_index('ix_auto_rules_priority', 'auto_rules', ['priority'])
    
    # Add flag to RawEmail: auto_rules_processed
    # Tracks whether email has been processed by auto-rules
    # SQLite workaround: Add as nullable first, set default, then make NOT NULL
    op.add_column('raw_emails', sa.Column('auto_rules_processed', sa.Boolean(), nullable=True))
    op.execute('UPDATE raw_emails SET auto_rules_processed = 0 WHERE auto_rules_processed IS NULL')
    # Note: SQLite doesn't support ALTER COLUMN, but the nullable=True is fine for our use case
    op.create_index('ix_raw_emails_auto_rules_processed', 'raw_emails', ['auto_rules_processed'])
    
    print("✅ Phase G.2: auto_rules table created")
    print("✅ Added auto_rules_processed flag to raw_emails")


def downgrade():
    """
    Rollback Phase G.2 migration
    """
    op.drop_index('ix_raw_emails_auto_rules_processed', 'raw_emails')
    op.drop_column('raw_emails', 'auto_rules_processed')
    
    op.drop_index('ix_auto_rules_priority', 'auto_rules')
    op.drop_index('ix_auto_rules_is_active', 'auto_rules')
    op.drop_index('ix_auto_rules_user_id', 'auto_rules')
    
    op.drop_table('auto_rules')
    
    print("🔙 Phase G.2: auto_rules table dropped")
