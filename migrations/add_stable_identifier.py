#!/usr/bin/env python3
"""
Migration: Add stable_identifier and content_hash to raw_emails

Diese Spalten ermöglichen:
- Effizientes Matching zwischen raw_emails und mail_server_state
- Move-Detection auch für Mails ohne message_id
- Schnelle Lookups via Index

Usage:
    python migrations/add_stable_identifier.py
"""

import sqlite3
import hashlib
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def compute_content_hash(date_str: str, from_addr: str, subject: str) -> str:
    """Berechnet stabilen Hash aus Date+From+Subject"""
    content = f"{date_str or ''}|{from_addr or ''}|{subject or ''}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]


def get_stable_id(message_id: str, content_hash: str) -> str:
    """Gibt den stabilen Identifier zurück"""
    return message_id if message_id else f"hash:{content_hash}"


def migrate(db_path: str = "emails.db"):
    """Add stable_identifier and content_hash columns to raw_emails"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(raw_emails)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'stable_identifier' in columns and 'content_hash' in columns:
        print("✅ Spalten stable_identifier und content_hash existieren bereits")
        conn.close()
        return
    
    print("📦 Füge Spalten zu raw_emails hinzu...")
    
    # Add columns
    if 'stable_identifier' not in columns:
        cursor.execute("""
            ALTER TABLE raw_emails ADD COLUMN stable_identifier TEXT
        """)
        print("  ✓ stable_identifier hinzugefügt")
    
    if 'content_hash' not in columns:
        cursor.execute("""
            ALTER TABLE raw_emails ADD COLUMN content_hash TEXT
        """)
        print("  ✓ content_hash hinzugefügt")
    
    conn.commit()
    
    # Create indexes
    print("📦 Erstelle Indexes...")
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_raw_emails_stable_identifier 
        ON raw_emails(stable_identifier)
    """)
    print("  ✓ idx_raw_emails_stable_identifier")
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_raw_emails_content_hash 
        ON raw_emails(content_hash)
    """)
    print("  ✓ idx_raw_emails_content_hash")
    
    conn.commit()
    
    # Backfill existing rows
    print("📦 Berechne stable_identifier für existierende Mails...")
    
    # Für Mails MIT message_id: stable_identifier = message_id
    cursor.execute("""
        UPDATE raw_emails 
        SET stable_identifier = message_id
        WHERE message_id IS NOT NULL 
          AND stable_identifier IS NULL
    """)
    updated_with_msgid = cursor.rowcount
    print(f"  ✓ {updated_with_msgid} Mails mit message_id aktualisiert")
    
    # Für Mails OHNE message_id: Müssen manuell berechnet werden
    # (Erfordert Entschlüsselung - hier nur Warnung)
    cursor.execute("""
        SELECT COUNT(*) FROM raw_emails 
        WHERE message_id IS NULL 
          AND stable_identifier IS NULL
    """)
    mails_without_msgid = cursor.fetchone()[0]
    
    if mails_without_msgid > 0:
        print(f"  ⚠️  {mails_without_msgid} Mails ohne message_id - content_hash muss manuell berechnet werden")
        print("     (Erfordert Entschlüsselung der encrypted_* Felder)")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migration abgeschlossen!")
    print("""
Nächste Schritte für Mails ohne message_id:
    
    from src.services.encryption import decrypt_field
    
    for raw in session.query(RawEmail).filter(
        RawEmail.message_id.is_(None),
        RawEmail.stable_identifier.is_(None)
    ).all():
        from_addr = decrypt_field(raw.encrypted_sender, user_key)
        subject = decrypt_field(raw.encrypted_subject, user_key)
        date_str = raw.received_at.isoformat() if raw.received_at else ''
        
        content_hash = compute_content_hash(date_str, from_addr, subject)
        raw.stable_identifier = f"hash:{content_hash}"
        raw.content_hash = content_hash
    
    session.commit()
""")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add stable_identifier to raw_emails")
    parser.add_argument("--db", default="emails.db", help="Path to database")
    args = parser.parse_args()
    
    migrate(args.db)
