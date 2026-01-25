# src/blueprints/email_actions.py
"""Email Actions Blueprint - CRUD-Operationen für Emails.

Routes (12 total):
    1. /email/<id>/done (POST) - als erledigt markieren
    2. /email/<id>/undo (POST) - erledigt rückgängig
    3. /email/<id>/reprocess (POST) - erneut verarbeiten
    4. /email/<id>/optimize (POST) - mit Optimize-Provider
    5. /email/<id>/correct (POST) - User-Korrektur speichern
    6. /email/<id>/delete (POST) - auf Server löschen
    7. /email/<id>/move-trash (POST) - in Papierkorb verschieben
    8. /email/<id>/move-to-folder (POST) - in Ordner verschieben
    9. /email/<id>/mark-read (POST) - als gelesen markieren
    10. /email/<id>/toggle-read (POST) - Lese-Status togglen
    11. /email/<id>/mark-flag (POST) - Flag togglen
    12. /emails/bulk-action (POST) - Massenbearbeitung (NEU)
"""

from flask import Blueprint, jsonify, request, redirect, url_for, session, flash
from flask_login import login_required, current_user
from datetime import datetime, UTC
import importlib
import logging

from src.helpers import get_db_session, get_current_user_model
from src.services.email_action_service import EmailActionService

email_actions_bp = Blueprint("email_actions", __name__)
logger = logging.getLogger(__name__)

# Lazy imports
_models = None
_encryption = None
_mail_fetcher_mod = None
_mail_sync = None


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


def _get_mail_sync():
    global _mail_sync
    if _mail_sync is None:
        _mail_sync = importlib.import_module(".16_mail_sync", "src")
    return _mail_sync


def _get_imap_fetcher(account, master_key):
    """Helper: Erstellt IMAP-Fetcher mit entschlüsselten Credentials.
    
    Returns:
        MailFetcher instance
    """
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
# Route 1: /email/<id>/done (Zeile 1794-1828)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/done", methods=["POST"])
@login_required
def mark_done(raw_email_id):
    """Markiert eine Mail als erledigt - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            flash("Benutzer nicht gefunden. Bitte neu anmelden.", "error")
            return redirect(url_for("auth.login"))
        
        result = EmailActionService.mark_done_single(db, user.id, raw_email_id)
        
        if result.success:
            logger.info(f"✅ Mail {raw_email_id} als erledigt markiert")
        else:
            flash(result.error or "E-Mail nicht gefunden.", "warning")
        
        return redirect(request.referrer or url_for("emails.list_view"))


# =============================================================================
# Route 2: /email/<id>/undo (Zeile 1830-1861)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/undo", methods=["POST"])
@login_required
def mark_undone(raw_email_id):
    """Macht 'erledigt'-Markierung rückgängig - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            flash("Benutzer nicht gefunden. Bitte neu anmelden.", "error")
            return redirect(url_for("auth.login"))
        
        result = EmailActionService.mark_undone_single(db, user.id, raw_email_id)
        
        if result.success:
            logger.info(f"↩️ Mail {raw_email_id} zurückgesetzt")
        else:
            flash(result.error or "E-Mail nicht gefunden.", "warning")
        
        return redirect(request.referrer or url_for("emails.list_view"))


# =============================================================================
# Route 3: /email/<id>/reprocess (Zeile 1863-1951)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/reprocess", methods=["POST"])
@login_required
def reprocess_email(raw_email_id):
    """Reprocessed eine Email - ASYNC via Celery"""
    models = _get_models()
    
    with get_db_session() as db:
        try:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Nicht authentifiziert"}), 401

            # Quick Ownership-Check (kein AI-Call hier!)
            raw_email = db.query(models.RawEmail).filter_by(
                id=raw_email_id,
                user_id=user.id
            ).first()
            
            if not raw_email:
                return jsonify({"error": "Email nicht gefunden"}), 404
            
            # Master-Key prüfen
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Session abgelaufen. Bitte neu einloggen."}), 401

            # ═══════════════════════════════════════════════════════════════
            # CELERY PATH (Standard) - Async Processing
            # ═══════════════════════════════════════════════════════════════
            import importlib
            from src.tasks.email_processing_tasks import reprocess_email_base
            auth = importlib.import_module(".07_auth", "src")
            ServiceTokenManager = auth.ServiceTokenManager
            
            try:
                # Phase 2 Security: ServiceToken erstellen
                _, service_token = ServiceTokenManager.create_token(
                    user_id=user.id,
                    master_key=master_key,
                    session=db,
                    days=1  # Reprocess-Token nur 1 Tag gültig
                )
                
                # Task starten (ASYNC!)
                task = reprocess_email_base.delay(
                    user_id=user.id,
                    raw_email_id=raw_email_id,
                    service_token_id=service_token.id
                )
                
                logger.info(f"✅ Reprocess Task {task.id} gequeued für Email {raw_email_id}")
                
                return jsonify({
                    "status": "queued",
                    "task_id": task.id,
                    "task_type": "celery",
                    "message": "Base-Lauf wird neu generiert..."
                })
                
            except Exception as e:
                logger.error(f"reprocess_email: Celery-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Starten des Reprocess-Tasks"}), 500

        except Exception as proc_err:
            db.rollback()
            logger.error(f"❌ Fehler bei Reprocessing von Email {raw_email_id}: {proc_err}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Verarbeitung fehlgeschlagen: {str(proc_err)}",
                    }
                ),
                500,
            )


# =============================================================================
# Route 4: /email/<id>/optimize (Zeile 1953-2098)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/optimize", methods=["POST"])
@login_required
def optimize_email(raw_email_id):
    """Triggert Optimize-Pass für Email - ASYNC via Celery"""
    models = _get_models()
    
    with get_db_session() as db:
        try:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Nicht authentifiziert"}), 401

            # Quick Ownership-Check (kein AI-Call hier!)
            raw_email = db.query(models.RawEmail).filter_by(
                id=raw_email_id,
                user_id=user.id
            ).first()
            
            if not raw_email:
                return jsonify({"error": "Email nicht gefunden"}), 404
            
            # Master-Key prüfen
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Session abgelaufen. Bitte neu einloggen."}), 401

            # ═══════════════════════════════════════════════════════════════
            # CELERY PATH (Standard) - Async Processing
            # ═══════════════════════════════════════════════════════════════
            import importlib
            from src.tasks.email_processing_tasks import optimize_email_processing
            auth = importlib.import_module(".07_auth", "src")
            ServiceTokenManager = auth.ServiceTokenManager
            
            try:
                # Phase 2 Security: ServiceToken erstellen
                _, service_token = ServiceTokenManager.create_token(
                    user_id=user.id,
                    master_key=master_key,
                    session=db,
                    days=1  # Optimize-Token nur 1 Tag gültig
                )
                
                # Task starten (ASYNC!)
                task = optimize_email_processing.delay(
                    user_id=user.id,
                    raw_email_id=raw_email_id,
                    service_token_id=service_token.id
                )
                
                logger.info(f"✅ Optimize Task {task.id} gequeued für Email {raw_email_id}")
                
                return jsonify({
                    "status": "queued",
                    "task_id": task.id,
                    "task_type": "celery",
                    "message": "Optimize-Lauf wird gestartet..."
                })
                
            except Exception as e:
                logger.error(f"optimize_email: Celery-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Starten des Optimize-Tasks"}), 500

        except Exception as proc_err:
            db.rollback()
            logger.error(f"❌ Fehler bei Optimize von Email {raw_email_id}: {proc_err}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Optimierung fehlgeschlagen: {str(proc_err)}",
                    }
                ),
                500,
            )


# =============================================================================
# Route 5: /email/<id>/correct (Zeile 2126-2195)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/correct", methods=["POST"])
@login_required
def correct_email(raw_email_id: int):
    """Speichert User-Korrektionen für eine Email (für Training)."""
    models = _get_models()
    
    with get_db_session() as db:
        try:
            user = db.query(models.User).filter(models.User.id == current_user.id).first()
            if not user:
                return jsonify({"error": "User nicht gefunden"}), 404

            email = (
                db.query(models.ProcessedEmail)
                .join(models.RawEmail)
                .filter(
                    models.RawEmail.id == raw_email_id,
                    models.RawEmail.user_id == user.id,
                )
                .first()
            )

            if not email:
                return jsonify({"error": "Email nicht gefunden"}), 404

            data = request.get_json() or {}
            
            # ===== Prüfe welche Werte sich WIRKLICH geändert haben =====
            # Nur echte Änderungen zählen als Korrektur (für Training)
            changed_fields = []
            
            new_d = data.get("dringlichkeit")
            if new_d is not None and new_d != email.user_override_dringlichkeit:
                email.user_override_dringlichkeit = new_d
                changed_fields.append("dringlichkeit")
            
            new_w = data.get("wichtigkeit")
            if new_w is not None and new_w != email.user_override_wichtigkeit:
                email.user_override_wichtigkeit = new_w
                changed_fields.append("wichtigkeit")
            
            new_k = data.get("kategorie")
            if new_k is not None and new_k != email.user_override_kategorie:
                email.user_override_kategorie = new_k
                changed_fields.append("kategorie")
            
            new_spam = data.get("spam_flag")
            if new_spam is not None and new_spam != email.user_override_spam_flag:
                email.user_override_spam_flag = new_spam
                changed_fields.append("spam")
            
            # Tags und Note immer überschreiben (kein Training-Trigger)
            email.user_override_tags = (
                ",".join(data.get("tags", [])) if data.get("tags") else None
            )
            email.encrypted_correction_note = data.get("note")
            
            # Nur bei echten Änderungen: Timestamps aktualisieren
            if changed_fields:
                email.correction_timestamp = datetime.now(UTC)
                email.updated_at = datetime.now(UTC)
                logger.debug(f"📝 Echte Korrekturen: {changed_fields}")
            
            # Score neu berechnen wenn D oder W korrigiert wurde
            if "dringlichkeit" in changed_fields or "wichtigkeit" in changed_fields:
                import importlib
                scoring = importlib.import_module("src.05_scoring")
                
                # Effektive Werte: Override wenn vorhanden, sonst Original
                eff_d = email.user_override_dringlichkeit if email.user_override_dringlichkeit is not None else email.dringlichkeit
                eff_w = email.user_override_wichtigkeit if email.user_override_wichtigkeit is not None else email.wichtigkeit
                
                if eff_d is not None and eff_w is not None:
                    new_score = scoring.calculate_score(eff_d, eff_w)
                    new_matrix = scoring.get_matrix_position(eff_d, eff_w)
                    new_color = scoring.get_color(new_score)
                    
                    email.score = new_score
                    email.matrix_x = new_matrix[0]
                    email.matrix_y = new_matrix[1]
                    email.farbe = new_color
                    logger.debug(f"📊 Score aktualisiert: {new_score} (D={eff_d}, W={eff_w})")

            db.commit()

            logger.info(f"✅ Mail {raw_email_id} korrigiert durch User {user.id}: {changed_fields if changed_fields else 'keine Änderungen'}")

            # Hybrid Score-Learning: Async Training triggern
            # NUR bei echten Änderungen! Throttling erfolgt zusätzlich im Task.
            if changed_fields:
                try:
                    from src.tasks.training_tasks import train_personal_classifier
                    
                    # Trigger NUR für geänderte Felder
                    for field in changed_fields:
                        train_personal_classifier.delay(user.id, field)
                    
                    logger.debug(f"🎓 Training getriggert für User {user.id}: {changed_fields}")
                except Exception as e:
                    # Training-Fehler sollte Korrektur nicht blockieren
                    logger.warning(f"⚠️ Training-Trigger fehlgeschlagen (non-blocking): {e}")

            return jsonify(
                {
                    "status": "success",
                    "message": "Korrektur gespeichert! Training wird im Hintergrund gestartet.",
                    "correction_count": db.query(models.ProcessedEmail)
                    .filter(models.ProcessedEmail.user_override_dringlichkeit != None)
                    .count(),
                    "training_triggered": True,
                }
            )

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Fehler bei correct_email für Email {raw_email_id}: {type(e).__name__}")
            return jsonify({"error": f"Korrektur fehlgeschlagen: {str(e)}"}), 500


# =============================================================================
# Route 6: /email/<id>/delete (Zeile 7527-7619)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/delete", methods=["POST"])
@login_required
def delete_email(raw_email_id):
    """Löscht eine Email auf dem Server - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        result = EmailActionService.delete_permanent_single(
            db, user.id, raw_email_id, master_key
        )
        
        if result.success:
            logger.info(f"✓ Email {raw_email_id} auf Server gelöscht")
            return jsonify({"success": True, "message": result.message})
        else:
            return jsonify({"error": result.error}), 500


# =============================================================================
# Route 7: /email/<id>/move-trash (Zeile 7621-7773)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/move-trash", methods=["POST"])
@login_required
def move_email_to_trash(raw_email_id):
    """Verschiebt eine Email in den Papierkorb auf dem Server - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        result = EmailActionService.move_to_trash_single(
            db, user.id, raw_email_id, master_key
        )
        
        if result.success:
            logger.info(f"✅ Email {raw_email_id} in Papierkorb verschoben")
            return jsonify({"success": True, "message": result.message})
        else:
            return jsonify({"error": result.error}), 500


# =============================================================================
# Route 8: /email/<id>/move-to-folder (Zeile 8031-8178)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/move-to-folder", methods=["POST"])
@login_required
def move_email_to_folder(raw_email_id):
    """Verschiebt eine Email in einen bestimmten Ordner - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        data = request.get_json() or {}
        target_folder = data.get("target_folder")
        if not target_folder:
            return jsonify({"error": "Ziel-Ordner erforderlich"}), 400
        
        result = EmailActionService.move_to_folder(
            db, user.id, raw_email_id, target_folder, master_key
        )
        
        if result.success:
            logger.info(f"✅ Email {raw_email_id} zu {target_folder} verschoben")
            return jsonify({"success": True, "message": result.message})
        else:
            return jsonify({"error": result.error}), 500


# =============================================================================
# Route 9: /email/<id>/mark-read (Zeile 8181-8272)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/mark-read", methods=["POST"])
@login_required
def mark_email_read(raw_email_id):
    """Markiert eine Email als gelesen auf dem Server - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        result = EmailActionService.mark_read(db, user.id, raw_email_id, master_key)
        
        if result.success:
            logger.info(f"✅ Email {raw_email_id} als gelesen markiert")
            return jsonify({"success": True, "message": result.message})
        else:
            return jsonify({"error": result.error}), 500


# =============================================================================
# Route 10: /email/<id>/toggle-read (Zeile 8274-8379)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/toggle-read", methods=["POST"])
@login_required
def toggle_email_read(raw_email_id):
    """Togglet Gelesen/Ungelesen Status einer Email - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        result = EmailActionService.toggle_read(db, user.id, raw_email_id, master_key)
        
        if result.success:
            # Parse is_seen state from message (format: "is_seen:True" or "is_seen:False")
            is_seen = result.message.endswith(":True")
            logger.info(f"✅ Email {raw_email_id} toggle-read: is_seen={is_seen}")
            return jsonify({"success": True, "message": result.message, "is_seen": is_seen})
        else:
            return jsonify({"error": result.error}), 500


# =============================================================================
# Route 11: /email/<id>/mark-flag (Zeile 8381-8478)
# =============================================================================
@email_actions_bp.route("/email/<int:raw_email_id>/mark-flag", methods=["POST"])
@login_required
def toggle_email_flag(raw_email_id):
    """Togglet Wichtig-Flag einer Email - nutzt EmailActionService"""
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401
        
        result = EmailActionService.toggle_flag(db, user.id, raw_email_id, master_key)
        
        if result.success:
            # Parse flagged state from message (format: "flagged:True" or "flagged:False")
            flagged = result.message.endswith(":True")
            logger.info(f"✅ Email {raw_email_id} toggle-flag: flagged={flagged}")
            return jsonify({"success": True, "message": result.message, "flagged": flagged})
        else:
            return jsonify({"error": result.error}), 500


# =============================================================================
# Route 12: /emails/bulk-action (NEU - Massenbearbeitung)
# =============================================================================
@email_actions_bp.route("/emails/bulk-action", methods=["POST"])
@login_required
def bulk_email_action():
    """Führt eine Aktion auf mehreren Emails gleichzeitig aus.
    
    Request Body:
        {
            "action": "mark_done" | "mark_undone" | "move_trash" | "delete_permanent",
            "email_ids": [1, 2, 3, ...]
        }
    
    Response:
        {
            "total": 3,
            "succeeded": 2,
            "failed": 1,
            "all_success": false,
            "partial_success": true,
            "results": [
                {"raw_email_id": 1, "success": true, "message": "OK"},
                {"raw_email_id": 2, "success": true, "message": "OK"},
                {"raw_email_id": 3, "success": false, "error": "IMAP-Fehler"}
            ]
        }
    """
    VALID_ACTIONS = ["mark_done", "mark_undone", "move_trash", "delete_permanent"]
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON-Body erforderlich"}), 400
        
        action = data.get("action")
        email_ids = data.get("email_ids", [])
        
        # Validierung
        if not action:
            return jsonify({"error": "action ist erforderlich"}), 400
        
        if action not in VALID_ACTIONS:
            return jsonify({
                "error": f"Ungültige Aktion '{action}'. Erlaubt: {VALID_ACTIONS}"
            }), 400
        
        if not email_ids or not isinstance(email_ids, list):
            return jsonify({"error": "email_ids muss eine nicht-leere Liste sein"}), 400
        
        # Limit für Bulk-Operationen (Sicherheit)
        MAX_BULK_SIZE = 100
        if len(email_ids) > MAX_BULK_SIZE:
            return jsonify({
                "error": f"Maximal {MAX_BULK_SIZE} Emails pro Bulk-Aktion erlaubt"
            }), 400
        
        # IDs validieren (müssen Integers sein)
        try:
            email_ids = [int(eid) for eid in email_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "email_ids müssen Integer-Werte sein"}), 400
        
        # Action ausführen
        logger.info(f"📦 Bulk-Action '{action}' für {len(email_ids)} Emails (User {user.id})")
        
        if action == "mark_done":
            result = EmailActionService.mark_done(db, user.id, email_ids)
        
        elif action == "mark_undone":
            result = EmailActionService.mark_undone(db, user.id, email_ids)
        
        elif action == "move_trash":
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key erforderlich. Bitte neu einloggen."}), 401
            result = EmailActionService.move_to_trash(db, user.id, email_ids, master_key)
        
        elif action == "delete_permanent":
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key erforderlich. Bitte neu einloggen."}), 401
            result = EmailActionService.delete_permanent(db, user.id, email_ids, master_key)
        
        else:
            # Sollte nicht passieren wegen VALID_ACTIONS check
            return jsonify({"error": f"Aktion '{action}' nicht implementiert"}), 501
        
        # Response
        logger.info(
            f"📦 Bulk-Action '{action}' abgeschlossen: "
            f"{result.succeeded}/{result.total} erfolgreich"
        )
        
        status_code = 200 if result.all_success else (207 if result.partial_success else 500)
        return jsonify(result.to_dict()), status_code
