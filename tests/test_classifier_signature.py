"""Signatur direkt nach dem Speichern, gleiche Rechnung wie beim Laden."""
import hashlib
import hmac
from pathlib import Path

from src.helpers.classifier_signature import sign_classifier_file


def test_sign_writes_the_digest_the_loader_expects(tmp_path, monkeypatch):
    monkeypatch.setenv("CLASSIFIER_HMAC_KEY", "example-classifier-key")
    model = tmp_path / "spam_clf.pkl"
    model.write_bytes(b"not-a-real-model")
    assert sign_classifier_file(model) is True
    sig = Path(str(model) + ".sig").read_text(encoding="ascii").strip()
    expected = hmac.new(
        b"example-classifier-key", model.read_bytes(), hashlib.sha256
    ).hexdigest()
    assert sig == expected


def test_sign_skips_when_the_key_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("CLASSIFIER_HMAC_KEY", raising=False)
    model = tmp_path / "spam_clf.pkl"
    model.write_bytes(b"not-a-real-model")
    assert sign_classifier_file(model) is False
    assert not Path(str(model) + ".sig").exists()
