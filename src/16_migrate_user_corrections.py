"""Migration: Fügt User-Correction-Felder zu processed_emails hinzu."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")


def ensure_user_correction_columns(db_path: str | None = None) -> None:
    """Stellt sicher, dass user_override_* Spalten in processed_emails existieren."""
    path = db_path or DEFAULT_DB
    if not os.path.exists(path):
        return

    with closing(sqlite3.connect(path)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(processed_emails)")
        columns = {row[1] for row in cursor.fetchall()}

        if "user_override_dringlichkeit" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN user_override_dringlichkeit INTEGER"
            )
        if "user_override_wichtigkeit" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN user_override_wichtigkeit INTEGER"
            )
        if "user_override_kategorie" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN user_override_kategorie TEXT"
            )
        if "user_override_spam_flag" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN user_override_spam_flag BOOLEAN"
            )
        if "user_override_tags" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN user_override_tags TEXT"
            )
        if "user_correction_note" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN user_correction_note TEXT"
            )
        if "correction_timestamp" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN correction_timestamp DATETIME"
            )
        conn.commit()


if __name__ == "__main__":
    ensure_user_correction_columns()
    print("✅ User Correction Migration abgeschlossen")
