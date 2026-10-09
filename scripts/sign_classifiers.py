"""Signiert Klassifikator-Dateien, wenn CLASSIFIER_HMAC_KEY gesetzt ist.

Schreibt neben jede .pkl und .joblib eine Datei mit dem Suffix .sig.
Den Schlüssel gibt das Skript nicht aus. Ohne Schlüssel tut es nichts
und endet mit Fehler, damit ein leerer Lauf nicht wie Erfolg aussieht.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from pathlib import Path


def main() -> int:
    key = os.getenv("CLASSIFIER_HMAC_KEY", "").encode()
    if not key:
        print("CLASSIFIER_HMAC_KEY is unset", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent / "src" / "classifiers"
    if not root.is_dir():
        print(f"classifier dir missing: {root}", file=sys.stderr)
        return 1
    signed = 0
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".pkl", ".joblib"}:
            continue
        digest = hmac.new(key, path.read_bytes(), hashlib.sha256).hexdigest()
        sig = Path(str(path) + ".sig")
        sig.write_text(digest + "\n", encoding="ascii")
        signed += 1
    print(f"signed {signed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
