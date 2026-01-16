"""Migration: Fügt KI-Präferenzspalten zu users hinzu."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")


def ensure_ai_preferences_columns(db_path: str | None = None) -> None:
    """Stellt sicher, dass preferred_ai_provider/-model existieren."""
    path = db_path or DEFAULT_DB
    if not os.path.exists(path):
        return

    with closing(sqlite3.connect(path)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}

        if "preferred_ai_provider" not in columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN preferred_ai_provider TEXT DEFAULT 'ollama'"
            )
        if "preferred_ai_model" not in columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN preferred_ai_model TEXT DEFAULT 'llama3.2'"
            )
        conn.commit()


if __name__ == "__main__":
    ensure_ai_preferences_columns()
    print("✅ AI Preference Migration abgeschlossen")
