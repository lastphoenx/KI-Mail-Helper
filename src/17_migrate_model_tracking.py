"""Migration: Fügt Modell-Tracking-Felder zu processed_emails hinzu."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")


def ensure_model_tracking_columns(db_path: str | None = None) -> None:
    """Stellt sicher, dass base_model, optimize_model, provider-Spalten existieren."""
    path = db_path or DEFAULT_DB
    if not os.path.exists(path):
        return

    with closing(sqlite3.connect(path)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(processed_emails)")
        columns = {row[1] for row in cursor.fetchall()}

        if "base_model" not in columns:
            cursor.execute("ALTER TABLE processed_emails ADD COLUMN base_model TEXT")
        if "base_provider" not in columns:
            cursor.execute("ALTER TABLE processed_emails ADD COLUMN base_provider TEXT")
        if "optimize_model" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN optimize_model TEXT"
            )
        if "optimize_provider" not in columns:
            cursor.execute(
                "ALTER TABLE processed_emails ADD COLUMN optimize_provider TEXT"
            )
        conn.commit()


if __name__ == "__main__":
    ensure_model_tracking_columns()
    print("✅ Model Tracking Migration abgeschlossen")
