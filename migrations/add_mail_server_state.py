#!/usr/bin/env python3
"""
Migration: Add mail_server_state table for full server sync

Diese Tabelle ermöglicht:
- Move-Detection (gleiche message_id, anderer folder)
- Delete-Detection (war in Tabelle, nicht mehr auf Server)
- Echtes Delta (was wurde gefetcht vs. was existiert)

Usage:
    python migrations/add_mail_server_state.py
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def migrate(db_path: str = "emails.db"):
    """Create mail_server_state table"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='mail_server_state'
    """)
    
    if cursor.fetchone():
        print("✅ Tabelle mail_server_state existiert bereits")
        conn.close()
        return
    
    print("📦 Erstelle Tabelle mail_server_state...")
    
    # Create table
    cursor.execute("""
        CREATE TABLE mail_server_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mail_account_id INTEGER NOT NULL,
            
            -- Server-Identifikation (ändert sich bei MOVE)
            folder TEXT NOT NULL,
            uid INTEGER NOT NULL,
            uidvalidity INTEGER NOT NULL,
            
            -- Stabiler Identifier (bleibt bei MOVE gleich)
            message_id TEXT,
            content_hash TEXT NOT NULL,
            
            -- Server-Metadaten (aus ENVELOPE)
            envelope_from TEXT,
            envelope_subject TEXT,
            envelope_date TIMESTAMP,
            flags TEXT,
            
            -- Referenz zu gefetchter Mail
            raw_email_id INTEGER REFERENCES raw_emails(id),
            
            -- Status
            is_deleted BOOLEAN DEFAULT 0,
            
            -- Timestamps
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (mail_account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE,
            UNIQUE(user_id, mail_account_id, folder, uid, uidvalidity)
        )
    """)
    
    # Create indexes
    print("📦 Erstelle Indexes...")
    
    cursor.execute("""
        CREATE INDEX idx_server_state_hash 
        ON mail_server_state(user_id, mail_account_id, content_hash)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_server_state_msgid 
        ON mail_server_state(user_id, mail_account_id, message_id)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_server_state_not_fetched 
        ON mail_server_state(user_id, mail_account_id, raw_email_id)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_server_state_folder 
        ON mail_server_state(user_id, mail_account_id, folder)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Migration erfolgreich!")
    print("")
    print("📊 Neue Tabelle: mail_server_state")
    print("   - Speichert Server-Zustand für ALLE Mails")
    print("   - Ermöglicht Move/Delete Detection")
    print("   - raw_email_id = NULL bedeutet 'noch nicht gefetcht'")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add mail_server_state table")
    parser.add_argument("--db", default="emails.db", help="Database path")
    args = parser.parse_args()
    
    migrate(args.db)
