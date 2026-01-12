# src/blueprints/tags.py
"""Tags Blueprint - Tag-Management-Seiten.

Routes (2 total):
    1. /tags (GET) - Tag-Management-Seite
    2. /tag-suggestions (GET) - Tag-Vorschläge-Seite

Extracted from 01_web_app.py lines: 2725-2769, 3311-3340
"""

from flask import Blueprint, render_template, redirect, url_for, g, flash
from flask_login import login_required
import importlib
import logging

from src.helpers import get_db_session, get_current_user_model

tags_bp = Blueprint("tags", __name__)
logger = logging.getLogger(__name__)

# Lazy imports
_models = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


# =============================================================================
# Route 1: /tags (Zeile 2725-2769)
# =============================================================================
@tags_bp.route("/tags")
@login_required
def tags_view():
    """Tag-Management-Seite"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            # Lade TagManager dynamisch
            try:
                tag_manager_mod = importlib.import_module("src.services.tag_manager")
                TagManager = tag_manager_mod.TagManager
            except ImportError as e:
                logger.error(f"tags_view: TagManager konnte nicht geladen werden: {e}")
                flash("Tag-Manager nicht verfügbar", "warning")
                return render_template("tags.html", user=user, tags=[], csp_nonce=g.get("csp_nonce", ""))

            # Hole alle Tags des Users
            try:
                tags = TagManager.get_user_tags(db, user.id)
            except Exception as e:
                logger.error(f"tags_view: Fehler beim Laden der Tags: {type(e).__name__}: {e}")
                flash("Fehler beim Laden der Tags", "danger")
                return render_template("tags.html", user=user, tags=[], csp_nonce=g.get("csp_nonce", ""))

            # Zähle E-Mails pro Tag
            tags_with_counts = []
            try:
                for tag in tags:
                    email_count = (
                        db.query(models.EmailTagAssignment)
                        .filter(models.EmailTagAssignment.tag_id == tag.id)
                        .count()
                    )
                    tags_with_counts.append(
                        {
                            "id": tag.id,
                            "name": tag.name,
                            "color": tag.color,
                            "description": tag.description,
                            "email_count": email_count,
                        }
                    )
            except Exception as e:
                logger.error(f"tags_view: Fehler beim Zählen der Emails: {type(e).__name__}: {e}")
                # Fallback: Tags ohne Counts anzeigen
                tags_with_counts = [
                    {
                        "id": tag.id,
                        "name": tag.name,
                        "color": tag.color,
                        "description": tag.description,
                        "email_count": 0,
                    }
                    for tag in tags
                ]
                flash("Email-Zählung fehlgeschlagen", "warning")

            return render_template(
                "tags.html", user=user, tags=tags_with_counts, csp_nonce=g.get("csp_nonce", "")
            )
    except Exception as e:
        logger.error(f"tags_view: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Fehler beim Laden der Tag-Seite", "danger")
        return redirect(url_for("index"))


# =============================================================================
# Route 2: /tag-suggestions (Zeile 3311-3340)
# =============================================================================
@tags_bp.route("/tag-suggestions")
@login_required
def tag_suggestions_page():
    """UI: Tag-Vorschläge Seite"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            # Lade Services dynamisch mit Exception Handling
            try:
                suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
                tag_manager_mod = importlib.import_module("src.services.tag_manager")
            except ImportError as e:
                logger.error(f"tag_suggestions_page: Service-Import fehlgeschlagen: {e}")
                flash("Tag-Services nicht verfügbar", "danger")
                return redirect(url_for("tags.tags_view"))

            # Holt pending Vorschläge + User-Tags mit Exception Handling
            try:
                suggestions = suggestion_mod.TagSuggestionService.get_pending_suggestions(db, user.id)
            except Exception as e:
                logger.error(f"tag_suggestions_page: Fehler bei get_pending_suggestions: {type(e).__name__}: {e}")
                suggestions = []
                flash("Fehler beim Laden der Vorschläge", "warning")

            try:
                user_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
            except Exception as e:
                logger.error(f"tag_suggestions_page: Fehler bei get_user_tags: {type(e).__name__}: {e}")
                user_tags = []

            try:
                stats = suggestion_mod.TagSuggestionService.get_suggestion_stats(db, user.id)
            except Exception as e:
                logger.error(f"tag_suggestions_page: Fehler bei get_suggestion_stats: {type(e).__name__}: {e}")
                stats = {"pending": 0, "approved": 0, "rejected": 0}

            return render_template(
                "tag_suggestions.html",
                suggestions=suggestions,
                user_tags=user_tags,
                stats=stats,
                queue_enabled=getattr(user, 'enable_tag_suggestion_queue', False),
                auto_assignment_enabled=getattr(user, 'enable_auto_assignment', False),
                csp_nonce=g.get("csp_nonce", "")
            )
    except Exception as e:
        logger.error(f"tag_suggestions_page: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Fehler beim Laden der Tag-Vorschläge", "danger")
        return redirect(url_for("index"))

