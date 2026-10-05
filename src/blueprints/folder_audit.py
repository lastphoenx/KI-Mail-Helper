"""
Folder Audit Blueprint - Papierkorb-Analyse und Aufräum-Tool

Endpoints:
    GET  /folder-audit         - Haupt-UI für Folder-Audit
    GET  /folder-audit/scan-settings/<account_id> - Audit-Ordner-Ausschlüsse laden
    POST /folder-audit/scan-settings - Audit-Ordner-Ausschlüsse speichern
    POST /folder-audit/scan    - Startet Scan async (Celery)
    POST /folder-audit/delete  - Löscht ausgewählte Emails permanent
    POST /folder-audit/preview - Textanfang einer Mail (IMAP PEEK, on-demand)
    POST /folder-audit/identity-check - Manueller Identitäts-Check (Layer1 + LLM)
"""

import logging
import json
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
import importlib

from src.helpers import get_db_session, get_current_user_model
from src.services.folder_audit_service import FolderAuditService, TrashCategory, AuditConfigCache

logger = logging.getLogger(__name__)

folder_audit_bp = Blueprint("folder_audit", __name__)


def _parse_audit_exclude_folders(account) -> list:
    raw = getattr(account, "audit_exclude_folders", None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid audit_exclude_folders JSON for account %s", getattr(account, "id", "?"))
    return []


def _parse_audit_own_domains(account) -> list:
    raw = getattr(account, "audit_own_domains", None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip().lower() for x in data if str(x).strip()]
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid audit_own_domains JSON for account %s", getattr(account, "id", "?"))
    return []


def _parse_scan_account_id(raw) -> int:
    try:
        account_id = int(raw)
    except (TypeError, ValueError):
        raise ValueError("account_id ungültig")
    if account_id < 1:
        raise ValueError("account_id ungültig")
    return account_id


def _parse_scan_limit(raw) -> int:
    if raw is None:
        return 5000
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise ValueError("limit ungültig")
    if limit < 1 or limit > 10000:
        raise ValueError("limit muss zwischen 1 und 10000 liegen")
    return limit


def _run_sync_folder_audit_scan(
    *,
    fetcher,
    db,
    user,
    account,
    limit: int,
    folder: str,
    cluster_mode: str,
    audit_exclude: list,
):
    if folder == "__ALL__":
        result = FolderAuditService.fetch_and_analyze_all_folders(
            fetcher,
            limit_per_folder=500,
            max_total=limit,
            db_session=db,
            user_id=user.id,
            account_id=account.id,
            exclude_folders=audit_exclude,
            cluster_mode=cluster_mode,
        )
        return result, "Alle Ordner"
    result = FolderAuditService.fetch_and_analyze_trash(
        fetcher,
        limit,
        db_session=db,
        user_id=user.id,
        account_id=account.id,
        folder=str(folder),
        cluster_mode=cluster_mode,
    )
    return result, folder or "Trash"


_models = None
_encryption = None
_mail_fetcher_mod = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


def _get_encryption():
    global _encryption
    if _encryption is None:
        _encryption = importlib.import_module(".08_encryption", "src")
    return _encryption


def _get_mail_fetcher_mod():
    global _mail_fetcher_mod
    if _mail_fetcher_mod is None:
        _mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
    return _mail_fetcher_mod


def _get_imap_fetcher(account, master_key):
    """Helper: Erstellt IMAP-Fetcher mit entschlüsselten Credentials."""
    from src.helpers.imap_fetcher_factory import build_imap_fetcher_for_account

    return build_imap_fetcher_for_account(account, master_key)


# =============================================================================
# Routes
# =============================================================================

@folder_audit_bp.route("/folder-audit")
@login_required
def folder_audit_page():
    """Hauptseite für Folder-Audit"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        # IMAP-Accounts laden
        accounts = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.user_id == user.id,
                models.MailAccount.auth_type == "imap",
            )
            .all()
        )
        
        account_list = [
            {"id": a.id, "name": a.name or f"Account {a.id}"}
            for a in accounts
        ]
        
        return render_template(
            "folder_audit.html",
            accounts=account_list,
        )


@folder_audit_bp.route("/folder-audit/folders/<int:account_id>", methods=["GET"])
@login_required
def get_folders(account_id):
    """Holt IMAP-Ordnerliste für einen Account"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        models = _get_models()
        
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )
        
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        fetcher = None
        try:
            fetcher = _get_imap_fetcher(account, master_key)
            fetcher.connect()
            
            if not fetcher.connection:
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500
            
            # Ordner-Liste holen
            folders_raw = fetcher.connection.list_folders()
            
            # Ordner sortieren und formatieren
            folders = []
            for flags, delimiter, name in folders_raw:
                # Überspringen von nicht-selektierbaren Ordnern
                if b'\\Noselect' in flags:
                    continue
                folders.append({
                    "name": name,
                    "flags": [f.decode() if isinstance(f, bytes) else f for f in flags],
                })
            
            # Sortiere: Standard-Ordner zuerst
            priority = {"INBOX": 0, "Trash": 1, "Deleted": 1, "Junk": 2, "Spam": 2, 
                       "Sent": 3, "Drafts": 4, "Archive": 5}
            folders.sort(key=lambda f: (priority.get(f["name"], 99), f["name"]))
            
            return jsonify({
                "success": True,
                "folders": [f["name"] for f in folders],
            })
            
        except Exception as e:
            logger.error(f"Folder list error: {type(e).__name__}: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            if fetcher:
                fetcher.disconnect()


@folder_audit_bp.route("/folder-audit/scan-settings/<int:account_id>", methods=["GET"])
@login_required
def get_scan_settings(account_id):
    """Gespeicherte Ordner-Audit Scan-Ausschlüsse (pro Account)."""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        return jsonify({
            "success": True,
            "account_id": account_id,
            "exclude_folders": _parse_audit_exclude_folders(account),
            "own_domains": _parse_audit_own_domains(account),
        })


@folder_audit_bp.route("/folder-audit/scan-settings", methods=["POST"])
@login_required
def save_scan_settings():
    """Speichert Ordner, die beim Ordner-Audit (Alle Ordner) übersprungen werden."""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        data = request.get_json() or {}
        account_id = data.get("account_id")
        exclude_folders = data.get("exclude_folders")
        own_domains = data.get("own_domains")

        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        if exclude_folders is None and own_domains is None:
            return jsonify({"error": "exclude_folders oder own_domains erforderlich"}), 400
        if exclude_folders is not None and not isinstance(exclude_folders, list):
            return jsonify({"error": "exclude_folders muss eine Liste sein"}), 400
        if own_domains is not None and not isinstance(own_domains, list):
            return jsonify({"error": "own_domains muss eine Liste sein"}), 400

        cleaned = []
        seen = set()
        if exclude_folders is not None:
            for item in exclude_folders:
                name = str(item).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                cleaned.append(name)

        cleaned_domains = []
        seen_dom = set()
        if own_domains is not None:
            for item in own_domains:
                dom = str(item).strip().lower().lstrip("@")
                if not dom or dom in seen_dom:
                    continue
                seen_dom.add(dom)
                cleaned_domains.append(dom)

        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        if exclude_folders is not None:
            account.audit_exclude_folders = json.dumps(cleaned) if cleaned else None
        if own_domains is not None:
            account.audit_own_domains = json.dumps(cleaned_domains) if cleaned_domains else None
        db.commit()

        from src.services.folder_audit_service import AuditConfigCache
        AuditConfigCache.clear_cache(user.id)

        return jsonify({
            "success": True,
            "account_id": account_id,
            "exclude_folders": _parse_audit_exclude_folders(account),
            "own_domains": _parse_audit_own_domains(account),
        })


@folder_audit_bp.route("/folder-audit/scan", methods=["POST"])
@login_required
def scan_trash():
    """Startet Ordner-Audit-Scan asynchron (Celery)."""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich. Bitte neu einloggen."}), 401

        data = request.get_json() or {}
        try:
            account_id = _parse_scan_account_id(data.get("account_id"))
            limit = _parse_scan_limit(data.get("limit"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        folder = data.get("folder")
        cluster_mode = data.get("cluster_mode", "cleanup")
        if cluster_mode not in ("cleanup", "maintenance"):
            cluster_mode = "cleanup"

        if not folder:
            return jsonify({"error": "folder erforderlich"}), 400

        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
                models.MailAccount.auth_type == "imap",
            )
            .first()
        )
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        audit_exclude = _parse_audit_exclude_folders(account)

        from src.services.folder_audit_scan_lock import (
            handoff_folder_audit_scan_lock,
            release_folder_audit_scan_lock,
            try_acquire_folder_audit_scan_lock,
        )
        from src.helpers.service_token_dek import delete_service_token

        lock_start = "queue"
        if not try_acquire_folder_audit_scan_lock(user.id, account.id, lock_start):
            return jsonify(
                {"error": "Scan für diesen Account läuft bereits"}
            ), 409

        service_token_id = None
        try:
            from src.tasks.folder_audit_tasks import run_folder_audit_scan_task
            from src.helpers.task_ownership import track_celery_task

            auth = importlib.import_module(".07_auth", "src")
            ServiceTokenManager = auth.ServiceTokenManager

            _, service_token = ServiceTokenManager.create_token(
                user_id=user.id,
                master_key=master_key,
                session=db,
                days=1,
            )
            service_token_id = service_token.id

            task = track_celery_task(
                run_folder_audit_scan_task.delay(
                    user_id=user.id,
                    account_id=account_id,
                    service_token_id=service_token_id,
                    limit=limit,
                    folder=str(folder),
                    cluster_mode=cluster_mode,
                    exclude_folders=audit_exclude,
                ),
                user.id,
            )
            handoff_folder_audit_scan_lock(
                user.id, account.id, lock_start, task.id
            )
            return jsonify(
                {
                    "status": "queued",
                    "task_id": task.id,
                    "task_type": "celery",
                }
            )
        except Exception as e:
            logger.exception(
                "Folder-audit Celery queue failed, sync fallback: %s", e
            )
            if service_token_id:
                delete_service_token(service_token_id, db)
            release_folder_audit_scan_lock(user.id, account.id, lock_start)
            if not try_acquire_folder_audit_scan_lock(
                user.id, account.id, "sync"
            ):
                return jsonify(
                    {"error": "Scan für diesen Account läuft bereits"}
                ), 409

            fetcher = None
            try:
                fetcher = _get_imap_fetcher(account, master_key)
                fetcher.connect()
                if not fetcher.connection:
                    return jsonify({"error": "Scan fehlgeschlagen"}), 500

                result, scan_folder = _run_sync_folder_audit_scan(
                    fetcher=fetcher,
                    db=db,
                    user=user,
                    account=account,
                    limit=limit,
                    folder=str(folder),
                    cluster_mode=cluster_mode,
                    audit_exclude=audit_exclude,
                )
                return jsonify(
                    {
                        "success": True,
                        "result": result.to_dict(),
                        "folder": scan_folder,
                    }
                )
            except Exception:
                logger.exception("Folder-audit sync scan failed")
                return jsonify({"error": "Scan fehlgeschlagen"}), 500
            finally:
                if fetcher:
                    fetcher.disconnect()
                release_folder_audit_scan_lock(user.id, account.id, "sync")


@folder_audit_bp.route("/folder-audit/scan-result/<string:task_id>", methods=["GET"])
@login_required
def folder_audit_scan_result(task_id: str):
    """Lädt gespeichertes Scan-Ergebnis (Redis) nach Celery-Abschluss."""
    if not task_id or len(task_id) > 100:
        return jsonify({"error": "Ungültige Task-ID"}), 400

    from src.celery_app import celery_app
    from src.helpers.task_ownership import verify_celery_task_access
    from src.services.folder_audit_scan_store import pop_scan_payload

    if not verify_celery_task_access(celery_app, task_id, current_user.id):
        return jsonify({"error": "Nicht gefunden"}), 404

    payload = pop_scan_payload(task_id)
    if not payload:
        return jsonify({"error": "Ergebnis abgelaufen oder noch nicht bereit"}), 404

    return jsonify({"success": True, **payload})


@folder_audit_bp.route("/folder-audit/llm-continue", methods=["POST"])
@login_required
def folder_audit_llm_continue():
    """Prüft LLM-Kandidaten, die beim Scan wegen Budget übersprungen wurden."""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        data = request.get_json() or {}
        try:
            account_id = _parse_scan_account_id(data.get("account_id"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        from src.services.audit_scam_detection import (
            AUDIT_SCAM_LLM_CONTINUE_MAX_PER_CALL,
        )

        raw_candidates = data.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            return jsonify({"error": "candidates erforderlich"}), 400
        max_items = AUDIT_SCAM_LLM_CONTINUE_MAX_PER_CALL
        if len(raw_candidates) > max_items:
            return jsonify(
                {
                    "error": f"Zu viele Kandidaten (max. {max_items} pro Aufruf)",
                }
            ), 400

        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        from src.services.audit_scam_llm_config import resolve_audit_scam_llm_config

        llm_cfg = resolve_audit_scam_llm_config(user)
        if not llm_cfg.enabled:
            return jsonify({"error": "Audit-LLM ist deaktiviert"}), 400

        emails: list = []
        for item in raw_candidates:
            if not isinstance(item, dict) or "uid" not in item:
                continue
            try:
                emails.append(FolderAuditService.trash_info_from_audit_payload(item))
            except (TypeError, ValueError, KeyError):
                continue
        if not emails:
            return jsonify({"error": "Keine gültigen Kandidaten"}), 400

        try:
            stats = FolderAuditService.run_llm_continue_for_emails(
                emails,
                user_id=user.id,
                llm_cfg=llm_cfg,
                db_session=db,
            )
        except Exception:
            logger.exception("folder audit llm-continue failed")
            return jsonify({"error": "LLM-Fortsetzung fehlgeschlagen"}), 500

        if stats.get("error") == "quota_exceeded":
            return jsonify(
                {
                    "error": "Tageslimit für Identitäts-LLM erreicht",
                    "quota_used": stats.get("quota_used"),
                }
            ), 429

        return jsonify(
            {
                "success": True,
                "processed": stats["processed"],
                "still_skipped": stats["still_skipped"],
                "quota_used": stats.get("quota_used"),
                "scan_notice": stats.get("scan_notice") or "",
                "emails": [e.to_dict() for e in emails],
            }
        )


@folder_audit_bp.route("/folder-audit/delete", methods=["POST"])
@login_required
def delete_trash_emails():
    """Löscht ausgewählte Emails permanent"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        data = request.get_json() or {}
        account_id = data.get("account_id")
        uids = data.get("uids", [])
        folder = data.get("folder")  # Optional: spezifischer Ordner (Legacy)
        items = data.get("items")  # [{folder, uid}, ...] für Multi-Ordner-Scan
        
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        if not items and not uids:
            return jsonify({"error": "Keine Mails angegeben (items oder uids)"}), 400
        
        models = _get_models()
        
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )
        
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        fetcher = None
        try:
            fetcher = _get_imap_fetcher(account, master_key)
            fetcher.connect()
            
            if not fetcher.connection:
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500
            
            if items:
                success, failed = FolderAuditService.delete_emails_by_folder(fetcher, items)
                if success == 0 and failed == 0 and items:
                    return jsonify({
                        "success": False,
                        "deleted": 0,
                        "failed": len(items),
                        "error": (
                            "Keine gültigen Ordner/UID in der Anfrage. "
                            "Scan neu starten (Hard-Reload). Nach git pull: Gunicorn neu starten."
                        ),
                    }), 400
            else:
                if folder in (None, "", "__ALL__"):
                    return jsonify({
                        "error": "Bei Löschen ohne items muss ein konkreter Ordner gesetzt sein",
                    }), 400
                success, failed = FolderAuditService.delete_safe_emails(fetcher, uids, folder)
            
            return jsonify({
                "success": True,
                "deleted": success,
                "failed": failed,
                "message": f"{success} Emails permanent gelöscht",
            })
            
        except Exception as e:
            logger.error(f"Trash delete error: {type(e).__name__}: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            if fetcher:
                fetcher.disconnect()


@folder_audit_bp.route("/folder-audit/identity-check", methods=["POST"])
@login_required
def folder_audit_identity_check():
    """Manueller Identitäts-Check für eine Audit-Zeile (eigenes Tageslimit, kein Scan-Budget)."""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        data = request.get_json() or {}
        account_id = data.get("account_id")
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400

        from types import SimpleNamespace
        from src.services.audit_scam_detection import run_manual_identity_check
        from src.services.audit_scam_llm_config import resolve_audit_scam_llm_config

        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
                models.MailAccount.auth_type == "imap",
            )
            .first()
        )
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        folder = data.get("folder")
        uid_raw = data.get("uid")
        use_imap = folder and uid_raw is not None

        if use_imap:
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key erforderlich"}), 401
            try:
                uid = int(uid_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "uid ungültig"}), 400
            fetcher = None
            try:
                fetcher = _get_imap_fetcher(account, master_key)
                fetcher.connect()
                if not fetcher.connection:
                    return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500
                info = FolderAuditService.peek_audit_meta(fetcher, str(folder), uid)
                meta = SimpleNamespace(
                    subject=info.subject or "",
                    sender=info.sender or "",
                    sender_name=info.sender_name or "",
                    auth_results=info.auth_results,
                    reply_to=info.reply_to,
                    x_mailer=info.x_mailer,
                    server_spam_flag=info.server_spam_flag,
                    provider_junk_score=info.provider_junk_score,
                    is_auto_generated=info.is_auto_generated,
                    to_header=info.to_header,
                    list_unsubscribe=info.has_list_unsubscribe,
                )
            except Exception as exc:
                logger.exception("Identity check IMAP meta: %s", exc)
                return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500
            finally:
                if fetcher:
                    fetcher.disconnect()
        else:
            meta = SimpleNamespace(
                subject=(data.get("subject") or "")[:500],
                sender=(data.get("sender") or "")[:320],
                sender_name=(data.get("sender_name") or "")[:320],
                auth_results=(data.get("auth_results") or "")[:2000] or None,
                reply_to=(data.get("reply_to") or "")[:320] or None,
                x_mailer=(data.get("x_mailer") or "")[:120] or None,
                server_spam_flag=bool(data.get("server_spam_flag")),
                provider_junk_score=data.get("provider_junk_score"),
                is_auto_generated=bool(data.get("is_auto_generated")),
                to_header=(data.get("to_header") or "")[:200] or None,
                list_unsubscribe=bool(
                    data.get("list_unsubscribe") or data.get("has_list_unsubscribe")
                ),
            )

        trusted = FolderAuditService._trusted_domains_for(db, user.id, account_id)
        audit_cfg = AuditConfigCache.get_config(db, user.id, account_id)
        brand_map = audit_cfg.get("brand_official_domains_effective")
        cfg = resolve_audit_scam_llm_config(user)
        payload = run_manual_identity_check(
            meta,
            user_id=user.id,
            audit_llm_config=cfg,
            db_session=db,
            trusted_domains=trusted,
            brand_map=brand_map,
        )
        if payload.get("error"):
            return jsonify(payload), 429
        return jsonify({"success": True, **payload})


@folder_audit_bp.route("/folder-audit/preview", methods=["POST"])
@login_required
def preview_email():
    """Lädt Textanfang einer Audit-Mail on-demand (IMAP PEEK)."""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich. Bitte neu einloggen."}), 401

        data = request.get_json() or {}
        account_id = data.get("account_id")
        folder = data.get("folder")
        uid = data.get("uid")

        if not account_id or not folder or uid is None:
            return jsonify({"error": "account_id, folder und uid erforderlich"}), 400
        if str(folder) == "__ALL__":
            return jsonify({"error": "Konkreten Ordner angeben, nicht Alle Ordner"}), 400

        try:
            uid = int(uid)
        except (TypeError, ValueError):
            return jsonify({"error": "uid ungültig"}), 400

        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
                models.MailAccount.auth_type == "imap",
            )
            .first()
        )
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        fetcher = None
        try:
            fetcher = _get_imap_fetcher(account, master_key)
            fetcher.connect()
            if not fetcher.connection:
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500
            text = FolderAuditService.peek_text(fetcher, str(folder), uid)
            return jsonify({"success": True, "text": text or "(kein Textteil)"})
        except Exception as e:
            logger.exception("Folder-audit preview error: %s", e)
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
        finally:
            if fetcher:
                fetcher.disconnect()
