"""Bekannte Kontakte aus Gesendet (To/Cc) — nur Header, inkrementell per UID."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from email.utils import getaddresses
from typing import Any, Dict, List, Optional, Tuple

from src.services.audit_safe_delete_veto import is_sent_or_drafts_folder
from src.services.audit_scam_detection import normalize_sender_email
from src.services.folder_audit_service import decode_mime_header

logger = logging.getLogger(__name__)

_HEADER_FETCH = ["BODY.PEEK[HEADER.FIELDS (TO CC)]"]


def _parse_import_state(raw: Optional[str]) -> Dict[str, int]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out: Dict[str, int] = {}
            for k, v in data.items():
                if str(k).startswith("_"):
                    continue
                if v is not None:
                    out[str(k)] = int(v)
            return out
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}


def _last_import_from_state(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            li = data.get("_last_import")
            if isinstance(li, dict):
                return li
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _dump_import_state(state: Dict[str, int], *, last_import: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = dict(state)
    if last_import is not None:
        payload["_last_import"] = last_import
    return json.dumps(payload, sort_keys=True)


def _coalesce_display_name(email: str, header_name: str) -> str:
    """Anzeigename aus To/Cc-Header; Fallback nur aus Local-Part (keine reinen Ziffern-IDs)."""
    hn = (header_name or "").strip()
    em = (email or "").lower()
    if hn and "@" not in hn and hn.lower() != em:
        return hn[:512]
    if not em or "@" not in em:
        return ""
    lp = em.split("@", 1)[0]
    if re.fullmatch(r"\d{5,}", lp):
        return ""
    if re.fullmatch(r"[a-z0-9._+-]+", lp, re.I):
        hint = re.sub(r"[._+-]+", " ", lp).strip()
        if len(hint) >= 3 and not hint.isdigit():
            return hint[:512]
    return ""


def _list_sent_folders(conn) -> List[str]:
    out: List[str] = []
    for flags, _delim, name in conn.list_folders():
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        if not is_sent_or_drafts_folder(name):
            continue
        tail = name.replace("\\", "/").split("/")[-1].lower()
        if "draft" in tail or "entw" in tail or "brouillon" in tail:
            continue
        out.append(name)
    return out


def _extract_addresses(header_blob: bytes) -> List[Tuple[str, str]]:
    if not header_blob:
        return []
    text = header_blob.decode("utf-8", errors="replace")
    pairs = getaddresses([text])
    out: List[Tuple[str, str]] = []
    for display, addr in pairs:
        em = normalize_sender_email(addr or "")
        if not em or "@" not in em:
            continue
        name = decode_mime_header(display or "")
        out.append((em, name))
    return out


def _upsert_contact(
    db_session,
    models,
    *,
    user_id: int,
    account_id: int,
    email: str,
    display_name: str,
    source: str = "sent",
) -> None:
    row = (
        db_session.query(models.AuditKnownContact)
        .filter_by(
            user_id=user_id,
            account_id=account_id,
            email_normalized=email,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if row:
        row.mail_count = int(row.mail_count or 0) + 1
        row.last_seen_at = now
        chosen = _coalesce_display_name(email, display_name)
        if chosen:
            prev = (row.display_name or "").strip()
            if not prev or len(chosen) > len(prev):
                row.display_name = chosen
        row.is_active = True
        if row.source not in ("vip", "trusted", "reply") and source == "sent":
            row.source = "sent"
        return
    chosen = _coalesce_display_name(email, display_name)
    db_session.add(
        models.AuditKnownContact(
            user_id=user_id,
            account_id=account_id,
            email_normalized=email,
            display_name=chosen or None,
            source=source,
            mail_count=1,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        )
    )


def import_sent_contacts_for_account(
    db_session,
    fetcher,
    *,
    user_id: int,
    account_id: int,
    max_messages_per_folder: int = 5000,
) -> Dict[str, Any]:
    """Liest To/Cc aus Gesendet-Ordnern; aktualisiert audit_known_contacts."""
    import importlib

    models = importlib.import_module(".02_models", "src")
    account = (
        db_session.query(models.MailAccount)
        .filter_by(id=account_id, user_id=user_id)
        .first()
    )
    if not account:
        return {"success": False, "error": "account_not_found"}

    conn = fetcher.connection
    if not conn:
        return {"success": False, "error": "not_connected"}

    state = _parse_import_state(getattr(account, "audit_contacts_import_state", None))
    own_email = (fetcher.username or "").strip().lower()
    folders = _list_sent_folders(conn)
    added = 0
    scanned = 0

    for folder in folders:
        try:
            conn.select_folder(folder, readonly=True)
        except Exception as e:
            logger.warning("Sent folder select failed %s: %s", folder, e)
            continue
        uids = list(conn.search(["ALL"]))
        last_uid = state.get(folder, 0)
        new_uids = sorted(u for u in uids if u > last_uid)
        if max_messages_per_folder and len(new_uids) > max_messages_per_folder:
            new_uids = new_uids[-max_messages_per_folder:]
        max_uid = last_uid
        for i in range(0, len(new_uids), 100):
            batch = new_uids[i : i + 100]
            if not batch:
                continue
            try:
                data = conn.fetch(batch, _HEADER_FETCH)
            except Exception as e:
                logger.warning("Sent header fetch failed: %s", e)
                continue
            for uid in batch:
                max_uid = max(max_uid, uid)
                scanned += 1
                raw = data.get(uid) or {}
                blob = None
                for key, val in raw.items():
                    if isinstance(key, (bytes, str)) and "HEADER" in str(key).upper():
                        blob = val
                        break
                if blob is None:
                    continue
                for em, name in _extract_addresses(blob):
                    if own_email and em == own_email:
                        continue
                    _upsert_contact(
                        db_session,
                        models,
                        user_id=user_id,
                        account_id=account_id,
                        email=em,
                        display_name=name,
                    )
                    added += 1
        state[folder] = max_uid

    contact_total = (
        db_session.query(models.AuditKnownContact)
        .filter_by(user_id=user_id, account_id=account_id, is_active=True)
        .count()
    )
    last_import = {
        "at": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "folders": len(folders),
        "scanned_messages": scanned,
        "address_upserts": added,
        "contact_count": int(contact_total),
    }
    account.audit_contacts_import_state = _dump_import_state(state, last_import=last_import)
    db_session.commit()
    return {
        "success": True,
        "folders": len(folders),
        "scanned_messages": scanned,
        "address_upserts": added,
        "contact_count": int(contact_total),
        "last_import": last_import,
    }


def delete_known_contact(
    db_session, user_id: int, account_id: int, contact_id: int
) -> bool:
    import importlib

    models = importlib.import_module(".02_models", "src")
    row = (
        db_session.query(models.AuditKnownContact)
        .filter_by(
            id=contact_id,
            user_id=user_id,
            account_id=account_id,
        )
        .first()
    )
    if not row:
        return False
    db_session.delete(row)
    db_session.commit()
    return True


def clear_known_contacts(db_session, user_id: int, account_id: int) -> int:
    import importlib

    models = importlib.import_module(".02_models", "src")
    q = db_session.query(models.AuditKnownContact).filter_by(
        user_id=user_id,
        account_id=account_id,
    )
    count = q.count()
    q.delete(synchronize_session=False)
    account = (
        db_session.query(models.MailAccount)
        .filter_by(id=account_id, user_id=user_id)
        .first()
    )
    if account:
        account.audit_contacts_import_state = None
    db_session.commit()
    return count
