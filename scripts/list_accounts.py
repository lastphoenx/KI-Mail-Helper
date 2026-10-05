#!/usr/bin/env python3
"""
Liste alle Mail-Accounts mit IDs über alle User.

Usage:
    python scripts/list_accounts.py
    python scripts/list_accounts.py --db /path/to/emails.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False
    print("⚠️  Hinweis: 'tabulate' nicht installiert. Ausgabe ist einfacher formatiert.")
    print("   Installation: pip install tabulate\n")


def list_accounts(db_path: str = "emails.db"):
    """Liste alle Mail-Accounts mit User-Zuordnung."""
    
    if not Path(db_path).exists():
        print(f"❌ Fehler: Datenbank '{db_path}' nicht gefunden!")
        sys.exit(1)
    
    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT 
                ma.id AS account_id,
                ma.name AS account_name,
                u.username AS user_login,
                CASE WHEN ma.enabled = 1 THEN 'Ja' ELSE 'Nein' END AS active,
                ma.auth_type AS auth_type
            FROM mail_accounts ma
            JOIN users u ON ma.user_id = u.id
            ORDER BY u.username, ma.name
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("ℹ️  Keine Mail-Accounts gefunden.")
            return
        
        headers = ["ID", "Account-Name", "User", "Aktiv", "Auth"]
        
        if HAS_TABULATE:
            print(tabulate(rows, headers=headers, tablefmt="grid"))
        else:
            # Fallback: Simple text output
            print(f"\n{'ID':<5} | {'Account-Name':<30} | {'User':<20} | {'Aktiv':<6} | {'Auth':<10}")
            print("-" * 85)
            for row in rows:
                print(f"{row[0]:<5} | {row[1]:<30} | {row[2]:<20} | {row[3]:<6} | {row[4]:<10}")
        
        print(f"\n📊 Gesamt: {len(rows)} Account(s)")
        
    except sqlite3.Error as e:
        print(f"❌ Datenbankfehler: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Liste alle Mail-Accounts mit IDs (über alle User)"
    )
    parser.add_argument(
        "--db",
        default="emails.db",
        help="Pfad zur SQLite-Datenbank (default: emails.db)"
    )
    
    args = parser.parse_args()
    list_accounts(args.db)
