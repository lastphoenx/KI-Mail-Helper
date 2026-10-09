"""Neue Datei-Session nach dem Login.

Die Kennung im Cookie bleibt sonst vor und nach der Anmeldung gleich.
Wer sie vorher kennt, wäre mit angemeldet.
"""
from flask import current_app, session


def rotate_server_session() -> None:
    """Alte Datei weg, neue Kennung. Die Daten in der Session bleiben."""
    current_app.session_interface.regenerate(session)
