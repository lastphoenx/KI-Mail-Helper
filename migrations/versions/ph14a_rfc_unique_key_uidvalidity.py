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
down_revision = 'c16e532f436d'  # Phase 13C Part 4 User Prefs
branch_labels = None
depends_on = None


def upgrade():
    """Migriert zu RFC-konformem Unique Key mit UIDVALIDITY"""
    
    conn = op.get_bind()
    
    # =================================================================
    # 1. RAWEMAIL: Table Recreation (SQLite Standard Pattern)
    # =================================================================
    
    # Check if imap_uidvalidity exists (idempotent)
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('raw_emails')]
    has_uidvalidity = 'imap_uidvalidity' in columns
    
    # Update imap_folder NULLs to 'INBOX'
    op.execute(text("UPDATE raw_emails SET imap_folder = 'INBOX' WHERE imap_folder IS NULL"))
    
    # Create new table with correct schema
    op.execute(text("""
        CREATE TABLE raw_emails_new (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            mail_account_id INTEGER NOT NULL,
            uid VARCHAR(255) NOT NULL,
            encrypted_sender TEXT NOT NULL,
            encrypted_subject TEXT,
            encrypted_body TEXT,
            received_at DATETIME NOT NULL,
            created_at DATETIME,
            deleted_at DATETIME,
            deleted_verm BOOLEAN,
            imap_uid INTEGER,
            imap_folder VARCHAR(200) NOT NULL DEFAULT 'INBOX',
            imap_uidvalidity INTEGER,
            imap_flags VARCHAR(500),
            imap_last_seen_at DATETIME,
            message_id VARCHAR(255),
            encrypted_in_reply_to TEXT,
            parent_uid VARCHAR(255),
            thread_id VARCHAR(36),
            imap_is_seen BOOLEAN,
            imap_is_answered BOOLEAN,
            imap_is_flagged BOOLEAN,
            imap_is_deleted BOOLEAN DEFAULT 0,
            imap_is_draft BOOLEAN DEFAULT 0,
            encrypted_to TEXT,
            encrypted_cc TEXT,
            encrypted_bcc TEXT,
            encrypted_reply_to TEXT,
            message_size INTEGER,
            encrypted_references TEXT,
            content_type VARCHAR(100),
            charset VARCHAR(50),
            has_attachments BOOLEAN DEFAULT 0,
            last_flag_sync_at DATETIME,
            CONSTRAINT uq_raw_emails_rfc_unique UNIQUE (user_id, mail_account_id, imap_folder, imap_uidvalidity, imap_uid),
            FOREIGN KEY(user_id) REFERENCES users (id),
            FOREIGN KEY(mail_account_id) REFERENCES mail_accounts (id)
        )
    """))
    
    # Copy data (convert imap_uid String → Integer)
    op.execute(text("""
        INSERT INTO raw_emails_new
        SELECT 
            id, user_id, mail_account_id, uid,
            encrypted_sender, encrypted_subject, encrypted_body,
            received_at, created_at, deleted_at, deleted_verm,
            CAST(imap_uid AS INTEGER),
            COALESCE(imap_folder, 'INBOX'),
            """ + ('imap_uidvalidity' if has_uidvalidity else 'NULL') + """,
            imap_flags, imap_last_seen_at,
            message_id, encrypted_in_reply_to, parent_uid, thread_id,
            imap_is_seen, imap_is_answered, imap_is_flagged,
            imap_is_deleted, imap_is_draft,
            encrypted_to, encrypted_cc, encrypted_bcc, encrypted_reply_to,
            message_size, encrypted_references,
            content_type, charset, has_attachments, last_flag_sync_at
        FROM raw_emails
    """))
    
    # Drop old table
    op.execute(text("DROP TABLE raw_emails"))
    
    # Rename new table
    op.execute(text("ALTER TABLE raw_emails_new RENAME TO raw_emails"))
    
    # Recreate indexes
    op.create_index('ix_raw_emails_user_id', 'raw_emails', ['user_id'])
    op.create_index('ix_raw_emails_mail_account_id', 'raw_emails', ['mail_account_id'])
    op.create_index('ix_raw_emails_imap_uid', 'raw_emails', ['imap_uid'])
    op.create_index('ix_raw_emails_imap_uidvalidity', 'raw_emails', ['imap_uidvalidity'])
    op.create_index('ix_raw_emails_received_at', 'raw_emails', ['received_at'])
    op.create_index('ix_raw_emails_message_id', 'raw_emails', ['message_id'])
    op.create_index('ix_raw_emails_parent_uid', 'raw_emails', ['parent_uid'])
    op.create_index('ix_raw_emails_thread_id', 'raw_emails', ['thread_id'])
    op.create_index('ix_raw_emails_imap_is_seen', 'raw_emails', ['imap_is_seen'])
    
    # Performance index (account, folder, uid)
    op.create_index('ix_raw_emails_account_folder_uid', 'raw_emails', 
                   ['mail_account_id', 'imap_folder', 'imap_uid'])
    
    # =================================================================
    # 2. MAILACCOUNT: folder_uidvalidity (JSON)
    # =================================================================
    
    # Check if column exists
    columns = [col['name'] for col in inspector.get_columns('mail_accounts')]
    if 'folder_uidvalidity' not in columns:
        op.add_column('mail_accounts',
            sa.Column('folder_uidvalidity', sa.Text(), nullable=True))
    
    # =================================================================
    # HINWEIS FÜR BESTEHENDE DATEN
    # =================================================================
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║  PHASE 14A MIGRATION ERFOLGREICH                              ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║                                                               ║
    ║  🚨 KRITISCH: Unique Constraint ist UNWIRKSAM ohne UIDVALIDITY║
    ║                                                               ║
    ║  Problem: NULL != NULL in SQL → Duplikate möglich!           ║
    ║  Lösung: UIDVALIDITY-Daten vom Server holen                  ║
    ║                                                               ║
    ║  ⚠️⚠️⚠️ NÄCHSTER SCHRITT ZWINGEND ERFORDERLICH: ⚠️⚠️⚠️         ║
    ║                                                               ║
    ║  python scripts/migrate_uidvalidity_data.py                   ║
    ║                                                               ║
    ║  Das Script:                                                  ║
    ║  1. Fragt UIDVALIDITY vom Server für alle Ordner ab          ║
    ║  2. Befüllt raw_emails.imap_uidvalidity                       ║
    ║  3. Befüllt mail_accounts.folder_uidvalidity                  ║
    ║  4. Aktiviert Unique Constraint vollständig                   ║
    ║                                                               ║
    ║  Ohne Migration:                                              ║
    ║  ❌ Alte Mails haben NULL UIDVALIDITY                         ║
    ║  ❌ Unique Constraint ineffektiv                              ║
    ║  ❌ Duplikate möglich                                         ║
    ║  ❌ Daten-Integrität gefährdet                                ║
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
