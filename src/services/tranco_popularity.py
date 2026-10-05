"""Tranco Top-N Popularität — Fehlalarm-Dämpfer für Marken-Check (nicht Echtheits-Beweis).

Liste nur zur Laufzeit (SQLite unter data/tranco/), nicht im Git-Repo.
Lizenz: gemischte Quellen — siehe docs/audit/tranco-popularity.md
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from src.services.brand_domain_policy import registrable_domain_from_host
from src.services.shared_mail_infrastructure import shared_infrastructure_registrable

logger = logging.getLogger(__name__)

_DISPLAY_STOP = {
    "team", "service", "support", "newsletter", "info", "noreply", "official",
    "customer", "the", "der", "die", "das", "und", "fur", "für", "von", "via",
    "ag", "gmbh", "inc", "ltd", "llc", "sa", "srl", "mail", "email",
    "bank", "post", "shop", "store",
}

_store_lock = threading.Lock()
_store_instance: Optional["TrancoStore"] = None


def tranco_data_dir() -> Path:
    raw = os.getenv("TRANCO_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / "data" / "tranco"


def tranco_db_path() -> Path:
    override = os.getenv("TRANCO_DB_PATH", "").strip()
    if override:
        return Path(override)
    return tranco_data_dir() / "tranco.db"


def tranco_top_n_threshold() -> int:
    try:
        return int(os.getenv("TRANCO_TOP_N", "100000"))
    except (TypeError, ValueError):
        return 100_000


def significant_name_tokens(display_name: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]{5,}", (display_name or "").lower())
    return [t for t in raw if t not in _DISPLAY_STOP]


def display_name_aligns_with_domain_label(display_name: str, registrable: str) -> bool:
    """Name muss zum Domain-Label passen (min. 5 Zeichen Label, Wortgleichheit)."""
    reg = (registrable or "").lower().strip(".")
    if not reg or "." not in reg:
        return False
    label = reg.split(".", 1)[0].replace("-", "")
    if len(label) < 5:
        return False
    compact = re.sub(r"[^a-z0-9]", "", (display_name or "").lower())
    if label in compact:
        return True
    words = set(significant_name_tokens(display_name))
    if label in words:
        return True
    if "tricks" in label and "tricks" in words and "css" in words:
        return True
    return False


@dataclass(frozen=True)
class TrancoStatus:
    available: bool
    list_id: str
    updated_at: str
    domain_count: int
    top_n: int
    message: str
    source_note: str


class TrancoStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._mtime: float = 0.0

    def _db_mtime(self) -> float:
        try:
            return self.db_path.stat().st_mtime
        except OSError:
            return 0.0

    def _connect(self) -> sqlite3.Connection:
        current_mtime = self._db_mtime()
        if self._conn is not None and current_mtime != self._mtime:
            self.close()
        if self._conn is None:
            self._mtime = current_mtime
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._mtime = 0.0

    def meta(self, key: str, default: str = "") -> str:
        if not self.db_path.is_file():
            return default
        try:
            row = self._connect().execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else default
        except sqlite3.Error:
            return default

    def rank(self, registrable: str) -> Optional[int]:
        if not registrable or not self.db_path.is_file():
            return None
        try:
            row = self._connect().execute(
                "SELECT rank FROM domains WHERE domain = ?", (registrable.lower(),)
            ).fetchone()
            return int(row[0]) if row else None
        except sqlite3.Error as exc:
            logger.debug("tranco rank lookup: %s", exc)
            return None

    def is_in_top_n(self, registrable: str, top_n: int) -> bool:
        r = self.rank(registrable)
        return r is not None and r <= top_n

    def top_domains(self, limit: int) -> Set[str]:
        if not self.db_path.is_file():
            return set()
        try:
            rows = self._connect().execute(
                "SELECT domain FROM domains WHERE rank <= ? ORDER BY rank",
                (limit,),
            ).fetchall()
            return {r[0] for r in rows}
        except sqlite3.Error:
            return set()


def get_tranco_store(*, force_reload: bool = False) -> Optional[TrancoStore]:
    global _store_instance
    path = tranco_db_path()
    if not path.is_file():
        return None
    with _store_lock:
        if force_reload and _store_instance:
            _store_instance.close()
            _store_instance = None
        if _store_instance is not None:
            if _store_instance.db_path != path:
                _store_instance.close()
                _store_instance = None
            elif path.is_file():
                try:
                    if _store_instance._db_mtime() != _store_instance._mtime:
                        _store_instance.close()
                        _store_instance = None
                except OSError:
                    _store_instance.close()
                    _store_instance = None
        if _store_instance is None:
            _store_instance = TrancoStore(path)
        return _store_instance


def is_well_known_domain(host_or_email: str, *, top_n: Optional[int] = None) -> bool:
    """Domain in Tranco Top-N und nicht geteilte Infrastruktur."""
    reg = registrable_domain_from_host(host_or_email)
    if not reg or shared_infrastructure_registrable(reg):
        return False
    store = get_tranco_store()
    if store is None:
        return False
    n = top_n if top_n is not None else tranco_top_n_threshold()
    return store.is_in_top_n(reg, n)


def tranco_exempts_brand_mismatch(sender_name: str, sender_email: str) -> bool:
    """
    Unterdrückt Marken-Fehlalarm nur wenn:
    - Tranco-Liste geladen
    - Domain Top-N, nicht Shared Infra
    - Anzeigename passt zum Domain-Label
    """
    reg = registrable_domain_from_host(_host(sender_email))
    if not reg or shared_infrastructure_registrable(reg):
        return False
    store = get_tranco_store()
    if store is None:
        return False
    if not store.is_in_top_n(reg, tranco_top_n_threshold()):
        return False
    return display_name_aligns_with_domain_label(sender_name, reg)


def _host(sender_email: str) -> str:
    if not sender_email or "@" not in sender_email:
        return ""
    return sender_email.split("@")[-1].lower().strip(">").strip()


def get_tranco_status() -> TrancoStatus:
    store = get_tranco_store()
    top_n = tranco_top_n_threshold()
    note = (
        "Tranco (Le Pochat et al., NDSS 2019). Enthält u. a. CC-BY-NC — "
        "bei kommerzieller Nutzung Bedingungen prüfen. Nicht im Git-Repo."
    )
    if store is None:
        fixed = os.getenv("TRANCO_LIST_ID", "").strip()
        return TrancoStatus(
            available=False,
            list_id=fixed or "auto",
            updated_at="",
            domain_count=0,
            top_n=top_n,
            message="Tranco-Liste fehlt: Marken-Fehlalarm-Dämpfer eingeschränkt.",
            source_note=note,
        )
    try:
        count = store._connect().execute("SELECT COUNT(*) FROM domains").fetchone()[0]
    except sqlite3.Error:
        count = 0
    updated = store.meta("updated_at", store.meta("built_at", ""))
    list_id = store.meta("list_id", os.getenv("TRANCO_LIST_ID", "").strip() or "auto")
    return TrancoStatus(
        available=True,
        list_id=list_id,
        updated_at=updated,
        domain_count=int(count),
        top_n=top_n,
        message=f"Tranco-Liste {list_id}, {count} Domains (Top {top_n})",
        source_note=note,
    )


def build_sqlite_from_rank_pairs(
    pairs: list[tuple[int, str]],
    dest: Path,
    *,
    list_id: str = "TEST",
    max_rank: int = 100_000,
) -> None:
    """Tests und Update-Pipeline."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    best_rank: dict[str, int] = {}
    for r, d in pairs:
        if r > max_rank:
            continue
        dom = (d or "").strip().lower()
        if not dom:
            continue
        prev = best_rank.get(dom)
        if prev is None or r < prev:
            best_rank[dom] = r
    rows = sorted((rank, dom) for dom, rank in best_rank.items())
    conn = sqlite3.connect(str(tmp))
    conn.execute("CREATE TABLE domains (domain TEXT PRIMARY KEY, rank INTEGER NOT NULL)")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO domains (domain, rank) VALUES (?, ?)",
        [(dom, rank) for rank, dom in rows],
    )
    conn.execute("INSERT INTO meta VALUES ('list_id', ?)", (list_id,))
    conn.execute(
        "INSERT INTO meta VALUES ('built_at', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()
    tmp.replace(dest)
