"""P1-002: Remove deleted_verm columns

Revision ID: p1_002_remove_deleted_verm
Revises: ph_y_spacy_hybrid
Create Date: 2026-01-08 15:30:00

P1-002: Data Clarity - deleted_verm Deprecation
Entfernt deprecated deleted_verm Spalten aus raw_emails und processed_emails.
Nur deleted_at wird noch genutzt für Soft-Delete.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p1_002_remove_deleted_verm'
down_revision = 'ph_y_spacy_hybrid'
branch_labels = None
depends_on = None


def upgrade():
    """Entfernt deleted_verm Spalten"""
    
    # SQLite: Direkt droppen
    with op.batch_alter_table('raw_emails') as batch_op:
        batch_op.drop_column('deleted_verm')
    
    with op.batch_alter_table('processed_emails') as batch_op:
        batch_op.drop_column('deleted_verm')


def downgrade():
    """Fügt deleted_verm Spalten wieder hinzu (falls Rollback nötig)"""
    
    with op.batch_alter_table('raw_emails') as batch_op:
        batch_op.add_column(sa.Column('deleted_verm', sa.Boolean(), default=False))
    
    with op.batch_alter_table('processed_emails') as batch_op:
        batch_op.add_column(sa.Column('deleted_verm', sa.Boolean(), default=False))
