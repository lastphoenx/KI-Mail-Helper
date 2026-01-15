# src/blueprints/rules.py
"""Rules Blueprint - Auto-Rules Management.

Routes (10 total):
    1. /rules (GET) - Rules Management Page
    2. /api/rules (GET) - API: Alle Regeln abrufen
    3. /api/rules (POST) - API: Neue Regel erstellen
    4. /api/rules/<id> (PUT) - API: Regel aktualisieren
    5. /api/rules/<id> (DELETE) - API: Regel löschen
    6. /api/rules/<id>/test (POST) - API: Regel testen (Dry-Run)
    7. /api/rules/apply (POST) - API: Regeln anwenden
    8. /api/rules/templates (GET) - API: Templates abrufen
    9. /api/rules/templates/<name> (POST) - API: Regel aus Template
    10. /rules/execution-log (GET) - Execution Log Page

Extracted from 01_web_app.py lines: 4881-5470

HINWEIS: rules_bp hat KEINEN Prefix. Die /api/rules Routes behalten ihren vollen Pfad!
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, g, flash
from flask_login import login_required
import importlib
import logging

from src.helpers import get_db_session, get_current_user_model

rules_bp = Blueprint("rules", __name__)
logger = logging.getLogger(__name__)

# Lazy imports
_models = None
_encryption = None


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


# =============================================================================
# Route 1: /rules (Zeile 4881-4906)
# =============================================================================
@rules_bp.route("/rules")
@login_required
def rules_management():
    """Rules Management Page - Übersicht über alle Auto-Rules"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))
            
            try:
                rules = db.query(models.AutoRule).filter_by(
                    user_id=user.id
                ).order_by(models.AutoRule.priority.asc()).all()
            except Exception as e:
                logger.error(f"rules_management: DB-Fehler bei Regel-Abfrage: {type(e).__name__}: {e}")
                rules = []
                flash("Fehler beim Laden der Regeln", "warning")
            
            return render_template(
                "rules_management.html",
                user=user,
                rules=rules
            )
    except Exception as e:
        logger.error(f"rules_management: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Fehler beim Laden der Regeln-Seite", "danger")
        return redirect(url_for("emails.dashboard"))


# =============================================================================
# Route 2: /api/rules GET (Zeile 4908-4943)
# =============================================================================
@rules_bp.route("/api/rules", methods=["GET"])
@login_required
def api_get_rules():
    """API: Alle Regeln des Users abrufen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rules = db.query(models.AutoRule).filter_by(
                user_id=user.id
            ).order_by(models.AutoRule.priority.asc()).all()
            
            return jsonify({
                "rules": [
                    {
                        "id": rule.id,
                        "name": rule.name,
                        "description": rule.description,
                        "is_active": rule.is_active,
                        "priority": rule.priority,
                        "conditions": rule.conditions,
                        "actions": rule.actions,
                        "times_triggered": rule.times_triggered,
                        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                        "created_at": rule.created_at.isoformat() if rule.created_at else None
                    }
                    for rule in rules
                ]
            }), 200
    except Exception as e:
        logger.error(f"api_get_rules: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 3: /api/rules POST (Zeile 4945-5008)
# =============================================================================
@rules_bp.route("/api/rules", methods=["POST"])
@login_required
def api_create_rule():
    """API: Neue Regel erstellen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            data = request.get_json()
            if not data:
                return jsonify({"error": "JSON-Daten erforderlich"}), 400
            
            name = data.get("name", "").strip()
            if not name:
                return jsonify({"error": "Name erforderlich"}), 400
            
            if len(name) > 100:
                return jsonify({"error": "Name zu lang (max. 100 Zeichen)"}), 400
            
            conditions = data.get("conditions", {})
            actions = data.get("actions", {})
            
            if not conditions:
                return jsonify({"error": "Mindestens eine Bedingung erforderlich"}), 400
            
            if not actions:
                return jsonify({"error": "Mindestens eine Aktion erforderlich"}), 400
            
            rule = models.AutoRule(
                user_id=user.id,
                name=name,
                description=data.get("description"),
                priority=data.get("priority", 100),
                is_active=data.get("is_active", True),
                conditions=conditions,
                actions=actions
            )
            
            db.add(rule)
            
            try:
                db.commit()
                logger.info(f"✅ Regel erstellt: '{rule.name}' (ID: {rule.id}) für User {user.id}")
                
                return jsonify({
                    "success": True,
                    "rule": {
                        "id": rule.id,
                        "name": rule.name,
                        "description": rule.description,
                        "is_active": rule.is_active,
                        "priority": rule.priority,
                        "conditions": rule.conditions,
                        "actions": rule.actions
                    }
                }), 201
            except Exception as e:
                db.rollback()
                logger.error(f"api_create_rule: Commit-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Speichern der Regel"}), 500
    except Exception as e:
        logger.error(f"api_create_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 4: /api/rules/<id> PUT (Zeile 5010-5069)
# =============================================================================
@rules_bp.route("/api/rules/<int:rule_id>", methods=["PUT"])
@login_required
def api_update_rule(rule_id):
    """API: Regel aktualisieren"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rule = db.query(models.AutoRule).filter_by(
                id=rule_id,
                user_id=user.id
            ).first()
            
            if not rule:
                return jsonify({"error": "Regel nicht gefunden"}), 404
            
            data = request.get_json()
            if not data:
                return jsonify({"error": "JSON-Daten erforderlich"}), 400
            
            if "name" in data:
                name = data["name"].strip()
                if len(name) > 100:
                    return jsonify({"error": "Name zu lang (max. 100 Zeichen)"}), 400
                rule.name = name
            if "description" in data:
                rule.description = data["description"]
            if "is_active" in data:
                rule.is_active = bool(data["is_active"])
            if "priority" in data:
                rule.priority = int(data["priority"])
            if "conditions" in data:
                rule.conditions = data["conditions"]
            if "actions" in data:
                rule.actions = data["actions"]
            
            try:
                db.commit()
                logger.info(f"✅ Regel aktualisiert: '{rule.name}' (ID: {rule.id})")
                
                return jsonify({
                    "success": True,
                    "rule": {
                        "id": rule.id,
                        "name": rule.name,
                        "description": rule.description,
                        "is_active": rule.is_active,
                        "priority": rule.priority,
                        "conditions": rule.conditions,
                        "actions": rule.actions
                    }
                }), 200
            except Exception as e:
                db.rollback()
                logger.error(f"api_update_rule: Commit-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Aktualisieren der Regel"}), 500
    except Exception as e:
        logger.error(f"api_update_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 5: /api/rules/<id> DELETE (Zeile 5071-5105)
# =============================================================================
@rules_bp.route("/api/rules/<int:rule_id>", methods=["DELETE"])
@login_required
def api_delete_rule(rule_id):
    """API: Regel löschen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rule = db.query(models.AutoRule).filter_by(
                id=rule_id,
                user_id=user.id
            ).first()
            
            if not rule:
                return jsonify({"error": "Regel nicht gefunden"}), 404
            
            rule_name = rule.name
            db.delete(rule)
            
            try:
                db.commit()
                logger.info(f"🗑️  Regel gelöscht: '{rule_name}' (ID: {rule_id})")
                return jsonify({"success": True}), 200
            except Exception as e:
                db.rollback()
                logger.error(f"api_delete_rule: Commit-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Löschen der Regel"}), 500
    except Exception as e:
        logger.error(f"api_delete_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 6: /api/rules/<id>/test (Zeile 5107-5205)
# =============================================================================
@rules_bp.route("/api/rules/<int:rule_id>/test", methods=["POST"])
@login_required
def api_test_rule(rule_id):
    """API: Regel auf E-Mail testen (Dry-Run)"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rule = db.query(models.AutoRule).filter_by(
                id=rule_id,
                user_id=user.id
            ).first()
            
            if not rule:
                return jsonify({"error": "Regel nicht gefunden"}), 404
            
            data = request.get_json() or {}
            email_id = data.get("email_id")
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            try:
                from src.auto_rules_engine import AutoRulesEngine
                engine = AutoRulesEngine(user.id, master_key, db)
                
                matches = []
                
                if email_id:
                    results = engine.process_email(email_id, dry_run=True, rule_id=rule_id)
                    
                    for result in results:
                        matches.append({
                            "email_id": result.email_id,
                            "matched": result.success,
                            "actions_would_execute": result.actions_executed
                        })
                else:
                    recent_emails = db.query(models.RawEmail).filter_by(
                        user_id=user.id,
                        deleted_at=None
                    ).order_by(models.RawEmail.received_at.desc()).limit(20).all()
                    
                    for email in recent_emails:
                        results = engine.process_email(email.id, dry_run=True, rule_id=rule_id)
                        
                        if results and results[0].success:
                            matches.append({
                                "email_id": email.id,
                                "matched": True,
                                "actions_would_execute": results[0].actions_executed
                            })
                
                logger.info(f"🧪 Regel '{rule.name}' getestet: {len(matches)} Matches")
                
                return jsonify({
                    "success": True,
                    "matches": matches,
                    "total_tested": 1 if email_id else 20,
                    "total_matches": len(matches),
                    "rule_name": rule.name
                }), 200
                
            except ImportError as e:
                logger.error(f"api_test_rule: AutoRulesEngine Import-Fehler: {e}")
                return jsonify({"error": "Regel-Engine nicht verfügbar"}), 500
            except Exception as e:
                logger.error(f"api_test_rule: Engine-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Testen der Regel"}), 500
    except Exception as e:
        logger.error(f"api_test_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 7: /api/rules/apply (Zeile 5207-5295)
# =============================================================================
@rules_bp.route("/api/rules/apply", methods=["POST"])
@login_required
def api_apply_rules():
    """API: Regeln manuell auf E-Mails anwenden (Celery + Legacy Dual-Mode)"""
    import os
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            data = request.get_json() or {}
            email_ids = data.get("email_ids", [])
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            # ═══════════════════════════════════════════════════════════
            # DUAL-MODE: Celery (Multi-User) vs Legacy
            # ═══════════════════════════════════════════════════════════
            use_legacy = os.getenv("USE_LEGACY_JOBS", "false").lower() == "true"
            
            if use_legacy:
                # ─────────────────────────────────────────────────────
                # LEGACY MODE: Synchrone Ausführung
                # ─────────────────────────────────────────────────────
                logger.info("🔧 [LEGACY] Applying rules synchronously")
                
                try:
                    from src.auto_rules_engine import AutoRulesEngine
                    engine = AutoRulesEngine(user.id, master_key, db)
                    
                    stats = {
                        "emails_processed": 0,
                        "rules_triggered": 0,
                        "actions_executed": 0,
                        "errors": 0
                    }
                    
                    if email_ids:
                        for email_id in email_ids:
                            try:
                                results = engine.process_email(email_id, dry_run=False)
                                
                                for result in results:
                                    if result.success:
                                        stats["rules_triggered"] += 1
                                        stats["actions_executed"] += len(result.actions_executed)
                                    else:
                                        stats["errors"] += 1
                                
                                stats["emails_processed"] += 1
                                
                            except Exception as e:
                                logger.error(f"api_apply_rules: Fehler bei E-Mail {email_id}: {type(e).__name__}: {e}")
                                stats["errors"] += 1
                    else:
                        batch_stats = engine.process_new_emails(since_minutes=10080, limit=500)
                        stats.update(batch_stats)
                        stats["emails_processed"] = batch_stats.get("emails_checked", 0)
                    
                    logger.info(
                        f"✅ [LEGACY] Auto-Rules angewendet: {stats['emails_processed']} E-Mails, "
                        f"{stats['rules_triggered']} Regeln ausgelöst"
                    )
                    
                    return jsonify({
                        "success": True,
                        "stats": stats,
                        "mode": "legacy"
                    }), 200
                    
                except ImportError as e:
                    logger.error(f"api_apply_rules: AutoRulesEngine Import-Fehler: {e}")
                    return jsonify({"error": "Regel-Engine nicht verfügbar"}), 500
                except Exception as e:
                    logger.error(f"api_apply_rules: Engine-Fehler: {type(e).__name__}: {e}")
                    return jsonify({"error": "Fehler beim Anwenden der Regeln"}), 500
            
            else:
                # ─────────────────────────────────────────────────────
                # CELERY MODE: Asynchrone Task-Queue
                # ─────────────────────────────────────────────────────
                logger.info("🚀 [CELERY] Applying rules asynchronously")
                
                try:
                    import importlib
                    from src.tasks.rule_execution_tasks import (
                        apply_rules_to_emails,
                        apply_rules_to_new_emails
                    )
                    auth = importlib.import_module(".07_auth", "src")
                    ServiceTokenManager = auth.ServiceTokenManager
                    
                    # Phase 2 Security: ServiceToken erstellen (DEK nicht in Redis!)
                    with get_db_session() as token_db:
                        _, service_token = ServiceTokenManager.create_token(
                            user_id=user.id,
                            master_key=master_key,
                            session=token_db,
                            days=1  # Rule-Token nur 1 Tag gültig
                        )
                        service_token_id = service_token.id
                    
                    if email_ids:
                        # Spezifische E-Mails
                        task = apply_rules_to_emails.delay(
                            user_id=user.id,
                            email_ids=email_ids,
                            service_token_id=service_token_id,
                            dry_run=False
                        )
                        
                        logger.info(f"✅ [CELERY] Rule task enqueued: {task.id}")
                        
                        return jsonify({
                            "success": True,
                            "task_id": task.id,
                            "status": "processing",
                            "message": f"Regeln werden auf {len(email_ids)} E-Mails angewendet",
                            "mode": "celery"
                        }), 202  # Accepted
                        
                    else:
                        # Batch: Alle neuen E-Mails
                        task = apply_rules_to_new_emails.delay(
                            user_id=user.id,
                            service_token_id=service_token_id,
                            since_minutes=10080,  # 7 days
                            limit=500
                        )
                        
                        logger.info(f"✅ [CELERY] Batch rule task enqueued: {task.id}")
                        
                        return jsonify({
                            "success": True,
                            "task_id": task.id,
                            "status": "processing",
                            "message": "Regeln werden auf neue E-Mails angewendet",
                            "mode": "celery"
                        }), 202  # Accepted
                        
                except ImportError as e:
                    logger.error(f"api_apply_rules: Task Import-Fehler: {e}")
                    return jsonify({"error": "Rule-Tasks nicht verfügbar"}), 500
                except Exception as e:
                    logger.error(f"api_apply_rules: Celery-Fehler: {type(e).__name__}: {e}")
                    return jsonify({"error": "Fehler beim Enqueuen der Rule-Tasks"}), 500
                    
    except Exception as e:
        logger.error(f"api_apply_rules: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 7b: /api/rules/task_status/<task_id> GET (Celery Task Status)
# =============================================================================
@rules_bp.route("/api/rules/task_status/<task_id>", methods=["GET"])
@login_required
def api_rule_task_status(task_id: str):
    """API: Celery Task Status für Rule-Execution abfragen"""
    import os
    
    use_legacy = os.getenv("USE_LEGACY_JOBS", "false").lower() == "true"
    
    if use_legacy:
        return jsonify({"error": "Task-Status nur im Celery-Modus verfügbar"}), 400
    
    try:
        from src.celery_app import celery_app
        from celery.result import AsyncResult
        
        task = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "state": task.state,
            "ready": task.ready(),
            "successful": task.successful() if task.ready() else None
        }
        
        if task.ready():
            if task.successful():
                result = task.result
                response["result"] = result
                response["message"] = "Task completed successfully"
            elif task.failed():
                response["error"] = str(task.info)
                response["message"] = "Task failed"
        else:
            response["message"] = "Task is still processing"
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error fetching task status: {e}")
        return jsonify({"error": "Could not fetch task status"}), 500


# =============================================================================
# Route 8: /api/rules/templates GET (Zeile 5297-5321)
# =============================================================================
@rules_bp.route("/api/rules/templates", methods=["GET"])
@login_required
def api_get_rule_templates():
    """API: Vordefinierte Regel-Templates abrufen"""
    try:
        # User Validation (auch wenn nur Templates geladen werden)
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
        
        try:
            from src.auto_rules_engine import RULE_TEMPLATES
            
            return jsonify({
                "templates": [
                    {
                        "id": key,
                        "name": template["name"],
                        "description": template["description"],
                        "priority": template.get("priority", 100),
                        "conditions": template["conditions"],
                        "actions": template["actions"]
                    }
                    for key, template in RULE_TEMPLATES.items()
                ]
            }), 200
        except ImportError as e:
            logger.error(f"api_get_rule_templates: Import-Fehler: {e}")
            return jsonify({"templates": [], "error": "Templates nicht verfügbar"}), 200
    except Exception as e:
        logger.error(f"api_get_rule_templates: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 9: /api/rules/templates/<name> POST (Zeile 5323-5380)
# =============================================================================
@rules_bp.route("/api/rules/templates/<template_name>", methods=["POST"])
@login_required
def api_create_rule_from_template(template_name):
    """API: Regel aus Template erstellen"""
    # Validate template_name
    if not template_name or len(template_name) > 50:
        return jsonify({"error": "Ungültiger Template-Name"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            data = request.get_json() or {}
            overrides = data.get("overrides", {})
            
            try:
                from src.auto_rules_engine import create_rule_from_template
                
                rule = create_rule_from_template(
                    db_session=db,
                    user_id=user.id,
                    template_name=template_name,
                    overrides=overrides
                )
                
                if not rule:
                    return jsonify({"error": "Template nicht gefunden"}), 404
                
                logger.info(f"✅ Regel aus Template '{template_name}' erstellt: {rule.name} (ID: {rule.id})")
                
                return jsonify({
                    "success": True,
                    "rule": {
                        "id": rule.id,
                        "name": rule.name,
                        "description": rule.description,
                        "is_active": rule.is_active,
                        "priority": rule.priority,
                        "conditions": rule.conditions,
                        "actions": rule.actions
                    }
                }), 201
                
            except ImportError as e:
                logger.error(f"api_create_rule_from_template: Import-Fehler: {e}")
                return jsonify({"error": "Template-Engine nicht verfügbar"}), 500
            except Exception as e:
                db.rollback()
                logger.error(f"api_create_rule_from_template: Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Erstellen der Regel aus Template"}), 500
    except Exception as e:
        logger.error(f"api_create_rule_from_template: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 10: /rules/execution-log (Zeile 5382-5470)
# =============================================================================
@rules_bp.route("/rules/execution-log")
@login_required
def rules_execution_log():
    """Zeigt Verlauf aller Regel-Ausführungen für Debugging und Monitoring"""
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))
            
            # Validate and sanitize inputs
            try:
                limit = min(int(request.args.get('limit', 100)), 500)  # Cap at 500
            except (ValueError, TypeError):
                limit = 100
            
            rule_id = request.args.get('rule_id')
            success_filter = request.args.get('success')
            
            try:
                query = db.query(
                    models.RuleExecutionLog,
                    models.AutoRule,
                    models.ProcessedEmail,
                    models.RawEmail
                ).join(
                    models.AutoRule,
                    models.RuleExecutionLog.rule_id == models.AutoRule.id
                ).join(
                    models.ProcessedEmail,
                    models.RuleExecutionLog.processed_email_id == models.ProcessedEmail.id
                ).join(
                    models.RawEmail,
                    models.ProcessedEmail.raw_email_id == models.RawEmail.id
                ).filter(
                    models.RuleExecutionLog.user_id == user.id
                )
                
                if rule_id:
                    try:
                        query = query.filter(models.RuleExecutionLog.rule_id == int(rule_id))
                    except (ValueError, TypeError):
                        pass  # Ignoriere ungültige rule_id
                
                if success_filter == 'true':
                    query = query.filter(models.RuleExecutionLog.success == True)
                elif success_filter == 'false':
                    query = query.filter(models.RuleExecutionLog.success == False)
                
                logs = query.order_by(
                    models.RuleExecutionLog.executed_at.desc()
                ).limit(limit).all()
                
                all_rules = db.query(models.AutoRule).filter_by(
                    user_id=user.id
                ).order_by(models.AutoRule.name.asc()).all()
            except Exception as e:
                logger.error(f"rules_execution_log: DB-Fehler: {type(e).__name__}: {e}")
                logs = []
                all_rules = []
                flash("Fehler beim Laden der Logs", "warning")
            
            master_key = session.get("master_key")
            decrypted_logs = []
            
            if master_key and logs:
                for log, rule, processed, raw in logs:
                    try:
                        subject = encryption.EmailDataManager.decrypt_email_subject(
                            raw.encrypted_subject or "", master_key
                        )
                    except Exception as e:
                        logger.warning(f"rules_execution_log: Entschlüsselung fehlgeschlagen: {type(e).__name__}")
                        subject = "(Entschlüsselung fehlgeschlagen)"
                    
                    decrypted_logs.append({
                        'log': log,
                        'rule': rule,
                        'subject': subject,
                        'email_id': raw.id
                    })
            
            return render_template(
                "rules_execution_log.html",
                user=user,
                logs=decrypted_logs,
                all_rules=all_rules,
                limit=limit,
                rule_id=rule_id,
                success_filter=success_filter
            )
    except Exception as e:
        logger.error(f"rules_execution_log: Fehler: {type(e).__name__}: {e}")
        flash("Fehler beim Laden des Execution-Logs", "danger")
        return redirect(url_for("rules.rules_management"))
