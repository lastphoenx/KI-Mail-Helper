"""
Mail Helper - E-Mail Sanitizer & Pseudonymisierung
Datenschutz-Level 1-3 gemäß Konzept
"""

import re
import signal
import logging
import sys
import threading
from functools import wraps

logger = logging.getLogger(__name__)


# Phase 9f: ReDoS Protection Timeout-Decorator (WSL2-compatible)
def regex_timeout(seconds=2):
    """Timeout-Decorator für Regex-Operationen (ReDoS Protection)

    Bei Timeout: Gibt original Text zurück statt Exception zu werfen
    WSL2-Compatible: Nutzt threading.Timer statt signal.SIGALRM
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # signal.alarm() funktioniert nur im Haupt-Thread
            # In Flask-Requests (Worker-Threads) oder Windows nutzen wir Threading-Fallback
            use_threading = (
                sys.platform == "win32" 
                or "microsoft" in sys.platform.lower()
                or threading.current_thread() != threading.main_thread()
            )
            
            if use_threading:
                result = [None]
                exception = [None]

                def run_func():
                    try:
                        result[0] = func(*args, **kwargs)
                    except Exception as e:
                        exception[0] = e

                thread = threading.Thread(target=run_func, daemon=True)
                thread.start()
                thread.join(timeout=seconds)

                if thread.is_alive():
                    logger.warning(
                        f"ReDoS Protection: Regex timeout ({seconds}s) - returning original text"
                    )
                    return args[0] if args else ""

                if exception[0]:
                    raise exception[0]
                return result[0]
            else:
                # Unix/Linux Haupt-Thread: Nutze signal.SIGALRM für präzisere Timeouts
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Regex timeout in {func.__name__}")

                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(seconds)

                try:
                    return func(*args, **kwargs)
                except TimeoutError as e:
                    logger.warning(f"ReDoS Protection: {e} - returning original text")
                    return args[0] if args else ""
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)

        return wrapper

    return decorator


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
        r"\n--\s*\n.*",  # Standard -- Marker
        r"\nMit freundlichen Grüßen.*",
        r"\nBest regards.*",
        r"\nCordiali saluti.*",
        r"\nCordialement.*",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    return text


def _remove_quoted_history(text: str) -> str:
    """Entfernt zitierte Mail-Historie"""
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        # Zeilen die mit > beginnen (Zitat)
        if line.strip().startswith(">"):
            continue

        # "Am XX schrieb Y:" Pattern
        # Phase 9f: Bounded quantifiers (ReDoS Protection)
        # ALT: r'^Am .* schrieb .*:' (catastrophic backtracking!)
        # NEU: Non-greedy + max 200 chars (realistische E-Mail Quote-Header)
        if re.match(r"^Am .{1,200}? schrieb .{1,200}?:", line, re.IGNORECASE):
            break  # Alles danach ist Historie
        if re.match(r"^On .{1,200}? wrote:", line, re.IGNORECASE):
            break

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


@regex_timeout(seconds=2)  # Phase 9f: ReDoS Protection Timeout
def _pseudonymize(text: str) -> str:
    """Pseudonymisiert sensible Daten
    Ersetzt: E-Mails, Telefon, IBAN, URLs, optional Namen/Orte

    Phase 9f: ReDoS Protection via Timeout + Input-Length Limit
    """
    # Phase 9f: Input-Length Limit (Defense-in-Depth gegen ReDoS)
    MAX_LENGTH = 500_000  # 500KB
    if len(text) > MAX_LENGTH:
        logger.warning(f"Sanitizer: Input truncated {len(text)} > {MAX_LENGTH}")
        text = text[:MAX_LENGTH]

    # Zähler für fortlaufende Nummerierung
    counters = {"email": 0, "phone": 0, "iban": 0, "url": 0}

    def replace_email(match):
        counters["email"] += 1
        return f"[EMAIL_{counters['email']}]"

    def replace_phone(match):
        counters["phone"] += 1
        return f"[PHONE_{counters['phone']}]"

    def replace_iban(match):
        return "[IBAN]"

    def replace_url(match):
        counters["url"] += 1
        return f"[URL_{counters['url']}]"

    # E-Mail-Adressen (robuster gegen Spaces: "user @ example.com")
    # Phase 9f: Simplified Pattern (ReDoS Protection)
    # ALT: r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Z|a-z]{2,}\b'
    #      (nested quantifiers + word boundaries = catastrophic backtracking!)
    # NEU: Bounded lengths (RFC 5321: local-part max 64, domain max 253)
    text = re.sub(
        r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,10}",
        replace_email,
        text,
    )

    # IBAN (DE + International) - robuster gegen variable Spaces
    # WICHTIG: VOR Telefonnummern prüfen, sonst wird IBAN als Phone erkannt!
    def normalize_and_replace_iban(match):
        normalized = match.group(0).replace(" ", "").replace("\t", "")
        # IBAN hat 15-34 Zeichen: 2 Ländercode + 2 Prüfziffer + 11-30 BBAN
        if len(normalized) >= 15 and len(normalized) <= 34:
            return replace_iban(match)
        return match.group(0)  # Kein IBAN

    text = re.sub(
        r"\b[A-Z]{2}\s*\d{2}(?:\s*[\dA-Z]){11,30}\b",
        normalize_and_replace_iban,
        text,
        flags=re.IGNORECASE,
    )

    # Telefonnummern (einfaches Pattern)
    text = re.sub(
        r"\b(\+?\d{1,3}[\s\-\.]?)?\(?\d{2,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}\b",
        replace_phone,
        text,
    )

    # URLs (Phase 9f: Bounded Pattern - max 2000 Zeichen)
    # ALT: r'https?://[^\s]+' (unbounded - ReDoS anfällig!)
    # NEU: Max 2000 chars (realistische URL-Länge)
    text = re.sub(r"https?://[^\s]{1,2000}", replace_url, text)

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
