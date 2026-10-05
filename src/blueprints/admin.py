# src/blueprints/admin.py
"""Admin Blueprint - Admin-Funktionen.

Routes (1 total):
    1. /api/debug-logger-status (GET) - Debug-Logger-Status
"""

from flask import Blueprint, jsonify
from flask_login import login_required
import importlib
import logging

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Route 1: /api/debug-logger-status (Zeile 9412-9433)
# =============================================================================
@admin_bp.route("/api/debug-logger-status")
@login_required
def api_debug_logger_status():
    """API: Zeigt Status des Debug-Loggers (nur für Admins)"""
    try:
        debug_logger_mod = importlib.import_module("src.debug_logger")
        DebugLogger = debug_logger_mod.DebugLogger
    except ImportError:
        return jsonify({
            "enabled": False,
            "status": "Debug-Logger nicht verfügbar",
        }), 200
    
    status = DebugLogger.get_status()
    
    if status["enabled"]:
        return jsonify({
            "enabled": True,
            "warning": "⚠️ DEBUG-LOGGING IST AKTIV - Sensible Daten werden geloggt!",
            "log_dir": status["log_dir"],
            "log_files": status["log_files"],
            "hint": "Zum Deaktivieren: src/debug_logger.py → ENABLED = False"
        }), 200
    else:
        return jsonify({
            "enabled": False,
            "status": "✅ Debug-Logging ist deaktiviert",
            "hint": "Zum Aktivieren: src/debug_logger.py → ENABLED = True"
        }), 200
