"""Rename auto-rule dispositions to match TrashCategory

DELETABLE -> SAFE
PROTECTED -> IMPORTANT
JUNK -> SCAM

Revision ID: f1a2b3c4d5e6
Revises: 46a0f5ab4550
Create Date: 2026-01-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '46a0f5ab4550'
branch_labels = None
depends_on = None


def _create_final_table() -> None:
    """Fresh DBs that never had the standalone script: create current schema."""
    op.create_table(
        'audit_auto_delete_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('sender_pattern', sa.String(length=255), nullable=True),
        sa.Column('subject_pattern', sa.String(length=255), nullable=True),
        sa.Column('disposition', sa.String(length=20), nullable=False),
        sa.Column('max_age_days', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('SAFE', 'IMPORTANT', 'SCAM', 'REVIEW')",
            name='ck_audit_auto_delete_disposition',
        ),
        sa.CheckConstraint(
            'sender_pattern IS NOT NULL OR subject_pattern IS NOT NULL',
            name='ck_audit_auto_delete_has_pattern',
        ),
        sa.ForeignKeyConstraint(['account_id'], ['mail_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'account_id', 'sender_pattern', 'subject_pattern',
            name='uq_audit_auto_delete_rule',
        ),
    )
    op.create_index(
        'idx_audit_auto_delete_user',
        'audit_auto_delete_rules',
        ['user_id', 'account_id'],
        unique=False,
    )


def _disposition_constraint_sql() -> str | None:
    conn = op.get_bind()
    row = conn.execute(text("""
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'audit_auto_delete_rules'::regclass
          AND conname = 'ck_audit_auto_delete_disposition'
    """)).fetchone()
    return row[0] if row else None


def upgrade():
    """Create table if missing (fresh install), else migrate old disposition names."""
    conn = op.get_bind()
    if not inspect(conn).has_table('audit_auto_delete_rules'):
        _create_final_table()
        return

    constraint_sql = _disposition_constraint_sql()
    if constraint_sql and 'SAFE' in constraint_sql:
        return

    if constraint_sql:
        op.drop_constraint('ck_audit_auto_delete_disposition', 'audit_auto_delete_rules', type_='check')
    op.execute("""
        UPDATE audit_auto_delete_rules
        SET disposition = CASE
            WHEN disposition = 'DELETABLE' THEN 'SAFE'
            WHEN disposition = 'PROTECTED' THEN 'IMPORTANT'
            WHEN disposition = 'JUNK' THEN 'SCAM'
            ELSE disposition
        END
        WHERE disposition IN ('DELETABLE', 'PROTECTED', 'JUNK')
    """)
    op.create_check_constraint(
        'ck_audit_auto_delete_disposition',
        'audit_auto_delete_rules',
        "disposition IN ('SAFE', 'IMPORTANT', 'SCAM', 'REVIEW')",
    )


def downgrade():
    """Revert disposition values back to original names."""
    conn = op.get_bind()
    if not inspect(conn).has_table('audit_auto_delete_rules'):
        return

    constraint_sql = _disposition_constraint_sql()
    if constraint_sql and 'DELETABLE' in constraint_sql:
        return

    op.drop_constraint('ck_audit_auto_delete_disposition', 'audit_auto_delete_rules', type_='check')
    op.execute("""
        UPDATE audit_auto_delete_rules
        SET disposition = CASE
            WHEN disposition = 'SAFE' THEN 'DELETABLE'
            WHEN disposition = 'IMPORTANT' THEN 'PROTECTED'
            WHEN disposition = 'SCAM' THEN 'JUNK'
            WHEN disposition = 'REVIEW' THEN 'JUNK'
            ELSE disposition
        END
        WHERE disposition IN ('SAFE', 'IMPORTANT', 'SCAM', 'REVIEW')
    """)
    op.create_check_constraint(
        'ck_audit_auto_delete_disposition',
        'audit_auto_delete_rules',
        "disposition IN ('DELETABLE', 'PROTECTED', 'JUNK')",
    )
