"""
Folder Audit Blueprint - Papierkorb-Analyse und Aufräum-Tool

Endpoints:
    GET  /folder-audit         - Haupt-UI für Folder-Audit
    POST /folder-audit/scan    - Startet Scan des Papierkorbs
    POST /folder-audit/delete  - Löscht ausgewählte Emails permanent
"""

import logging
from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required
import importlib

from src.helpers import get_db_session, get_current_user_model
from src.services.folder_audit_service import FolderAuditService, TrashCategory

logger = logging.getLogger(__name__)

folder_audit_bp = Blueprint("folder_audit", __name__)


# =============================================================================
# Lazy Imports (wie in anderen Blueprints)
# =============================================================================

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
    encryption = _get_encryption()
    mail_fetcher_mod = _get_mail_fetcher_mod()
    
    imap_server = encryption.CredentialManager.decrypt_server(
        account.encrypted_imap_server, master_key
    )
    imap_username = encryption.CredentialManager.decrypt_email_address(
        account.encrypted_imap_username, master_key
    )
    imap_password = encryption.CredentialManager.decrypt_imap_password(
        account.encrypted_imap_password, master_key
    )
    
    fetcher = mail_fetcher_mod.MailFetcher(
        server=imap_server,
        username=imap_username,
        password=imap_password,
        port=account.imap_port,
    )
    return fetcher


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


@folder_audit_bp.route("/folder-audit/scan", methods=["POST"])
@login_required
def scan_trash():
    """Scannt Ordner und kategorisiert Emails"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich. Bitte neu einloggen."}), 401
        
        data = request.get_json() or {}
        account_id = data.get("account_id")
        limit = data.get("limit", 5000)
        folder = data.get("folder")  # Optional: spezifischer Ordner
        
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
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
            
            # "Alle Ordner" oder einzelner Ordner?
            if folder == "__ALL__":
                # Alle Ordner scannen
                # Pro Ordner bis zu 2000 Emails, aber Gesamt-Limit aus UI
                result = FolderAuditService.fetch_and_analyze_all_folders(
                    fetcher,
                    limit_per_folder=2000,
                    max_total=limit,  # User-Limit als Gesamt-Limit
                    db_session=db,
                    user_id=user.id,
                    account_id=account.id,
                )
                scan_folder = "Alle Ordner"
            else:
                # Einzelner Ordner
                result = FolderAuditService.fetch_and_analyze_trash(
                    fetcher, 
                    limit, 
                    db_session=db, 
                    user_id=user.id,
                    account_id=account.id,
                    folder=folder
                )
                scan_folder = folder or "Trash"
            
            return jsonify({
                "success": True,
                "result": result.to_dict(),
                "folder": scan_folder,
            })
            
        except Exception as e:
            logger.error(f"Trash scan error: {type(e).__name__}: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            if fetcher:
                fetcher.disconnect()


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
        folder = data.get("folder")  # Optional: spezifischer Ordner
        
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        if not uids:
            return jsonify({"error": "Keine UIDs angegeben"}), 400
        
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
