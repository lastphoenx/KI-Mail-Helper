"""Celery: Ordner-Audit Scan (IMAP Header + Layer 1 + LLM-Batch)."""

from __future__ import annotations

import logging
from typing import List, Optional

from src.celery_app import celery_app
from src.helpers.database import get_session, get_user, get_mail_account
from src.helpers.imap_fetcher_factory import build_imap_fetcher_for_account
from src.helpers.service_token_dek import (
    delete_service_token,
    get_dek_from_service_token,
)
from src.services.folder_audit_scan_lock import release_folder_audit_scan_lock
from src.services.folder_audit_service import FolderAuditService
from src.services.folder_audit_scan_store import store_scan_payload

logger = logging.getLogger(__name__)

_SCAN_TIME_LIMIT = 7200
_SCAN_SOFT_LIMIT = 6900


@celery_app.task(
    bind=True,
    name="tasks.folder_audit.run_scan",
    soft_time_limit=_SCAN_SOFT_LIMIT,
    time_limit=_SCAN_TIME_LIMIT,
)
def run_folder_audit_scan_task(
    self,
    user_id: int,
    account_id: int,
    service_token_id: int,
    limit: int,
    folder: str,
    cluster_mode: str,
    exclude_folders: Optional[List[str]] = None,
) -> dict:
    """Scannt Ordner-Audit asynchron; Fortschritt via update_state(PROGRESS)."""
    session = get_session()
    fetcher = None
    exclude_folders = exclude_folders or []
    lock_owner = self.request.id

    def progress(meta: dict) -> None:
        payload = {
            "phase": meta.get("phase", "scan"),
            "message": meta.get("message", "Scan läuft…"),
            "processed": meta.get("processed"),
            "total": meta.get("total"),
            "folder": meta.get("folder"),
            "folder_index": meta.get("folder_index"),
            "folder_count": meta.get("folder_count"),
            "llm_provider": meta.get("llm_provider"),
            "llm_model": meta.get("llm_model"),
            "llm_mode": meta.get("llm_mode"),
            "llm_budget": meta.get("llm_budget"),
            "llm_time_budget_sec": meta.get("llm_time_budget_sec"),
        }
        self.update_state(state="PROGRESS", meta=payload)

    try:
        user = get_user(session, user_id)
        account = get_mail_account(session, account_id, user_id)
        if not user or not account:
            return {"success": False, "error": "scan_failed"}

        master_key = get_dek_from_service_token(service_token_id, session)
        if not master_key:
            return {"success": False, "error": "scan_failed"}

        progress({"phase": "connect", "message": "IMAP-Verbindung…"})
        fetcher = build_imap_fetcher_for_account(account, master_key)
        fetcher.connect()
        if not fetcher.connection:
            return {"success": False, "error": "scan_failed"}

        if cluster_mode not in ("cleanup", "maintenance"):
            cluster_mode = "cleanup"

        if folder == "__ALL__":
            progress(
                {
                    "phase": "scan",
                    "message": "Alle Ordner — Liste wird aufgebaut…",
                }
            )
            result = FolderAuditService.fetch_and_analyze_all_folders(
                fetcher,
                limit_per_folder=500,
                max_total=limit,
                db_session=session,
                user_id=user_id,
                account_id=account_id,
                exclude_folders=exclude_folders,
                cluster_mode=cluster_mode,
                progress_callback=progress,
            )
            scan_folder = "Alle Ordner"
        else:
            result = FolderAuditService.fetch_and_analyze_trash(
                fetcher,
                limit,
                db_session=session,
                user_id=user_id,
                account_id=account_id,
                folder=folder,
                cluster_mode=cluster_mode,
                progress_callback=progress,
            )
            scan_folder = folder or "Trash"

        progress({"phase": "done", "message": "Scan abgeschlossen"})
        payload = {
            "result": result.to_dict(),
            "folder": scan_folder,
        }
        store_scan_payload(self.request.id, payload)
        return {
            "success": True,
            "scan_result_id": self.request.id,
            "folder": scan_folder,
        }
    except Exception as exc:
        logger.exception("Folder audit scan task failed: %s", exc)
        return {"success": False, "error": "scan_failed"}
    finally:
        delete_service_token(service_token_id, session)
        release_folder_audit_scan_lock(user_id, account_id, lock_owner)
        if fetcher:
            try:
                fetcher.disconnect()
            except Exception:
                pass
        try:
            session.close()
        except Exception:
            pass
