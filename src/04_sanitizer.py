"""
Mail Helper - E-Mail Sanitizer & Pseudonymisierung
Datenschutz-Level 1-3 gemäß Konzept
"""

import re
from typing import Tuple


def sanitize_email(text: str, level: int = 2) -> str:
    """
    Bereinigt und pseudonymisiert E-Mail-Text
    
    Args:
        text: Original E-Mail-Body
        level: Datenschutz-Level
            1 = Volltext (keine Änderungen)
            2 = Ohne Signatur + Historie
            3 = + Pseudonymisierung (Pflicht für Cloud-KI!)
    
    Returns:
        Bereinigter Text
    """
    if level == 1:
        return text
    
    # Level 2+: Signatur & Historie entfernen
    cleaned = _remove_signature(text)
    cleaned = _remove_quoted_history(cleaned)
    
    if level >= 3:
        # Level 3: Pseudonymisierung
        cleaned = _pseudonymize(cleaned)
    
    return cleaned.strip()


def _remove_signature(text: str) -> str:
    """Entfernt E-Mail-Signatur"""
    # Typische Signatur-Marker
    patterns = [
        r'\n--\s*\n.*',           # Standard -- Marker
        r'\nMit freundlichen Grüßen.*',
        r'\nBest regards.*',
        r'\nCordiali saluti.*',
        r'\nCordialement.*',
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
    
    return text


def _remove_quoted_history(text: str) -> str:
    """Entfernt zitierte Mail-Historie"""
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Zeilen die mit > beginnen (Zitat)
        if line.strip().startswith('>'):
            continue
        
        # "Am XX schrieb Y:" Pattern
        if re.match(r'^Am .* schrieb .*:', line, re.IGNORECASE):
            break  # Alles danach ist Historie
        if re.match(r'^On .* wrote:', line, re.IGNORECASE):
            break
        
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def _pseudonymize(text: str) -> str:
    """
    Pseudonymisiert sensible Daten
    Ersetzt: E-Mails, Telefon, IBAN, URLs, optional Namen/Orte
    """
    # Zähler für fortlaufende Nummerierung
    counters = {
        'email': 0,
        'phone': 0,
        'iban': 0,
        'url': 0
    }
    
    def replace_email(match):
        counters['email'] += 1
        return f"[EMAIL_{counters['email']}]"
    
    def replace_phone(match):
        counters['phone'] += 1
        return f"[PHONE_{counters['phone']}]"
    
    def replace_iban(match):
        return "[IBAN]"
    
    def replace_url(match):
        counters['url'] += 1
        return f"[URL_{counters['url']}]"
    
    # E-Mail-Adressen
    text = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        replace_email,
        text
    )
    
    # Telefonnummern (einfaches Pattern)
    text = re.sub(
        r'\b(\+?\d{1,3}[\s\-\.]?)?\(?\d{2,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}\b',
        replace_phone,
        text
    )
    
    # IBAN (DE + International)
    text = re.sub(
        r'\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{4}[\s]?[\dA-Z]{0,4}\b',
        replace_iban,
        text,
        flags=re.IGNORECASE
    )
    
    # URLs
    text = re.sub(
        r'https?://[^\s]+',
        replace_url,
        text
    )
    
    # Optional: Namen, Orte (sehr einfach, kann erweitert werden)
    # TODO: Für bessere Erkennung → NER (spaCy, transformers)
    
    return text


def get_sanitization_level(use_cloud: bool = False) -> int:
    """
    Bestimmt den erforderlichen Datenschutz-Level
    
    Args:
        use_cloud: Wird externe Cloud-KI genutzt?
    
    Returns:
        Empfohlener Level (2 oder 3)
    """
    return 3 if use_cloud else 2


if __name__ == "__main__":
    # Test-Beispiel
    test_email = """
Hallo Herr Müller,

bitte überweisen Sie 1.500 EUR auf folgendes Konto:
IBAN: DE89 3704 0044 0532 0130 00

Bei Fragen erreichen Sie mich unter +49 171 1234567 oder max@beispiel.de.

Mehr Infos: https://www.beispiel.de/info

Mit freundlichen Grüßen
Max Mustermann
--
Musterfirma GmbH
Musterstraße 1, 12345 Musterstadt
"""
    
    print("=== Level 1 (Volltext) ===")
    print(sanitize_email(test_email, level=1))
    
    print("\n=== Level 2 (ohne Signatur) ===")
    print(sanitize_email(test_email, level=2))
    
    print("\n=== Level 3 (Pseudonymisiert) ===")
    print(sanitize_email(test_email, level=3))
