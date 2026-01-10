"""
Tests für E-Mail Sanitizer & Pseudonymisierung
"""

import sys
from pathlib import Path
import importlib

sys.path.insert(0, str(Path(__file__).parent.parent))

sanitizer = importlib.import_module('src.04_sanitizer')
sanitize_email = sanitizer.sanitize_email
get_sanitization_level = sanitizer.get_sanitization_level


def test_level_1_volltext():
    """Level 1 sollte nichts ändern"""
    original = "Test mit max@example.com und +49 171 1234567"
    result = sanitize_email(original, level=1)
    assert result == original


def test_level_2_signature_removal():
    """Level 2 sollte Signatur entfernen"""
    text = """
Hallo,

bitte antworten Sie.

Mit freundlichen Grüßen
Max Mustermann
"""
    result = sanitize_email(text, level=2)
    assert "Mit freundlichen Grüßen" not in result
    assert "Max Mustermann" not in result


def test_level_2_quoted_history():
    """Level 2 sollte zitierte Historie entfernen"""
    text = """
Neue Nachricht hier.

Am 20.12.2024 schrieb Hans:
> Alte Nachricht
> Noch mehr alt
"""
    result = sanitize_email(text, level=2)
    assert "Alte Nachricht" not in result
    assert "Neue Nachricht" in result


def test_level_3_email_pseudonymization():
    """Level 3 sollte E-Mail-Adressen pseudonymisieren"""
    text = "Kontakt: max@example.com und info@test.de"
    result = sanitize_email(text, level=3)
    
    assert "max@example.com" not in result
    assert "info@test.de" not in result
    assert "[EMAIL_1]" in result
    assert "[EMAIL_2]" in result


def test_level_3_phone_pseudonymization():
    """Level 3 sollte Telefonnummern pseudonymisieren"""
    text = "Rufen Sie an: +49 171 1234567"
    result = sanitize_email(text, level=3)
    
    assert "+49 171 1234567" not in result
    assert "[PHONE_" in result


def test_level_3_iban_pseudonymization():
    """Level 3 sollte IBANs pseudonymisieren"""
    text = "Überweisen auf: DE89 3704 0044 0532 0130 00"
    result = sanitize_email(text, level=3)
    
    assert "DE89" not in result
    assert "[IBAN]" in result


def test_level_3_url_pseudonymization():
    """Level 3 sollte URLs pseudonymisieren"""
    text = "Mehr Infos: https://example.com/page"
    result = sanitize_email(text, level=3)
    
    assert "https://example.com" not in result
    assert "[URL_" in result


def test_get_sanitization_level():
    """Test für Level-Empfehlung"""
    assert get_sanitization_level(use_cloud=False) == 2
    assert get_sanitization_level(use_cloud=True) == 3


if __name__ == "__main__":
    print("🧪 Führe Sanitizer-Tests aus...\n")
    
    tests = [
        test_level_1_volltext,
        test_level_2_signature_removal,
        test_level_2_quoted_history,
        test_level_3_email_pseudonymization,
        test_level_3_phone_pseudonymization,
        test_level_3_iban_pseudonymization,
        test_level_3_url_pseudonymization,
        test_get_sanitization_level
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠️  {test_func.__name__}: {e}")
            failed += 1
    
    print(f"\n📊 Ergebnis: {passed} bestanden, {failed} fehlgeschlagen")
