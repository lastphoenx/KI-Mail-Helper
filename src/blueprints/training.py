# src/blueprints/training.py
"""Training Blueprint - ML-Training für User-Korrektionen.

Routes (1 total):
    1. /retrain (POST) - Trainiert ML-Klassifikatoren
"""

from flask import Blueprint, jsonify
from flask_login import login_required, current_user
import logging

training_bp = Blueprint("training", __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Route 1: /retrain (Zeile 2249-2296)
# =============================================================================
@training_bp.route("/retrain", methods=["POST"])
@login_required
def retrain_models():
    """Trainiert ML-Klassifikatoren aus User-Korrektionen."""
    if not current_user:
        return jsonify({"error": "Nicht authentifiziert"}), 401

    try:
        from train_classifier import train_from_corrections

        trained_count = train_from_corrections()

        if trained_count == 0:
            return (
                jsonify(
                    {
                        "status": "no_data",
                        "message": "Keine ausreichenden Korrektionen zum Trainieren vorhanden. Mindestens 5 Korrektionen pro Klassifikator erforderlich.",
                        "trained": 0,
                    }
                ),
                200,
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"✅ {trained_count} Klassifikator(en) erfolgreich trainiert. System nutzt jetzt Ihre Feedback-Labels!",
                    "trained": trained_count,
                }
            ),
            200,
        )

    except ImportError:
        return (
            jsonify(
                {
                    "error": "scikit-learn nicht installiert. Bitte: pip install scikit-learn"
                }
            ),
            500,
        )

    except Exception as e:
        logger.error(f"Fehler beim Retraining: {type(e).__name__}")
        return jsonify({"error": "Retraining fehlgeschlagen"}), 500
