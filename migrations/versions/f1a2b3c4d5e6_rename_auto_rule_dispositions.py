"""Rename auto-rule dispositions to match TrashCategory

DELETABLE -> SAFE
PROTECTED -> IMPORTANT
JUNK -> SCAM

Revision ID: f1a2b3c4d5e6
Revises: c3d4e5f6g7h8
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '46a0f5ab4550'
branch_labels = None
depends_on = None


def upgrade():
    """Migrate disposition values from old names to new TrashCategory-compatible names."""
    
    # 1. ERST den alten Constraint droppen (sonst blockiert er das UPDATE)
    op.drop_constraint('ck_audit_auto_delete_disposition', 'audit_auto_delete_rules', type_='check')
    
    # 2. DANN die Daten migrieren
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
    
    # 3. Neuen Constraint mit erweiterten Werten erstellen
    op.create_check_constraint(
        'ck_audit_auto_delete_disposition',
        'audit_auto_delete_rules',
        "disposition IN ('SAFE', 'IMPORTANT', 'SCAM', 'REVIEW')"
    )


def downgrade():
    """Revert disposition values back to original names."""
    
    # 1. Constraint droppen
    op.drop_constraint('ck_audit_auto_delete_disposition', 'audit_auto_delete_rules', type_='check')
    
    # 2. Daten zurück migrieren (REVIEW hat kein Äquivalent, wird zu JUNK)
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
    
    # 3. Alten Constraint wiederherstellen
    op.create_check_constraint(
        'ck_audit_auto_delete_disposition',
        'audit_auto_delete_rules',
        "disposition IN ('DELETABLE', 'PROTECTED', 'JUNK')"
    )
