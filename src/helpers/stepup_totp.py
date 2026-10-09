"""Frischer TOTP-Code für einzelne POST-Aktionen.

Nach einer richtigen Eingabe, und direkt nach dem Login, gilt die Freigabe
einige Minuten. Dieselbe Kennung zählt nicht noch einmal. Ein falscher Code
erhöht denselben Zähler wie der Login.
"""
import importlib
import logging
import time

from flask import request, session

logger = logging.getLogger(__name__)

STEPUP_SECONDS = 300
SESSION_KEY = "totp_stepup_until"

_SECRET_FIELDS = {
    "imap_password",
    "smtp_password",
    "client_secret",
    "password",
    "totp_code",
    "csrf_token",
}


def mark_stepup_fresh() -> None:
    """Fenster neu öffnen. Login und eine bestandene Prüfung rufen das auf."""
    session[SESSION_KEY] = time.time() + STEPUP_SECONDS
    session.modified = True


def stepup_is_fresh() -> bool:
    raw = session.get(SESSION_KEY)
    try:
        return float(raw) > time.time()
    except (TypeError, ValueError):
        return False


def posted_public_fields() -> dict:
    """Formulardaten ohne Geheimnisse, zum erneuten Zeichnen der Seite."""
    return {
        key: value
        for key, value in request.form.items()
        if key not in _SECRET_FIELDS
    }


def stepup_error_text(reason, secrets_cleared=False, cleared_hint="Passwort bitte erneut eingeben.") -> str:
    if reason == "locked":
        text = "Konto vorübergehend gesperrt."
    elif reason == "missing":
        text = "Aktueller 2FA-Code erforderlich."
    else:
        text = "Ungültiger Code."
    if secrets_cleared and reason != "locked":
        text += " " + cleared_hint
    return text


def _submitted_code() -> str:
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        raw = payload.get("totp_code", "")
    else:
        raw = request.form.get("totp_code", "")
    return str(raw or "").strip().replace(" ", "")


def require_stepup(user, db):
    """None, wenn die Aktion weiterlaufen darf.

    Sonst ``locked``, ``missing`` oder ``invalid``.
    ``invalid`` schreibt ``record_failed_login`` und schließt das Fenster.
    """
    if user.is_locked():
        session.pop(SESSION_KEY, None)
        return "locked"
    if stepup_is_fresh():
        return None

    token = _submitted_code()
    if not token:
        return "missing"

    auth = importlib.import_module(".07_auth", "src")
    accepted = auth.AuthManager.matching_totp_step(
        user.totp_secret, token, user.last_totp_step
    )
    if accepted is None:
        session.pop(SESSION_KEY, None)
        try:
            user.record_failed_login(db)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("SECURITY[STEPUP]: Fehlversuch nicht gespeichert")
        logger.warning(
            "SECURITY[STEPUP_FAILED]: user_id=%s attempts=%s",
            user.id,
            user.failed_login_attempts,
        )
        return "invalid"

    try:
        user.last_totp_step = accepted
        user.reset_failed_logins(db)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("SECURITY[STEPUP]: Schritt nicht gespeichert")
        return "invalid"
    mark_stepup_fresh()
    return None
