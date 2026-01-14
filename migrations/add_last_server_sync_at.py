#!/usr/bin/env python3
"""
Migration: Fügt last_server_sync_at zu mail_accounts hinzu

Wird benötigt für den Server-Sync-Service um zu tracken
wann der letzte vollständige Server-Scan durchgeführt wurde.
"""
import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def migrate(db_path: str = "emails.db"):
    """Führt die Migration durch"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check ob mail_accounts existiert
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='mail_accounts'
    """)
    if not cursor.fetchone():
        print("❌ Tabelle mail_accounts existiert nicht!")
        conn.close()
        return False
    
    # Check ob Spalte schon existiert
    cursor.execute("PRAGMA table_info(mail_accounts)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'last_server_sync_at' in columns:
        print("✅ last_server_sync_at existiert bereits in mail_accounts")
        conn.close()
        return True
    
    print("📦 Füge last_server_sync_at zu mail_accounts hinzu...")
    
    try:
        cursor.execute("""
            ALTER TABLE mail_accounts 
            ADD COLUMN last_server_sync_at DATETIME NULL
        """)
        conn.commit()
        
        print("✅ Migration erfolgreich!")
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration fehlgeschlagen: {e}")
        conn.close()
        return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
