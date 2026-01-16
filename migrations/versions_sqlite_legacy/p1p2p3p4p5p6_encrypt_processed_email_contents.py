"""encrypt_processed_email_contents

Revision ID: p1p2p3p4p5p6
Revises: z1z2z3z4z5z6
Create Date: 2025-12-26 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p1p2p3p4p5p6'
down_revision = 'z1z2z3z4z5z6'
branch_labels = None
depends_on = None


def upgrade():
    """
    Migration für Zero-Knowledge-Verschlüsselung von ProcessedEmail-Inhalten:
    
    - summary_de → encrypted_summary_de
    - text_de → encrypted_text_de
    - tags → encrypted_tags
    - user_correction_note → encrypted_correction_note
    """
    
    # ProcessedEmail: Neue verschlüsselte Felder hinzufügen
    op.add_column('processed_emails', sa.Column('encrypted_summary_de', sa.Text(), nullable=True))
    op.add_column('processed_emails', sa.Column('encrypted_text_de', sa.Text(), nullable=True))
    op.add_column('processed_emails', sa.Column('encrypted_tags', sa.Text(), nullable=True))
    op.add_column('processed_emails', sa.Column('encrypted_correction_note', sa.Text(), nullable=True))
    
    # WARNUNG: Bestehende Daten können nicht automatisch verschlüsselt werden
    # da der Master-Key des Users benötigt wird (Zero-Knowledge)
    # 
    # Optionen:
    # 1. Alle ProcessedEmails löschen (Neustart)
    # 2. Manuelle Migration via Script mit User-Login
    # 3. User muss E-Mails neu verarbeiten lassen
    
    # Alte unverschlüsselte Felder entfernen (nach Migration der Daten)
    # ACHTUNG: Nur aktivieren wenn Daten migriert sind!
    # op.drop_column('processed_emails', 'summary_de')
    # op.drop_column('processed_emails', 'text_de')
    # op.drop_column('processed_emails', 'tags')
    # op.drop_column('processed_emails', 'user_correction_note')


def downgrade():
    """
    Rollback: Verschlüsselte Felder entfernen
    
    ACHTUNG: Datenverlust! Verschlüsselte Daten können nicht
    zurück in Klartext konvertiert werden ohne Master-Key.
    """
    
    op.drop_column('processed_emails', 'encrypted_correction_note')
    op.drop_column('processed_emails', 'encrypted_tags')
    op.drop_column('processed_emails', 'encrypted_text_de')
    op.drop_column('processed_emails', 'encrypted_summary_de')
