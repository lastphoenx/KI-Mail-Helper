"""
Migration: Add missing ML training columns to processed_emails table
Run with: python -m src.18_migrate_ml_columns
"""

import sqlite3

DB_PATH = "emails.db"


def migrate():
    """Adds missing columns for ML training to processed_emails table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        columns_to_add = [
            ("base_provider", "TEXT"),
            ("base_model", "TEXT"),
            ("optimize_provider", "TEXT"),
            ("optimize_model", "TEXT"),
            ("user_override_dringlichkeit", "INTEGER"),
            ("user_override_wichtigkeit", "INTEGER"),
            ("user_override_kategorie", "TEXT"),
            ("user_override_spam_flag", "BOOLEAN"),
            ("user_override_tags", "TEXT"),
            ("correction_timestamp", "DATETIME"),
            ("user_correction_note", "TEXT"),
        ]

        existing_columns = set()
        cursor.execute("PRAGMA table_info(processed_emails)")
        for row in cursor.fetchall():
            existing_columns.add(row[1])

        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                sql = f"ALTER TABLE processed_emails ADD COLUMN {col_name} {col_type}"
                cursor.execute(sql)
                print(f"✅ Added column: {col_name} ({col_type})")
            else:
                print(f"ℹ️  Column already exists: {col_name}")

        conn.commit()
        print("✅ Migration completed successfully!")

    except sqlite3.OperationalError as e:
        print(f"❌ Migration error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"📊 Migrating database: {DB_PATH}")
    migrate()
