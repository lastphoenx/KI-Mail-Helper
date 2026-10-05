#!/usr/bin/env python3
"""BFS-Vornamen (opendata.swiss) in audit_firstnames laden."""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path
from typing import Iterable, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("import_firstnames")

# BFS: Vornamen Bevölkerung nach Jahrgang, Schweiz 2025 (opendata.swiss)
BFS_FIRSTNAME_ASSETS: Tuple[Tuple[str, str], ...] = (
    (
        "female",
        "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36752506/master",
    ),
    (
        "male",
        "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36752513/master",
    ),
)

# Fallback: Kanton Zug (kleiner) — nur mit --legacy-zg
RESOURCE_CSV_URLS: dict[str, Tuple[str, ...]] = {
    "214": (
        "https://data.zg.ch/store/1/resource/214",
        "https://data.zg.ch/store/1/resource/214/revisions/latest/download",
    ),
    "212": (
        "https://data.zg.ch/store/1/resource/212",
        "https://data.zg.ch/store/1/resource/212/revisions/latest/download",
    ),
}

_HTTP_HEADERS = {
    "User-Agent": "KI-Mail-Helper/1.0 (audit firstnames import)",
}


def fold_name_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", (name or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z\-']", "", s.replace(" ", ""))
    return s


def keys_from_vorname(raw: str) -> set[str]:
    out: set[str] = set()
    k = fold_name_key(raw)
    if len(k) >= 2:
        out.add(k)
    if "ue" in k:
        out.add(k.replace("ue", "u"))
    return out


def _http_get(url: str, *, accept: str = "text/csv,application/csv,*/*") -> bytes:
    headers = {**_HTTP_HEADERS, "Accept": accept}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_csv_from_url(url: str) -> str:
    payload = _http_get(url)
    text = payload.decode("utf-8-sig", errors="replace")
    head = text.lstrip()[:500].lower()
    if head.startswith("<") or "<html" in head:
        raise RuntimeError(f"HTML statt CSV: {url}")
    if "firstname" not in head and "vorname" not in head:
        raise RuntimeError(f"Spalte firstname/vorname fehlt: {url}")
    return text


def fetch_csv_text(candidates: Iterable[str]) -> Tuple[str, str]:
    last_err: Exception | None = None
    for url in candidates:
        try:
            text = fetch_csv_from_url(url)
            return text, url
        except Exception as e:
            last_err = e
            logger.debug("fetch failed %s: %s", url, e)
    msg = "Keine CSV-Quelle erreichbar"
    if last_err:
        msg += f" — letzter Fehler: {last_err}"
    raise RuntimeError(msg)


def keys_from_csv_text(text: str) -> set[str]:
    keys: set[str] = set()
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise RuntimeError("CSV ohne Kopfzeile")
    name_col = None
    for fn in reader.fieldnames:
        if fn and fn.strip().lower() in ("vorname", "firstname"):
            name_col = fn
            break
    if not name_col:
        raise RuntimeError(f"Spalte firstname/vorname fehlt (Spalten: {reader.fieldnames})")
    rows = 0
    for row in reader:
        rows += 1
        vn = (row.get(name_col) or "").strip()
        if vn:
            keys |= keys_from_vorname(vn)
    if rows == 0:
        raise RuntimeError("CSV ohne Datenzeilen")
    return keys


def collect_name_keys_bfs() -> Tuple[set[str], list[str]]:
    keys: set[str] = set()
    used: list[str] = []
    for label, url in BFS_FIRSTNAME_ASSETS:
        logger.info("Fetching BFS %s …", label)
        text = fetch_csv_from_url(url)
        part = keys_from_csv_text(text)
        keys |= part
        used.append(url)
        logger.info("  url=%s keys=%s total_keys=%s", url, len(part), len(keys))
    return keys, used


def collect_name_keys_zg(resources: Tuple[str, ...] = ("214", "212")) -> Tuple[set[str], list[str]]:
    keys: set[str] = set()
    used: list[str] = []
    for rid in resources:
        urls = RESOURCE_CSV_URLS.get(rid)
        if not urls:
            raise RuntimeError(f"Unbekannte Ressource {rid}")
        logger.info("Fetching ZG resource %s …", rid)
        text, url = fetch_csv_text(urls)
        part = keys_from_csv_text(text)
        keys |= part
        used.append(url)
        logger.info("  url=%s keys=%s total_keys=%s", url, len(part), len(keys))
    return keys, used


def write_notice(path: Path, urls: list[str], *, key_count: int, source_label: str) -> None:
    lines = [
        "Vornamen fuer Ordner-Audit (Personenerkennung E9/N1).",
        "Skript: scripts/import_firstnames.py",
        "",
        f"Quelle: {source_label}",
        "Lizenz: opendata.swiss — Open use, Quelle angeben (BFS / Kantonsdaten).",
        f"Stand Import: {key_count} normalisierte name_key-Eintraege in audit_firstnames.",
        "",
        "CSV-URLs:",
    ]
    lines.extend(f"- {u}" for u in urls)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_firstnames_in_db() -> int:
    from src.helpers.database import get_db_session
    import importlib

    models = importlib.import_module(".02_models", "src")
    with get_db_session() as session:
        if not hasattr(models, "AuditFirstname"):
            return 0
        return int(session.query(models.AuditFirstname).count())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur zählen, nicht in DB schreiben",
    )
    parser.add_argument(
        "--test-api",
        action="store_true",
        help="CSV-Download testen (BFS-Assets)",
    )
    parser.add_argument(
        "--count-db",
        action="store_true",
        help="Anzahl Zeilen in audit_firstnames ausgeben (kein Import)",
    )
    parser.add_argument(
        "--legacy-zg",
        action="store_true",
        help="Kanton Zug statt BFS Schweiz (Altlast)",
    )
    parser.add_argument(
        "--csv-file",
        action="append",
        help="Lokale CSV statt Download (mehrfach möglich)",
    )
    args = parser.parse_args()

    if args.count_db:
        n = count_firstnames_in_db()
        print(f"audit_firstnames: {n} rows")
        return 0

    source_db = "bfs_ch_firstnames"
    source_label = (
        "BFS — Weibliche/männliche Vornamen der Bevölkerung nach Jahrgang, "
        "Schweiz 2025 (dam-api.bfs.admin.ch, opendata.swiss)"
    )

    if args.test_api:
        if args.legacy_zg:
            for rid in ("214", "212"):
                text, url = fetch_csv_text(RESOURCE_CSV_URLS[rid])
                keys = keys_from_csv_text(text)
                sample = next(iter(keys), "")
                print(f"resource {rid}: url={url} keys={len(keys)} sample={sample!r}")
        else:
            for label, url in BFS_FIRSTNAME_ASSETS:
                text = fetch_csv_from_url(url)
                keys = keys_from_csv_text(text)
                sample = next(iter(keys), "")
                print(f"bfs {label}: url={url} keys={len(keys)} sample={sample!r}")
        return 0

    if args.csv_file:
        keys: set[str] = set()
        used = []
        for path in args.csv_file:
            text = Path(path).read_text(encoding="utf-8-sig")
            keys |= keys_from_csv_text(text)
            used.append(str(path))
        source_db = "csv_file"
        source_label = "Lokale CSV-Datei(en)"
    elif args.legacy_zg:
        keys, used = collect_name_keys_zg()
        source_db = "bfs_zg_opendata"
        source_label = "Kanton Zug data.zg.ch (214/212), nicht vollstaendige BFS-CH-Liste"
    else:
        keys, used = collect_name_keys_bfs()

    logger.info("Unique name keys: %s", len(keys))
    notice = ROOT / "NOTICE-firstnames.txt"
    write_notice(notice, used, key_count=len(keys), source_label=source_label)

    if args.dry_run:
        print(f"dry-run: {len(keys)} unique name_key (keine DB-Aenderung)")
        return 0

    from src.helpers.database import get_db_session, _get_engine
    import importlib

    models = importlib.import_module(".02_models", "src")
    from src.services.audit_firstnames import invalidate_firstname_cache
    from sqlalchemy import inspect

    engine = _get_engine()
    url = str(engine.url)
    if url.startswith("sqlite"):
        logger.warning(
            "DATABASE_URL nicht gesetzt — nutze SQLite (%s). "
            "Produktion: .env laden und alembic upgrade head.",
            url,
        )

    with get_db_session() as session:
        tables = inspect(session.bind).get_table_names()
        if "audit_firstnames" not in tables:
            logger.error(
                "Tabelle audit_firstnames fehlt (DB: %s). "
                "Zuerst: alembic upgrade head",
                url.split("@")[-1] if "@" in url else url,
            )
            return 1
        session.query(models.AuditFirstname).delete()
        batch = 0
        for k in sorted(keys):
            session.add(
                models.AuditFirstname(name_key=k, source=source_db)
            )
            batch += 1
            if batch % 2000 == 0:
                session.flush()
        session.commit()
    invalidate_firstname_cache()
    logger.info("Inserted %s rows into audit_firstnames", len(keys))
    print(f"audit_firstnames: {len(keys)} rows inserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
