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
    
    # Message-ID & Threading
    op.add_column('raw_emails', sa.Column('message_id', sa.String(255), nullable=True, index=True))
    op.add_column('raw_emails', sa.Column('encrypted_in_reply_to', sa.Text, nullable=True))
    op.add_column('raw_emails', sa.Column('parent_uid', sa.String(255), nullable=True, index=True))
    op.add_column('raw_emails', sa.Column('thread_id', sa.String(36), nullable=True, index=True))
    
    # Boolean Flags (replace imap_flags string, aber NICHT löschen für backward-compat!)
    # Prefix 'imap_' used to distinguish from 'deleted_at' property
    op.add_column('raw_emails', sa.Column('imap_is_seen', sa.Boolean, default=False, nullable=True, index=True))
    op.add_column('raw_emails', sa.Column('imap_is_answered', sa.Boolean, default=False, nullable=True, index=True))
    op.add_column('raw_emails', sa.Column('imap_is_flagged', sa.Boolean, default=False, nullable=True, index=True))
    op.add_column('raw_emails', sa.Column('imap_is_deleted', sa.Boolean, default=False, nullable=True))
    op.add_column('raw_emails', sa.Column('imap_is_draft', sa.Boolean, default=False, nullable=True))
    
    # ===== PHASE 12.2: SHOULD-HAVE COLUMNS (Extended Envelope, Message Size, References) =====
    
    # Extended Envelope Fields
    op.add_column('raw_emails', sa.Column('encrypted_to', sa.Text, nullable=True))
    op.add_column('raw_emails', sa.Column('encrypted_cc', sa.Text, nullable=True))
    op.add_column('raw_emails', sa.Column('encrypted_bcc', sa.Text, nullable=True))
    op.add_column('raw_emails', sa.Column('encrypted_reply_to', sa.Text, nullable=True))
    
    # Message Metadata
    op.add_column('raw_emails', sa.Column('message_size', sa.Integer, nullable=True))
    op.add_column('raw_emails', sa.Column('encrypted_references', sa.Text, nullable=True))
    
    # ===== PHASE 12.3: NICE-TO-HAVE COLUMNS (Content Info, Audit) =====
    
    # Content Info
    op.add_column('raw_emails', sa.Column('content_type', sa.String(100), nullable=True))
    op.add_column('raw_emails', sa.Column('charset', sa.String(50), nullable=True))
    op.add_column('raw_emails', sa.Column('has_attachments', sa.Boolean, default=False, nullable=True))
    
    # Audit
    op.add_column('raw_emails', sa.Column('last_flag_sync_at', sa.DateTime, nullable=True))
    
    # ===== MailAccount Enhancements (Server Metadata) =====
    
    op.add_column('mail_accounts', sa.Column('detected_provider', sa.String(50), nullable=True))
    op.add_column('mail_accounts', sa.Column('server_name', sa.String(255), nullable=True))
    op.add_column('mail_accounts', sa.Column('server_version', sa.String(100), nullable=True))
    
    # ===== EmailFolder Enhancements (Folder Classification) =====
    
    op.add_column('email_folders', sa.Column('is_special_folder', sa.Boolean, default=False, nullable=True))
    op.add_column('email_folders', sa.Column('special_folder_type', sa.String(50), nullable=True))
    op.add_column('email_folders', sa.Column('display_name_localized', sa.String(255), nullable=True))


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
    
    # RawEmail rollback (PHASE 12.1)
    op.drop_column('raw_emails', 'imap_is_draft')
    op.drop_column('raw_emails', 'imap_is_deleted')
    op.drop_column('raw_emails', 'imap_is_flagged')
    op.drop_column('raw_emails', 'imap_is_answered')
    op.drop_column('raw_emails', 'imap_is_seen')
    op.drop_column('raw_emails', 'thread_id')
    op.drop_column('raw_emails', 'parent_uid')
    op.drop_column('raw_emails', 'encrypted_in_reply_to')
    op.drop_column('raw_emails', 'message_id')
