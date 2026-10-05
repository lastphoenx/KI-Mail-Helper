"""TrancoStore lädt SQLite neu, wenn die Datei ersetzt wurde."""

import sqlite3

from src.services.tranco_popularity import (
    TrancoStore,
    build_sqlite_from_rank_pairs,
    get_tranco_store,
)


def test_tranco_store_reopens_after_file_replace(tmp_path, monkeypatch):
    db = tmp_path / "tranco.db"
    build_sqlite_from_rank_pairs([(1, "alpha.example")], db, list_id="A")
    monkeypatch.setenv("TRANCO_DB_PATH", str(db))
    get_tranco_store(force_reload=True)
    assert get_tranco_store().rank("alpha.example") == 1

    build_sqlite_from_rank_pairs([(5, "alpha.example")], db, list_id="B")
    assert get_tranco_store().rank("alpha.example") == 5
