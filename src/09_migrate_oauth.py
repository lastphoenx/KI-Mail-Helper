"""
Migration: Fügt OAuth-Spalten zu mail_accounts hinzu
"""
import sqlite3
import os


def migrate():
    db_path = "emails.db"
    if not os.path.exists(db_path):
        print("❌ Datenbank nicht gefunden")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(mail_accounts)")
        columns = [row[1] for row in cursor.fetchall()]

        migrations = [
            (
                "oauth_provider",
                "ALTER TABLE mail_accounts ADD COLUMN oauth_provider VARCHAR(20)",
            ),
            (
                "encrypted_oauth_token",
                "ALTER TABLE mail_accounts ADD COLUMN encrypted_oauth_token TEXT",
            ),
            (
                "encrypted_oauth_refresh_token",
                "ALTER TABLE mail_accounts ADD COLUMN encrypted_oauth_refresh_token TEXT",
            ),
            (
                "oauth_expires_at",
                "ALTER TABLE mail_accounts ADD COLUMN oauth_expires_at DATETIME",
            ),
        ]

        for col_name, sql in migrations:
            if col_name not in columns:
                try:
                    cursor.execute(sql)
                    print(f"✅ Spalte '{col_name}' hinzugefügt")
                except sqlite3.OperationalError as e:
                    print(f"⚠️  Spalte '{col_name}': {e}")
            else:
                print(f"✓ Spalte '{col_name}' existiert bereits")

        conn.commit()
        print("\n✅ Migrationen abgeschlossen!")
        return True

    except sqlite3.Error as e:
        print(f"❌ Datenbankfehler: {type(e).__name__}")
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
