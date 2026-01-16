"""Phase 12: Email Metadata Enrichment für Threading & bessere Queries

Revision ID: ph12_metadata_enrichment
Revises: ph11d_sender_patterns
Create Date: 2025-12-30

Erweitert RawEmail-Tabelle mit:
- Message-ID & In-Reply-To (für Conversation-Threading)
- Boolean Flags statt String (200-300% schneller)
- Thread-ID & Parent-UID (für Conversation-Grouping)
- Extended Envelope Fields (To, CC, BCC, Reply-To)
- Message Size (für SORT-Operationen)
- References Header (RFC 5322 Fallback)
- Content-Type & Attachment-Detection
- Server Metadata (auf MailAccount-Ebene)
- Folder Klassifizierung (auf EmailFolder-Ebene)
"""

from alembic import op
import sqlalchemy as sa


revision = 'ph12_metadata_enrichment'
down_revision = 'ph11d_sender_patterns'
branch_labels = None
depends_on = None


def upgrade():
    """Fügt neue Metadaten-Spalten zu raw_emails und related tables hinzu."""
    
    # ===== PHASE 12.1: MUST-HAVE COLUMNS (Message-ID, Threading, Boolean Flags) =====
    
    # Message-ID & Threading (mit if_not_exists für Idempotenz)
    op.execute("""
        ALTER TABLE raw_emails ADD COLUMN message_id VARCHAR(255) DEFAULT NULL;
    """)
    op.create_index('ix_raw_emails_message_id', 'raw_emails', ['message_id'], if_not_exists=True)
    
    op.execute("ALTER TABLE raw_emails ADD COLUMN encrypted_in_reply_to TEXT DEFAULT NULL;")
    
    op.execute("ALTER TABLE raw_emails ADD COLUMN parent_uid VARCHAR(255) DEFAULT NULL;")
    op.create_index('ix_raw_emails_parent_uid', 'raw_emails', ['parent_uid'], if_not_exists=True)
    
    op.execute("ALTER TABLE raw_emails ADD COLUMN thread_id VARCHAR(36) DEFAULT NULL;")
    op.create_index('ix_raw_emails_thread_id', 'raw_emails', ['thread_id'], if_not_exists=True)
    
    # Boolean Flags (replace imap_flags string, aber NICHT löschen für backward-compat!)
    op.execute("ALTER TABLE raw_emails ADD COLUMN imap_is_seen BOOLEAN DEFAULT 0;")
    op.create_index('ix_raw_emails_imap_is_seen', 'raw_emails', ['imap_is_seen'], if_not_exists=True)
    
    op.execute("ALTER TABLE raw_emails ADD COLUMN imap_is_answered BOOLEAN DEFAULT 0;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN imap_is_flagged BOOLEAN DEFAULT 0;")
    op.create_index('ix_raw_emails_imap_is_flagged', 'raw_emails', ['imap_is_flagged'], if_not_exists=True)
    
    op.execute("ALTER TABLE raw_emails ADD COLUMN imap_is_deleted BOOLEAN DEFAULT 0;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN imap_is_draft BOOLEAN DEFAULT 0;")
    
    # ===== PHASE 12.2: SHOULD-HAVE COLUMNS (Extended Envelope, Message Size, References) =====
    
    # Extended Envelope Fields
    op.execute("ALTER TABLE raw_emails ADD COLUMN encrypted_to TEXT DEFAULT NULL;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN encrypted_cc TEXT DEFAULT NULL;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN encrypted_bcc TEXT DEFAULT NULL;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN encrypted_reply_to TEXT DEFAULT NULL;")
    
    # Message Metadata
    op.execute("ALTER TABLE raw_emails ADD COLUMN message_size INTEGER DEFAULT NULL;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN encrypted_references TEXT DEFAULT NULL;")
    
    # ===== PHASE 12.3: NICE-TO-HAVE COLUMNS (Content Info, Audit) =====
    
    # Content Info
    op.execute("ALTER TABLE raw_emails ADD COLUMN content_type VARCHAR(100) DEFAULT NULL;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN charset VARCHAR(50) DEFAULT NULL;")
    op.execute("ALTER TABLE raw_emails ADD COLUMN has_attachments BOOLEAN DEFAULT 0;")
    
    # Audit
    op.execute("ALTER TABLE raw_emails ADD COLUMN last_flag_sync_at DATETIME DEFAULT NULL;")
    
    # ===== MailAccount Enhancements (Server Metadata) =====
    
    op.execute("ALTER TABLE mail_accounts ADD COLUMN detected_provider VARCHAR(50) DEFAULT NULL;")
    op.execute("ALTER TABLE mail_accounts ADD COLUMN server_name VARCHAR(255) DEFAULT NULL;")
    op.execute("ALTER TABLE mail_accounts ADD COLUMN server_version VARCHAR(100) DEFAULT NULL;")
    
    # ===== EmailFolder Enhancements (Folder Classification) =====
    
    op.execute("ALTER TABLE email_folders ADD COLUMN is_special_folder BOOLEAN DEFAULT 0;")
    op.execute("ALTER TABLE email_folders ADD COLUMN special_folder_type VARCHAR(50) DEFAULT NULL;")
    op.execute("ALTER TABLE email_folders ADD COLUMN display_name_localized VARCHAR(255) DEFAULT NULL;")


def downgrade():
    """Entfernt Phase 12 Spalten in reverse order."""
    
    # EmailFolder rollback
    op.drop_column('email_folders', 'display_name_localized')
    op.drop_column('email_folders', 'special_folder_type')
    op.drop_column('email_folders', 'is_special_folder')
    
    # MailAccount rollback
    op.drop_column('mail_accounts', 'server_version')
    op.drop_column('mail_accounts', 'server_name')
    op.drop_column('mail_accounts', 'detected_provider')
    
    # RawEmail rollback (PHASE 12.3)
    op.drop_column('raw_emails', 'last_flag_sync_at')
    op.drop_column('raw_emails', 'has_attachments')
    op.drop_column('raw_emails', 'charset')
    op.drop_column('raw_emails', 'content_type')
    
    # RawEmail rollback (PHASE 12.2)
    op.drop_column('raw_emails', 'encrypted_references')
    op.drop_column('raw_emails', 'message_size')
    op.drop_column('raw_emails', 'encrypted_reply_to')
    op.drop_column('raw_emails', 'encrypted_bcc')
    op.drop_column('raw_emails', 'encrypted_cc')
    op.drop_column('raw_emails', 'encrypted_to')
    
    # RawEmail rollback (PHASE 12.1) - drop indices before columns
    op.drop_index('ix_raw_emails_message_id', table_name='raw_emails')
    op.drop_index('ix_raw_emails_parent_uid', table_name='raw_emails')
    op.drop_index('ix_raw_emails_thread_id', table_name='raw_emails')
    op.drop_index('ix_raw_emails_imap_is_seen', table_name='raw_emails')
    op.drop_index('ix_raw_emails_imap_is_answered', table_name='raw_emails')
    op.drop_index('ix_raw_emails_imap_is_flagged', table_name='raw_emails')
    
    op.drop_column('raw_emails', 'imap_is_draft')
    op.drop_column('raw_emails', 'imap_is_deleted')
    op.drop_column('raw_emails', 'imap_is_flagged')
    op.drop_column('raw_emails', 'imap_is_answered')
    op.drop_column('raw_emails', 'imap_is_seen')
    op.drop_column('raw_emails', 'thread_id')
    op.drop_column('raw_emails', 'parent_uid')
    op.drop_column('raw_emails', 'encrypted_in_reply_to')
    op.drop_column('raw_emails', 'message_id')
