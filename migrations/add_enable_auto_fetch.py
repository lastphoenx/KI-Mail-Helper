#!/usr/bin/env python3
"""
Migration: Add enable_auto_fetch to users table

Diese Spalte ermöglicht:
- User kann automatisches Mail-Fetching im Hintergrund aktivieren
- Frontend pollt alle 10 Minuten /api/auto-fetch-mails
- Nutzt ServiceToken-Pattern für Sicherheit

Usage:
    python migrations/add_enable_auto_fetch.py
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def migrate(db_path: str = "emails.db"):
    """Add enable_auto_fetch column to users table"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'enable_auto_fetch' in columns:
        print("✅ Spalte enable_auto_fetch existiert bereits")
        conn.close()
        return
    
    print("📦 Füge Spalte enable_auto_fetch zu users hinzu...")
    
    try:
        # Add column (SQLite doesn't support adding NOT NULL with default in one statement)
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN enable_auto_fetch INTEGER DEFAULT 0
        """)
        
        conn.commit()
        print("✅ Spalte enable_auto_fetch erfolgreich hinzugefügt")
        print("   Default: False (User muss explizit aktivieren)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Fehler bei Migration: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add enable_auto_fetch column to users")
    parser.add_argument(
        "--db",
        default="emails.db",
        help="Path to SQLite database (default: emails.db)"
    )
    
    args = parser.parse_args()
    migrate(args.db)
