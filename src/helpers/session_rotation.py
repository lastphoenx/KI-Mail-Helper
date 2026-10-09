"""Neue Datei-Session nach dem Login.

Die Kennung im Cookie bleibt sonst vor und nach der Anmeldung gleich.
Wer sie vorher kennt, wäre mit angemeldet.
"""
import logging
import secrets

from flask import current_app, session

logger = logging.getLogger(__name__)


def rotate_server_session() -> None:
    """Neue Session-Datei. Der alte Cookie zeigt danach ins Leere."""
    if not hasattr(session, "sid"):
        return
    kept = dict(session)
    interface = current_app.session_interface
    if session.sid and hasattr(interface, "delete_session"):
        try:
            interface.delete_session(current_app, session)
        except Exception:
            logger.warning("SECURITY[SESSION]: alte Session-Datei nicht geloescht")
    length = int(current_app.config.get("SESSION_ID_LENGTH") or 32)
    session.clear()
    session.sid = secrets.token_urlsafe(length)
    for key, value in kept.items():
        session[key] = value
    session.modified = True
