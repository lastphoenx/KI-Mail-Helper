"""Tranco-Liste sicher herunterladen und in SQLite überführen."""

from __future__ import annotations

import io
import logging
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from src.services.tranco_popularity import (
    build_sqlite_from_rank_pairs,
    get_tranco_store,
    tranco_data_dir,
    tranco_db_path,
    tranco_top_n_threshold,
)
from src.services.tranco_update_lock import (
    release_tranco_update_lock,
    try_acquire_tranco_update_lock,
)

logger = logging.getLogger(__name__)

TRANCO_DOWNLOAD_HOST = "tranco-list.eu"
TRANCO_DAILY_ZIP_URL = f"https://{TRANCO_DOWNLOAD_HOST}/top-1m.csv.zip"
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_CSV_BYTES = 200 * 1024 * 1024
MIN_CSV_LINES = 900_000
OVERLAP_MIN_RATIO = 0.70
OVERLAP_SAMPLE = 10_000
_REDIRECT_HOPS = 5

_PUBLIC_ERROR = "Tranco-Aktualisierung fehlgeschlagen. Details stehen im Server-Log."
_HINT_CHOWN = (
    "Verzeichnis data/tranco muss für User mailhelper schreibbar sein "
    "(nach git pull als root: chown -R mailhelper:mailhelper …/data/tranco)."
)


class TrancoStepHttpError(Exception):
    """HTTP-Fehler an einem Tranco-Schritt (ohne URL in der Meldung)."""

    def __init__(self, step: str, status_code: int):
        self.step = step
        self.status_code = status_code
        super().__init__(f"{step}: HTTP {status_code}")


def _failure_from_exception(exc: BaseException) -> dict:
    """Sichere, handlungsorientierte Fehler für UI (ohne Secrets/URLs)."""
    if isinstance(exc, sqlite3.OperationalError):
        low = str(exc).lower()
        if "unable to open database file" in low or "readonly" in low:
            return {
                "ok": False,
                "error": "SQLite kann tranco.db nicht anlegen oder öffnen.",
                "hint": _HINT_CHOWN,
            }
    if isinstance(exc, PermissionError):
        return {
            "ok": False,
            "error": "Keine Schreibrechte in data/tranco.",
            "hint": _HINT_CHOWN,
        }
    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) in (13, 30):
            return {
                "ok": False,
                "error": "Keine Schreibrechte in data/tranco.",
                "hint": _HINT_CHOWN,
            }
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "exceeds" in msg and "bytes" in msg:
            return {
                "ok": False,
                "error": "Tranco-Download überschreitet das Größenlimit.",
                "hint": msg,
            }
        if "empty body" in msg.lower():
            return {
                "ok": False,
                "error": "Tranco-Download war leer.",
                "hint": "Netzwerk/Proxy oder abgebrochene Verbindung — erneut versuchen.",
            }
        if "line count" in msg or "parsed rows" in msg:
            return {
                "ok": False,
                "error": "Tranco-Liste unvollständig oder ungültig.",
                "hint": msg,
            }
        if "redirect" in msg.lower() or "blocked" in msg.lower():
            return {
                "ok": False,
                "error": "Tranco-Download abgelehnt (Sicherheitsregel).",
                "hint": msg,
            }
        if "daily_list_id" in msg.lower() or "invalid" in msg.lower():
            return {
                "ok": False,
                "error": "Tranco-Listen-ID konnte nicht ermittelt werden.",
                "hint": msg,
            }
    if isinstance(exc, TrancoStepHttpError):
        return {
            "ok": False,
            "error": f"Tranco {exc.step}: HTTP {exc.status_code}",
            "hint": "Kurz nach Mitternacht UTC ggf. noch keine Tagesliste — erneut versuchen.",
        }
    if isinstance(exc, requests.HTTPError):
        code = getattr(getattr(exc, "response", None), "status_code", None)
        hint = f"HTTP {code}" if code else "HTTPError"
        hint += " — kurz nach Mitternacht UTC ggf. noch keine Tagesliste; erneut versuchen."
        return {
            "ok": False,
            "error": "Tranco-Download: HTTP-Fehlerstatus.",
            "hint": hint,
        }
    if isinstance(exc, requests.RequestException):
        return {
            "ok": False,
            "error": "Netzwerkfehler beim Tranco-Download.",
            "hint": type(exc).__name__,
        }
    return {"ok": False, "error": _PUBLIC_ERROR}


def _check_tranco_data_dir_writable() -> Optional[dict]:
    """Schreibprobe — verhindert generischen Fehler nach langem Download."""
    dest_dir = tranco_data_dir()
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.exception("Tranco data dir not creatable: %s", exc)
        return {
            "ok": False,
            "error": "Verzeichnis data/tranco kann nicht angelegt werden.",
            "hint": _HINT_CHOWN,
        }
    probe = dest_dir / ".write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Tranco data dir not writable: %s", exc)
        return {
            "ok": False,
            "error": "Verzeichnis data/tranco ist nicht beschreibbar.",
            "hint": _HINT_CHOWN,
        }
    return None


def tranco_list_id_fixed() -> str:
    """Nur gesetzte TRANCO_LIST_ID — sonst leer (dann daily API)."""
    return os.getenv("TRANCO_LIST_ID", "").strip()


def tranco_auto_update_enabled() -> bool:
    return os.getenv("TRANCO_AUTO_UPDATE", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _allowed_tranco_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme != "https":
        return False
    host = (p.hostname or "").lower().rstrip(".")
    return host == TRANCO_DOWNLOAD_HOST


def _resolve_tranco_redirect(current: str, location: str) -> str:
    loc = (location or "").strip()
    if not loc:
        raise ValueError("Tranco redirect without Location")
    if loc.startswith("/") or not loc.lower().startswith("http"):
        next_url = urljoin(current, loc)
    else:
        next_url = loc
    if not _allowed_tranco_url(next_url):
        raise ValueError("Tranco redirect to disallowed host")
    return next_url


def _download_tranco_https(url: str, dest: Path, limit: int) -> int:
    """
    HTTPS-Download mit Redirect-Hops; Body wird innerhalb des offenen Response gelesen.
    Response nicht aus `with` zurückgeben — sonst leerer Body bei iter_content.
    """
    if not _allowed_tranco_url(url):
        raise ValueError("Tranco download URL blocked")
    current = url
    for _ in range(_REDIRECT_HOPS):
        with requests.get(
            current, timeout=120, stream=True, allow_redirects=False
        ) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location") or ""
                current = _resolve_tranco_redirect(current, loc)
                continue
            if resp.status_code >= 400:
                raise TrancoStepHttpError("Download", resp.status_code)
            resp.raise_for_status()
            total = 0
            with dest.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise ValueError(f"Tranco download exceeds {limit} bytes")
                    out.write(chunk)
            if total == 0:
                raise ValueError("Tranco download empty body")
            return total
    raise ValueError("Tranco redirect loop")


def fetch_daily_tranco_list_id(*, day: Optional[datetime] = None) -> str:
    """Aktuelle Listen-ID (gestern UTC), wie offizielles tranco-Paket."""
    ref = day or (datetime.now(timezone.utc) - timedelta(days=1))
    date_s = ref.strftime("%Y-%m-%d")
    url = (
        f"https://{TRANCO_DOWNLOAD_HOST}/daily_list_id"
        f"?date={date_s}&subdomains=false"
    )
    with requests.get(url, timeout=60, allow_redirects=False) as resp:
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location") or ""
            next_url = _resolve_tranco_redirect(url, loc)
            with requests.get(next_url, timeout=60, allow_redirects=False) as resp2:
                if resp2.status_code >= 400:
                    raise TrancoStepHttpError("Listen-ID", resp2.status_code)
                resp2.raise_for_status()
                list_id = (resp2.text or "").strip()
        else:
            if resp.status_code >= 400:
                raise TrancoStepHttpError("Listen-ID", resp.status_code)
            resp.raise_for_status()
            list_id = (resp.text or "").strip()
    if not list_id or not re.match(r"^[A-Z0-9]+$", list_id):
        raise ValueError("Tranco daily_list_id invalid")
    return list_id


def resolve_tranco_list_id(*, align_with_daily_zip: bool = False) -> str:
    fixed = tranco_list_id_fixed()
    if fixed:
        return fixed
    if align_with_daily_zip:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        for day in (yesterday, now):
            try:
                return fetch_daily_tranco_list_id(day=day)
            except Exception as exc:
                logger.warning("Tranco daily_list_id %s failed: %s", day.date(), exc)
        raise ValueError("Tranco daily_list_id invalid")
    return fetch_daily_tranco_list_id()


def download_url(list_id: str) -> str:
    return f"https://{TRANCO_DOWNLOAD_HOST}/download/{list_id}/1000000"


def resolve_tranco_download_url(list_id: str) -> str:
    """Standard: offizielles daily ZIP (~10 MB). Override: TRANCO_DOWNLOAD_URL."""
    custom = os.getenv("TRANCO_DOWNLOAD_URL", "").strip()
    if custom:
        if not _allowed_tranco_url(custom):
            raise ValueError("Tranco TRANCO_DOWNLOAD_URL blocked")
        return custom
    mode = os.getenv("TRANCO_DOWNLOAD_MODE", "zip").strip().lower()
    if mode in ("csv", "list", "legacy"):
        return download_url(list_id)
    return TRANCO_DAILY_ZIP_URL


def _fetch_list_blob(list_id: str, *, force_csv: bool = False) -> bytes:
    if force_csv:
        url = download_url(list_id)
        if not _allowed_tranco_url(url):
            raise ValueError("Tranco download URL blocked")
    else:
        url = resolve_tranco_download_url(list_id)
    work = tranco_data_dir()
    tmp = work / ".tranco_download.tmp"
    try:
        nbytes = _download_tranco_https(url, tmp, MAX_ZIP_BYTES)
        logger.info("Tranco fetch %s: downloaded %s bytes", url, nbytes)
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def _extract_csv_from_zip(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"Unexpected zip entries: {len(names)}")
        with zf.open(names[0]) as raw:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = raw.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_CSV_BYTES:
                    raise ValueError("Tranco CSV too large after unzip")
                chunks.append(chunk)
            return b"".join(chunks)


def parse_tranco_csv(raw: bytes) -> List[Tuple[int, str]]:
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) < MIN_CSV_LINES:
        raise ValueError(f"Tranco CSV line count low: {len(lines)}")
    pairs: List[Tuple[int, str]] = []
    for line in lines:
        line = line.strip()
        if not line or "," not in line:
            continue
        rank_s, domain = line.split(",", 1)
        try:
            rank = int(rank_s.strip())
        except ValueError:
            continue
        dom = domain.strip().lower().strip(".")
        if dom and "." in dom:
            pairs.append((rank, dom))
    if len(pairs) < MIN_CSV_LINES - 1000:
        raise ValueError(f"Tranco parsed rows low: {len(pairs)}")
    return pairs


def _overlap_ratio(old_top: set, new_top: set) -> float:
    if not old_top:
        return 1.0
    inter = len(old_top & new_top)
    return inter / len(old_top)


def update_tranco_database(*, force: bool = False) -> dict:
    """
    Lädt Tranco, baut SQLite (Top N). Behält alte DB bei Fehler/Overlap.
    """
    if not try_acquire_tranco_update_lock():
        return {
            "ok": False,
            "busy": True,
            "message": "Tranco-Aktualisierung läuft bereits.",
        }

    try:
        writable = _check_tranco_data_dir_writable()
        if writable:
            return writable

        mode = os.getenv("TRANCO_DOWNLOAD_MODE", "zip").strip().lower()
        custom_url = os.getenv("TRANCO_DOWNLOAD_URL", "").strip()
        use_daily_zip = not custom_url and mode not in ("csv", "list", "legacy")
        list_id = resolve_tranco_list_id(align_with_daily_zip=use_daily_zip)
        dest = tranco_db_path()

        if not force and not tranco_auto_update_enabled():
            return {"ok": False, "skipped": True, "reason": "TRANCO_AUTO_UPDATE=false"}

        old_store = get_tranco_store()
        old_top: set = set()
        if old_store and dest.is_file():
            old_top = old_store.top_domains(OVERLAP_SAMPLE)

        try:
            blob = _fetch_list_blob(list_id)
        except (requests.HTTPError, TrancoStepHttpError):
            if use_daily_zip and not tranco_list_id_fixed():
                fallback_id = fetch_daily_tranco_list_id(
                    day=datetime.now(timezone.utc) - timedelta(days=1)
                )
                logger.warning(
                    "Tranco ZIP/HTTP failed — CSV-Fallback list_id=%s",
                    fallback_id,
                )
                list_id = fallback_id
                blob = _fetch_list_blob(list_id, force_csv=True)
            else:
                raise
        if blob[:2] == b"PK":
            csv_bytes = _extract_csv_from_zip(blob)
        else:
            csv_bytes = blob
            if len(csv_bytes) > MAX_CSV_BYTES:
                raise ValueError("Tranco CSV too large")
        pairs = parse_tranco_csv(csv_bytes)
        new_top = {d for r, d in pairs if r <= OVERLAP_SAMPLE}
        ratio = _overlap_ratio(old_top, new_top)
        if old_top and ratio < OVERLAP_MIN_RATIO:
            msg = f"Tranco overlap {ratio:.0%} < {OVERLAP_MIN_RATIO:.0%} — keeping old DB"
            logger.warning(msg)
            return {"ok": False, "overlap_rejected": True, "overlap_ratio": ratio, "message": msg}

        max_rank = tranco_top_n_threshold()
        filtered = [(r, d) for r, d in pairs if r <= max_rank]
        tmp = dest.with_suffix(".tmp")
        build_sqlite_from_rank_pairs(filtered, tmp, list_id=list_id, max_rank=max_rank)
        conn = sqlite3.connect(str(tmp))
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at', ?)", (now,))
        conn.execute(
            "INSERT OR REPLACE INTO meta VALUES ('citation', ?)",
            (
                "Le Pochat et al., Tranco, NDSS 2019, doi:10.14722/ndss.2019.23386",
            ),
        )
        conn.commit()
        conn.close()
        backup = dest.with_suffix(".bak")
        if dest.is_file():
            dest.replace(backup)
        tmp.replace(dest)
        get_tranco_store(force_reload=True)
        return {
            "ok": True,
            "list_id": list_id,
            "domains": len(filtered),
            "overlap_ratio": ratio,
            "updated_at": now,
        }
    except Exception as exc:
        logger.exception("Tranco update failed: %s", exc)
        return _failure_from_exception(exc)
    finally:
        release_tranco_update_lock()
