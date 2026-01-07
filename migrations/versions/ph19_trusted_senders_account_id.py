"""Add account_id to trusted_senders (account-based whitelist)

Revision ID: ph19_trusted_senders_account_id
Revises: ph18_trusted_senders
Create Date: 2026-01-07

Phase X Update: Support both user_id (global) and account_id (per-account)

Neue Spalte: account_id (Foreign Key zu mail_accounts)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ph19_trusted_senders_account_id'
down_revision = 'ph18_trusted_senders'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add account_id support to trusted_senders table"""
    
    # SQLite migration via raw SQL (most reliable)
    op.execute("""
    CREATE TABLE trusted_senders_new (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        account_id INTEGER,
        sender_pattern VARCHAR(255) NOT NULL,
        pattern_type VARCHAR(20) NOT NULL,
        label VARCHAR(100),
        use_urgency_booster BOOLEAN DEFAULT 1 NOT NULL,
        added_at DATETIME NOT NULL,
        last_seen_at DATETIME,
        email_count INTEGER DEFAULT 0 NOT NULL,
        UNIQUE (user_id, sender_pattern),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE
    )
    """)
    
    op.execute("""
        INSERT INTO trusted_senders_new 
        (id, user_id, account_id, sender_pattern, pattern_type, label, use_urgency_booster, added_at, last_seen_at, email_count)
        SELECT id, user_id, NULL, sender_pattern, pattern_type, label, use_urgency_booster, added_at, last_seen_at, email_count
        FROM trusted_senders
    """)
    
    op.execute("DROP TABLE trusted_senders")
    op.execute("ALTER TABLE trusted_senders_new RENAME TO trusted_senders")
    
    # Recreate indexes
    op.execute("""
        CREATE INDEX ix_trusted_senders_user_pattern ON trusted_senders (user_id, sender_pattern)
    """)
    op.execute("""
        CREATE INDEX ix_trusted_senders_account_pattern ON trusted_senders (account_id, sender_pattern)
    """)
    
    print("✅ Migration ph19: account_id added to trusted_senders")
    print("✅ Both user_id and account_id now supported")


def downgrade() -> None:
    """Rollback changes"""
    op.execute("""
    CREATE TABLE trusted_senders_new (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        sender_pattern VARCHAR(255) NOT NULL,
        pattern_type VARCHAR(20) NOT NULL,
        label VARCHAR(100),
        use_urgency_booster BOOLEAN DEFAULT 1 NOT NULL,
        added_at DATETIME NOT NULL,
        last_seen_at DATETIME,
        email_count INTEGER DEFAULT 0 NOT NULL,
        UNIQUE (user_id, sender_pattern),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    
    op.execute("""
        INSERT INTO trusted_senders_new 
        (id, user_id, sender_pattern, pattern_type, label, use_urgency_booster, added_at, last_seen_at, email_count)
        SELECT id, user_id, sender_pattern, pattern_type, label, use_urgency_booster, added_at, last_seen_at, email_count
        FROM trusted_senders
    """)
    
    op.execute("DROP TABLE trusted_senders")
    op.execute("ALTER TABLE trusted_senders_new RENAME TO trusted_senders")
    
    op.execute("""
        CREATE INDEX ix_trusted_senders_user_pattern ON trusted_senders (user_id, sender_pattern)
    """)
    
    print("⬇️ Rollback ph19: account_id removed")
