"""Phase 11d: Sender-Patterns für konsistente Klassifizierung

Revision ID: ph11d_sender_patterns
Revises: ph10_email_tags
Create Date: 2025-01-17

Erstellt Tabelle für gelernte Absender-Muster.
Privacy-preserving: Absenderadressen werden als SHA-256 Hash gespeichert.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ph11d_sender_patterns'
down_revision = 'ph10_email_tags'
branch_labels = None
depends_on = None


def upgrade():
    """Erstellt sender_patterns Tabelle."""
    op.create_table(
        'sender_patterns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('sender_hash', sa.String(64), nullable=False, index=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('is_newsletter', sa.Boolean(), nullable=True),
        sa.Column('email_count', sa.Integer(), default=1),
        sa.Column('correction_count', sa.Integer(), default=0),
        sa.Column('confidence', sa.Integer(), default=50),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', 'sender_hash', name='uq_user_sender_pattern')
    )


def downgrade():
    """Entfernt sender_patterns Tabelle."""
    op.drop_table('sender_patterns')
