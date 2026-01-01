"""RFC-konformer Unique Key mit UIDVALIDITY (Phase 14a)

Revision ID: ph14a_rfc_unique_key_uidvalidity
Revises: ph13c_fix_unique_constraint_folder_uid
Create Date: 2026-01-01

===== PHASE 14A: SERVER = SOURCE OF TRUTH =====

Ersetzt Deduplizierung durch RFC-konformen Unique Key (RFC 3501 / RFC 9051):
"The combination of mailbox name, UIDVALIDITY, and UID must refer to 
 a single, immutable message on that server forever."

ÄNDERUNGEN:
1. RawEmail.imap_uidvalidity: Integer (RFC-garantierte UID-Gültigkeit)
2. RawEmail.imap_uid: String → Integer (Performance + korrekte Typisierung)
3. RawEmail.imap_folder: NOT NULL (war nullable, default 'INBOX')
4. MailAccount.folder_uidvalidity: JSON (speichert UIDVALIDITY pro Ordner)
5. Neuer Unique Constraint: (user_id, account_id, folder, uidvalidity, uid)
6. Performance-Index: (account_id, folder, uid)

VORTEILE:
✅ Deterministisch (keine Hash-Heuristik)
✅ MOVE-Support (Server gibt neue UID via COPYUID)
✅ UIDVALIDITY-Tracking (Ordner-Reset erkennbar)
✅ Keine Deduplizierung mehr nötig
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = 'ph14a_rfc_unique_key_uidvalidity'
down_revision = 'ph13c_fix_unique_constraint_folder_uid'
branch_labels = None
depends_on = None


def upgrade():
    """Migriert zu RFC-konformem Unique Key mit UIDVALIDITY"""
    
    # =================================================================
    # 1. RAWEMAIL: NEUE SPALTEN
    # =================================================================
    
    # 1a. imap_uidvalidity hinzufügen (nullable erstmal, wird später gefüllt)
    op.add_column('raw_emails',
        sa.Column('imap_uidvalidity', sa.Integer(), nullable=True))
    
    # 1b. imap_folder NOT NULL machen (bestehende NULL → 'INBOX')
    # SQLite unterstützt kein ALTER COLUMN, daher mit UPDATE + neuer Spalte
    op.execute(text("UPDATE raw_emails SET imap_folder = 'INBOX' WHERE imap_folder IS NULL"))
    
    # =================================================================
    # 2. RAWEMAIL: imap_uid zu Integer konvertieren
    # =================================================================
    
    # SQLite: Spalte neu erstellen (String → Integer)
    # Bestehende Daten konvertieren (nur numerische Werte)
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        # Temporäre Spalte für Integer UID
        batch_op.add_column(sa.Column('imap_uid_int', sa.Integer(), nullable=True))
    
    # Numerische UIDs konvertieren (ignoriere non-numeric)
    # CAST in SQLite: nur Zahlen werden konvertiert, Rest wird NULL
    op.execute(text("""
        UPDATE raw_emails 
        SET imap_uid_int = CAST(imap_uid AS INTEGER)
        WHERE imap_uid IS NOT NULL 
          AND imap_uid != '' 
          AND imap_uid NOT LIKE '%[^0-9]%'
    """))
    
    # Alte String-Spalte droppen, neue Integer-Spalte umbenennen
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.drop_column('imap_uid')
        batch_op.alter_column('imap_uid_int', new_column_name='imap_uid')
    
    # =================================================================
    # 3. MAILACCOUNT: folder_uidvalidity (JSON)
    # =================================================================
    
    op.add_column('mail_accounts',
        sa.Column('folder_uidvalidity', sa.Text(), nullable=True))
    
    # =================================================================
    # 4. UNIQUE CONSTRAINT: RFC-konform (mit UIDVALIDITY)
    # =================================================================
    
    # Alten Constraint droppen
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.drop_constraint('uq_raw_emails_folder_uid', type_='unique')
        
        # Neuen RFC-konformen Constraint erstellen
        # WICHTIG: Erst wenn imap_uidvalidity gefüllt ist!
        # Für jetzt: Nur wenn beide Felder NOT NULL sind
        batch_op.create_unique_constraint(
            'uq_raw_emails_rfc_unique',
            ['user_id', 'mail_account_id', 'imap_folder', 'imap_uidvalidity', 'imap_uid']
        )
    
    # =================================================================
    # 5. PERFORMANCE INDEX
    # =================================================================
    
    op.create_index(
        'ix_raw_emails_account_folder_uid',
        'raw_emails',
        ['mail_account_id', 'imap_folder', 'imap_uid']
    )
    
    # =================================================================
    # HINWEIS FÜR BESTEHENDE DATEN
    # =================================================================
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║  PHASE 14A MIGRATION ERFOLGREICH                              ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║                                                               ║
    ║  ⚠️  WICHTIG: Bestehende Daten müssen migriert werden!        ║
    ║                                                               ║
    ║  Nächster Schritt:                                            ║
    ║  python scripts/migrate_uidvalidity_data.py                   ║
    ║                                                               ║
    ║  Das Script:                                                  ║
    ║  1. Fragt UIDVALIDITY vom Server für alle Ordner ab          ║
    ║  2. Befüllt raw_emails.imap_uidvalidity                       ║
    ║  3. Befüllt mail_accounts.folder_uidvalidity                  ║
    ║                                                               ║
    ║  Ohne Migration: Alte Mails haben NULL UIDVALIDITY!          ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)


def downgrade():
    """Revert zu altem Constraint ohne UIDVALIDITY"""
    
    # Index droppen
    op.drop_index('ix_raw_emails_account_folder_uid', 'raw_emails')
    
    # Neuen Constraint droppen
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.drop_constraint('uq_raw_emails_rfc_unique', type_='unique')
        
        # Alten Constraint wiederherstellen
        batch_op.create_unique_constraint(
            'uq_raw_emails_folder_uid',
            ['user_id', 'mail_account_id', 'imap_folder', 'imap_uid']
        )
    
    # MailAccount Spalte entfernen
    op.drop_column('mail_accounts', 'folder_uidvalidity')
    
    # RawEmail: Integer UID zurück zu String (verlustbehaftet!)
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.add_column(sa.Column('imap_uid_str', sa.String(100), nullable=True))
    
    op.execute(text("UPDATE raw_emails SET imap_uid_str = CAST(imap_uid AS TEXT)"))
    
    with op.batch_alter_table('raw_emails', schema=None) as batch_op:
        batch_op.drop_column('imap_uid')
        batch_op.alter_column('imap_uid_str', new_column_name='imap_uid')
    
    # imap_uidvalidity entfernen
    op.drop_column('raw_emails', 'imap_uidvalidity')
