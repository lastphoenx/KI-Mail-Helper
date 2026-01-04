"""Phase 14f: Remove uid field completely (RFC-konform Key verwendet)

Revision ID: ph14f_deprecate_uid_field
Revises: ph14a_rfc_unique_key_uidvalidity
Create Date: 2026-01-01

===== PHASE 14F: CLEANUP (uid Feld komplett entfernen) =====

Das alte uid Feld (selbst-generierter String/UUID) wird nicht mehr verwendet.
Der RFC-konforme Key (folder, uidvalidity, imap_uid) ersetzt es vollständig.

ÄNDERUNGEN:
1. RawEmail.uid Spalte wird gedroppt
2. Alle Emails haben jetzt imap_uid (Unique Constraint erzwingt das)
3. Kein Fallback mehr nötig

VORHER:
- uid = Column(String(255), nullable=False)  # Selbst generiert
- Unique Constraint ALT: (user_id, account_id, uid)

NACHHER:
- uid Feld existiert nicht mehr!
- Unique Constraint NEU: (user_id, account_id, folder, uidvalidity, imap_uid)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = 'ph14f_deprecate_uid_field'
down_revision = 'ph14a_rfc_unique_key_uidvalidity'
branch_labels = None
depends_on = None


def upgrade():
    """uid Spalte komplett entfernen (DROP COLUMN)"""
    
    print("\n" + "=" * 70)
    print("PHASE 14F: REMOVE UID FIELD")
    print("=" * 70)
    print()
    print("Das alte uid Feld wird komplett entfernt.")
    print("Der RFC-konforme Key (folder, uidvalidity, imap_uid) wird verwendet.")
    print()
    
    conn = op.get_bind()
    
    # SQLite: DROP COLUMN via table recreation
    # Get column list (ohne uid)
    inspector = sa.inspect(conn)
    columns = inspector.get_columns('raw_emails')
    
    # Build column list without 'uid'
    column_names = [col['name'] for col in columns if col['name'] != 'uid']
    column_names_str = ', '.join(column_names)
    
    print(f"📋 Erstelle neue Tabelle ohne uid Spalte...")
    
    # Create new table without uid
    op.execute(text("""
        CREATE TABLE raw_emails_new (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            mail_account_id INTEGER NOT NULL,
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
    
    print(f"📦 Kopiere Daten (ohne uid Spalte)...")
    
    # Copy data (without uid column)
    op.execute(text(f"""
        INSERT INTO raw_emails_new ({column_names_str})
        SELECT {column_names_str}
        FROM raw_emails
    """))
    
    print(f"🗑️  Lösche alte Tabelle...")
    op.execute(text("DROP TABLE raw_emails"))
    
    print(f"♻️  Benenne neue Tabelle um...")
    op.execute(text("ALTER TABLE raw_emails_new RENAME TO raw_emails"))
    
    print(f"🔍 Erstelle Indexes...")
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
    
    print()
    print("=" * 70)
    print("PHASE 14F MIGRATION ERFOLGREICH")
    print("=" * 70)
    print("✅ uid Spalte komplett entfernt!")
    print("✅ Nur noch RFC-konformer Key: (folder, uidvalidity, imap_uid)")
    print()


def downgrade():
    """Downgrade nicht möglich ohne Daten zu verlieren"""
    print("⚠️  Downgrade von Phase 14f nicht implementiert")
    print("   (uid Werte können nicht rekonstruiert werden)")
