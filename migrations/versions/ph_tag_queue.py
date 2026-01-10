"""Phase TAG-QUEUE: Tag Suggestion Queue

Revision ID: ph_tag_queue
Revises: ph17_semantic_search
Create Date: 2026-01-05

Neue Tabelle für KI-vorgeschlagene Tags in einer Warteschlange.
User kann approve/reject/merge diese Vorschläge.
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, UTC


revision = 'ph_tag_queue'
down_revision = 'ph17_semantic_search'
branch_labels = None
depends_on = None


def upgrade():
    """Erstellt tag_suggestion_queue Tabelle und User-Setting."""
    
    # Neue Tabelle: tag_suggestion_queue
    op.create_table(
        'tag_suggestion_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('suggested_name', sa.String(50), nullable=False),
        sa.Column('source_email_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(UTC)),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),  # pending, approved, rejected, merged
        sa.Column('merged_into_tag_id', sa.Integer(), nullable=True),
        sa.Column('suggestion_count', sa.Integer(), nullable=False, default=1),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_email_id'], ['processed_emails.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['merged_into_tag_id'], ['email_tags.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('user_id', 'suggested_name', name='uq_user_pending_suggestion'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # User-Setting: enable_tag_suggestion_queue (Default: False)
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN enable_tag_suggestion_queue BOOLEAN DEFAULT 0;
    """)


def downgrade():
    """Rollback: Löscht tag_suggestion_queue Tabelle und User-Setting."""
    
    # Entferne User-Setting
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS enable_tag_suggestion_queue;
    """)
    
    # Entferne Tabelle
    op.drop_table('tag_suggestion_queue')
