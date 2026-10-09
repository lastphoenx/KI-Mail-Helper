"""HMAC neben einer Klassifikator-Datei.

Gleiche Rechnung wie beim Laden: Dateiinhalt, SHA-256, Hex in ``pfad.sig``.
Ohne CLASSIFIER_HMAC_KEY bleibt die Datei unsigniert. Das Laden verlangt
die Signatur nur, wenn der Schlüssel gesetzt ist.
"""
import hashlib
import hmac
import os
from pathlib import Path


def sign_classifier_file(path) -> bool:
    """Schreibt die Signatur, wenn der Schlüssel gesetzt ist."""
    key = os.getenv("CLASSIFIER_HMAC_KEY", "").encode()
    if not key:
        return False
    model_path = Path(path)
    digest = hmac.new(key, model_path.read_bytes(), hashlib.sha256).hexdigest()
    Path(str(model_path) + ".sig").write_text(digest + "\n", encoding="ascii")
    return True
