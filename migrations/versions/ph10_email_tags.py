"""Phase 10: Email-Tags System

Revision ID: ph10_email_tags
Revises: z1z2z3z4z5z6
Create Date: 2025-12-28

Erstellt:
- email_tags Tabelle (id, name, color, user_id, created_at)
- email_tag_assignments Tabelle (id, email_id, tag_id, assigned_at)
- Constraints: unique(user_id, name), unique(email_id, tag_id)
- CASCADE DELETE: User löschen → Tags löschen → Assignments löschen
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = 'ph10_email_tags'
down_revision = 'a8d9d8855a82'  # change_salt_to_text
branch_labels = None
depends_on = None


def upgrade():
    # Erstelle email_tags Tabelle
    op.create_table(
        'email_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_user_tag_name')
    )
    op.create_index(op.f('ix_email_tags_user_id'), 'email_tags', ['user_id'], unique=False)

    # Erstelle email_tag_assignments Tabelle
    op.create_table(
        'email_tag_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['email_id'], ['processed_emails.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['email_tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email_id', 'tag_id', name='uq_email_tag')
    )
    op.create_index(op.f('ix_email_tag_assignments_email_id'), 'email_tag_assignments', ['email_id'], unique=False)
    op.create_index(op.f('ix_email_tag_assignments_tag_id'), 'email_tag_assignments', ['tag_id'], unique=False)


def downgrade():
    # Lösche Tabellen in umgekehrter Reihenfolge (wegen FKs)
    op.drop_index(op.f('ix_email_tag_assignments_tag_id'), table_name='email_tag_assignments')
    op.drop_index(op.f('ix_email_tag_assignments_email_id'), table_name='email_tag_assignments')
    op.drop_table('email_tag_assignments')
    
    op.drop_index(op.f('ix_email_tags_user_id'), table_name='email_tags')
    op.drop_table('email_tags')
