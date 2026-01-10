"""Separate Optimize-Pass results from initial analysis

Revision ID: ph16_separate_optimize_results
Revises: ph15_add_rebase_timestamp
Create Date: 2026-01-02

===== PHASE 16: SEPARATE OPTIMIZE RESULTS =====

Die Optimize-Pass Ergebnisse sollten die Initial-Analyse-Ergebnisse NICHT überschreiben.
Wir speichern Optimize-Ergebnisse in separaten Feldern.

NEUE SPALTEN:
- optimize_dringlichkeit
- optimize_wichtigkeit
- optimize_kategorie_aktion
- optimize_spam_flag
- optimize_encrypted_summary_de
- optimize_encrypted_text_de
- optimize_encrypted_tags
- optimize_score
- optimize_matrix_x
- optimize_matrix_y
- optimize_farbe
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ph16_separate_optimize_results'
down_revision: Union[str, Sequence[str], None] = 'ph15_add_rebase_timestamp'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add separate optimize result columns to processed_emails."""
    op.add_column('processed_emails', sa.Column('optimize_dringlichkeit', sa.Integer(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_wichtigkeit', sa.Integer(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_kategorie_aktion', sa.String(length=50), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_spam_flag', sa.Boolean(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_encrypted_summary_de', sa.Text(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_encrypted_text_de', sa.Text(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_encrypted_tags', sa.Text(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_score', sa.Integer(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_matrix_x', sa.Integer(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_matrix_y', sa.Integer(), nullable=True))
    op.add_column('processed_emails', sa.Column('optimize_farbe', sa.String(length=10), nullable=True))


def downgrade() -> None:
    """Remove optimize result columns from processed_emails."""
    op.drop_column('processed_emails', 'optimize_farbe')
    op.drop_column('processed_emails', 'optimize_matrix_y')
    op.drop_column('processed_emails', 'optimize_matrix_x')
    op.drop_column('processed_emails', 'optimize_score')
    op.drop_column('processed_emails', 'optimize_encrypted_tags')
    op.drop_column('processed_emails', 'optimize_encrypted_text_de')
    op.drop_column('processed_emails', 'optimize_encrypted_summary_de')
    op.drop_column('processed_emails', 'optimize_spam_flag')
    op.drop_column('processed_emails', 'optimize_kategorie_aktion')
    op.drop_column('processed_emails', 'optimize_wichtigkeit')
    op.drop_column('processed_emails', 'optimize_dringlichkeit')
