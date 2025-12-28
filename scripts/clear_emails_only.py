#!/usr/bin/env python3
"""Clear only email tables (raw_emails, processed_emails) without deleting users/accounts."""
import sqlite3
import sys

def clear_emails_only(db_path="emails.db"):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA foreign_keys = ON")
        
        cursor.execute("DELETE FROM processed_emails")
        cursor.execute("DELETE FROM raw_emails")
        
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM raw_emails")
        raw_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM processed_emails")
        proc_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM mail_accounts")
        account_count = cursor.fetchone()[0]
        
        print(f"✅ Email-Tabellen geleert:")
        print(f"   raw_emails: {raw_count}")
        print(f"   processed_emails: {proc_count}")
        print(f"✓ Benutzer erhalten: {user_count}")
        print(f"✓ Mail-Accounts erhalten: {account_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = clear_emails_only()
    sys.exit(0 if success else 1)
