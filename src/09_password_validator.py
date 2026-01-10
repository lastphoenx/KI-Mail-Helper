"""
Mail Helper - Password Validator (Security Hardening Phase 8c)
OWASP-konforme Password-Policy mit Entropie-Messung + HIBP-Check
"""

import re
import logging
import hashlib
import requests
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Top 100 häufigste Passwörter (rockyou.txt Auszug)
COMMON_PASSWORDS = {
    "123456",
    "password",
    "12345678",
    "qwerty",
    "123456789",
    "12345",
    "1234",
    "111111",
    "1234567",
    "dragon",
    "123123",
    "baseball",
    "iloveyou",
    "trustno1",
    "1234567890",
    "sunshine",
    "master",
    "123321",
    "666666",
    "photoshop",
    "1111111",
    "654321",
    "football",
    "987654321",
    "letmein",
    "monkey",
    "shadow",
    "abc123",
    "qwertyuiop",
    "zxcvbnm",
    "asdfghjkl",
    "welcome",
    "admin",
    "login",
    "password1",
    "passw0rd",
    "qwerty123",
    "welcome123",
    "admin123",
    "root",
    "toor",
    "test",
    "guest",
    "user",
    "administrator",
    "adminadmin",
    "superman",
    "batman",
    "spiderman",
    "starwars",
    "pokemon",
    "computer",
    "whatever",
    "love",
    "hello",
    "freedom",
    "internet",
    "michael",
    "ashley",
    "jessica",
    "jennifer",
    "daniel",
    "matthew",
    "joshua",
    "andrew",
    "david",
    "james",
    "robert",
    "john",
    "william",
    "richard",
    "thomas",
    "charles",
    "christopher",
    "joseph",
    "donald",
    "george",
    "kenneth",
    "steven",
    "edward",
    "brian",
    "ronald",
    "anthony",
    "kevin",
    "jason",
    "matthew",
    "gary",
    "timothy",
    "jose",
    "larry",
    "jeffrey",
    "frank",
    "scott",
    "eric",
    "stephen",
    "andrew",
    "raymond",
    "gregory",
    "joshua",
    "jerry",
    "dennis",
    "walter",
    "patrick",
    "peter",
    "harold",
    "douglas",
    "henry",
    "carl",
    "arthur",
    "ryan",
}


class PasswordValidator:
    """OWASP-konforme Password-Validation

    Requirements:
    - Mindestlänge: 24 Zeichen (empfohlen für Master-Passwörter)
    - Komplexität: Groß-, Kleinbuchstaben, Zahlen, Sonderzeichen
    - Keine häufigen Passwörter (Blacklist)
    - Entropie-Check (optional mit zxcvbn)
    """

    MIN_LENGTH = 24
    MIN_LOWERCASE = 1
    MIN_UPPERCASE = 1
    MIN_DIGITS = 1
    MIN_SPECIAL = 1

    @classmethod
    def validate(cls, password: str) -> Tuple[bool, Optional[str]]:
        """Validiert ein Passwort

        Args:
            password: Zu validierendes Passwort

        Returns:
            (is_valid, error_message)
            - (True, None) wenn valide
            - (False, "Fehlertext") wenn invalide
        """
        if not password:
            return False, "Passwort ist erforderlich"

        # 1. Längencheck
        if len(password) < cls.MIN_LENGTH:
            return (
                False,
                f"Passwort muss mindestens {cls.MIN_LENGTH} Zeichen lang sein (aktuell: {len(password)})",
            )

        # 2. Komplexitäts-Checks
        has_lowercase = bool(re.search(r"[a-z]", password))
        has_uppercase = bool(re.search(r"[A-Z]", password))
        has_digit = bool(re.search(r"\d", password))
        has_special = bool(
            re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`;\']', password)
        )

        missing = []
        if not has_lowercase:
            missing.append("Kleinbuchstaben")
        if not has_uppercase:
            missing.append("Großbuchstaben")
        if not has_digit:
            missing.append("Zahlen")
        if not has_special:
            missing.append("Sonderzeichen")

        if missing:
            return False, f"Passwort muss enthalten: {', '.join(missing)}"

        # 3. Blacklist-Check (häufige Passwörter)
        password_lower = password.lower()
        if password_lower in COMMON_PASSWORDS:
            return False, "Passwort ist zu häufig/unsicher (in Top-100 Passwortliste)"

        # 3b. Have I Been Pwned Check (k-Anonymity Model - Zero-Knowledge!)
        hibp_count = cls._check_hibp(password)
        if hibp_count is not None and hibp_count > 0:
            return (
                False,
                f"⚠️ Passwort wurde {hibp_count:,}x in Datenlecks gefunden (Have I Been Pwned). Bitte anderes Passwort wählen!",
            )

        # 4. zxcvbn-Check (optional, wenn installiert)
        try:
            import zxcvbn

            result = zxcvbn.zxcvbn(password)
            score = result["score"]  # 0-4 (0=sehr schwach, 4=sehr stark)

            if score < 3:
                feedback = result.get("feedback", {})
                warning = feedback.get("warning", "Passwort zu schwach")
                suggestions = feedback.get("suggestions", [])

                error_msg = (
                    f"Passwort-Entropie zu niedrig (Score: {score}/4). {warning}"
                )
                if suggestions:
                    error_msg += f" Vorschläge: {', '.join(suggestions)}"

                return False, error_msg

            logger.info(f"✅ Password Entropy Score: {score}/4 (zxcvbn)")

        except ImportError:
            # zxcvbn nicht installiert - überspringen
            logger.debug("zxcvbn nicht installiert - überspringe Entropie-Check")

        # 5. Sequenzen-Check (optional)
        if cls._has_sequential_chars(password):
            return (
                False,
                "Passwort enthält zu viele aufeinanderfolgende Zeichen (z.B. 'abc', '123')",
            )

        # Alle Checks bestanden
        return True, None

    @staticmethod
    def _check_hibp(password: str) -> Optional[int]:
        """Prüft Passwort gegen Have I Been Pwned API (k-Anonymity Model - Zero-Knowledge!)

        Sendet nur erste 5 Zeichen vom SHA-1 Hash an API.
        API gibt alle Hashes mit gleichem Prefix zurück.
        Client matched lokal → kein Passwort wird übertragen!

        Args:
            password: Zu prüfendes Passwort

        Returns:
            Anzahl der Fundstellen in Datenlecks (None bei API-Fehler)
        """
        try:
            # 1. SHA-1 Hash des Passworts berechnen
            sha1_hash = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()

            # 2. Erste 5 Zeichen (Prefix) an API senden
            prefix = sha1_hash[:5]
            suffix = sha1_hash[5:]

            # 3. API-Request (k-Anonymity Model)
            url = f"https://api.pwnedpasswords.com/range/{prefix}"
            headers = {
                "User-Agent": "KI-Mail-Helper/1.0 (Security Hardening Phase 8c)",
                "Add-Padding": "true",  # Privacy-Plus: verhindert Timing-Angriffe
            }
            # Separate Timeouts: (connect, read)
            response = requests.get(url, headers=headers, timeout=(2, 3))

            if response.status_code == 429:
                # Rate-Limit Hit - könnte Retry-After Header respektieren
                # TODO: Für Production mit vielen Users: Retry-After auswerten oder Caching implementieren
                logger.warning("HIBP API Rate-Limit (429) - überspringe Check")
                return None

            if response.status_code != 200:
                logger.warning(f"HIBP API error: {response.status_code}")
                return None  # Bei API-Fehler: nicht blockieren

            # 4. Lokaler Match (Zero-Knowledge!) - Robust Parsing
            for line in response.text.splitlines():
                if ":" not in line:
                    continue  # Ungültige Zeile überspringen

                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue

                hash_suffix, count = parts
                if hash_suffix.strip().upper() == suffix:
                    return int(count.strip())

            # Passwort nicht in HIBP gefunden ✅
            return 0

        except requests.exceptions.Timeout:
            logger.warning("HIBP API timeout - überspringe Check")
            return None  # Bei Timeout: nicht blockieren

        except Exception as e:
            logger.error(f"HIBP Check fehlgeschlagen: {e}")
            return None  # Bei Fehler: nicht blockieren

    @staticmethod
    def _has_sequential_chars(password: str, min_seq_length: int = 4) -> bool:
        """Prüft auf aufeinanderfolgende Zeichen (abc, 123, etc.)"""
        sequences = [
            "abcdefghijklmnopqrstuvwxyz",
            "0123456789",
            "qwertyuiopasdfghjklzxcvbnm",  # Keyboard-Sequenz
        ]

        for seq in sequences:
            for i in range(len(seq) - min_seq_length + 1):
                substring = seq[i : i + min_seq_length]
                if substring in password.lower():
                    return True

        return False

    @classmethod
    def get_strength_label(cls, password: str) -> str:
        """Gibt ein Label für die Passwort-Stärke zurück (für UI)

        Returns:
            "Sehr schwach" | "Schwach" | "Mittel" | "Stark" | "Sehr stark"
        """
        try:
            import zxcvbn

            result = zxcvbn.zxcvbn(password)
            score = result["score"]

            labels = ["Sehr schwach", "Schwach", "Mittel", "Stark", "Sehr stark"]
            return labels[score]

        except ImportError:
            # Fallback ohne zxcvbn (heuristische Stärke)
            is_valid, _ = cls.validate(password)

            if not is_valid:
                return "Schwach"

            if len(password) >= 32:
                return "Sehr stark"
            elif len(password) >= cls.MIN_LENGTH:
                return "Stark"
            else:
                return "Mittel"
