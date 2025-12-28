"""
Mail Helper - Encryption Module
Phase 3: AES-256-GCM encryption for sensitive data
"""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os
import base64
import logging
import hashlib

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Verwaltet Verschlüsselung mit AES-256-GCM"""

    ALGORITHM = algorithms.AES
    KEY_SIZE = 32
    ITERATIONS = 600000  # OWASP empfiehlt min. 600.000 für PBKDF2-HMAC-SHA256 (2024)
    TAG_LENGTH = 16

    @staticmethod
    def generate_salt(length: int = 32) -> str:
        """Generiert einen zufälligen Salt"""
        return base64.b64encode(os.urandom(length)).decode()

    @staticmethod
    def generate_master_key(password: str, salt: str) -> str:
        """Leitet Master-Key aus Passwort ab (PBKDF2)

        Args:
            password: Benutzer-Passwort
            salt: Salt für PBKDF2

        Returns:
            Base64-kodierter Master-Key (256 Bit)
        """
        salt_bytes = base64.b64decode(salt)

        master_key = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt_bytes, EncryptionManager.ITERATIONS
        )

        return base64.b64encode(master_key).decode()

    @staticmethod
    def encrypt_data(plaintext: str, master_key: str) -> str:
        """Verschlüsselt Daten mit AES-256-GCM

        Args:
            plaintext: Zu verschlüsselnde Daten
            master_key: Base64-kodierter Master-Key

        Returns:
            Base64-kodiertes Encrypted-Blob (IV + Ciphertext + Tag)
        """
        if not plaintext:
            return ""

        try:
            key = base64.b64decode(master_key)
            iv = os.urandom(12)

            cipher = Cipher(
                algorithms.AES(key), modes.GCM(iv), backend=default_backend()
            )
            encryptor = cipher.encryptor()

            ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()

            encrypted_blob = iv + ciphertext + encryptor.tag
            return base64.b64encode(encrypted_blob).decode()

        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise

    @staticmethod
    def decrypt_data(encrypted_blob: str, master_key: str) -> str:
        """Entschlüsselt Daten mit AES-256-GCM

        Args:
            encrypted_blob: Base64-kodiertes Encrypted-Blob
            master_key: Base64-kodierter Master-Key

        Returns:
            Entschlüsselte Daten als String
        """
        if not encrypted_blob:
            return ""

        try:
            key = base64.b64decode(master_key)
            encrypted_bytes = base64.b64decode(encrypted_blob)

            iv = encrypted_bytes[:12]
            ciphertext = encrypted_bytes[12 : -EncryptionManager.TAG_LENGTH]
            tag = encrypted_bytes[-EncryptionManager.TAG_LENGTH :]

            cipher = Cipher(
                algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend()
            )
            decryptor = cipher.decryptor()

            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            return plaintext.decode()

        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise

    @staticmethod
    def generate_dek() -> str:
        """Generiert einen zufälligen Data Encryption Key (DEK)

        DEK ist ein 256-Bit zufälliger Schlüssel, der alle E-Mail-Daten verschlüsselt.
        Wird mit KEK (aus Passwort) verschlüsselt gespeichert.

        Returns:
            Base64-kodierter DEK (32 Bytes)
        """
        dek = os.urandom(32)  # 256 Bit
        return base64.b64encode(dek).decode()

    @staticmethod
    def encrypt_dek(dek: str, kek: str) -> str:
        """Verschlüsselt DEK mit KEK (Key Encryption Key)

        Args:
            dek: Base64-kodierter Data Encryption Key
            kek: Base64-kodierter Key Encryption Key (aus Passwort via PBKDF2)

        Returns:
            Base64-kodiertes Encrypted-Blob (IV + Ciphertext + Tag)
        """
        try:
            key = base64.b64decode(kek)
            dek_bytes = base64.b64decode(dek)
            iv = os.urandom(12)

            cipher = Cipher(
                algorithms.AES(key), modes.GCM(iv), backend=default_backend()
            )
            encryptor = cipher.encryptor()

            ciphertext = encryptor.update(dek_bytes) + encryptor.finalize()

            encrypted_blob = iv + ciphertext + encryptor.tag
            return base64.b64encode(encrypted_blob).decode()

        except Exception as e:
            logger.error(f"DEK encryption error: {e}")
            raise

    @staticmethod
    def decrypt_dek(encrypted_dek: str, kek: str) -> str:
        """Entschlüsselt DEK mit KEK

        Args:
            encrypted_dek: Base64-kodiertes Encrypted-Blob
            kek: Base64-kodierter Key Encryption Key (aus Passwort via PBKDF2)

        Returns:
            Base64-kodierter DEK
        """
        try:
            key = base64.b64decode(kek)
            encrypted_bytes = base64.b64decode(encrypted_dek)

            iv = encrypted_bytes[:12]
            ciphertext = encrypted_bytes[12 : -EncryptionManager.TAG_LENGTH]
            tag = encrypted_bytes[-EncryptionManager.TAG_LENGTH :]

            cipher = Cipher(
                algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend()
            )
            decryptor = cipher.decryptor()

            dek_bytes = decryptor.update(ciphertext) + decryptor.finalize()
            return base64.b64encode(dek_bytes).decode()

        except Exception as e:
            logger.error(f"DEK decryption error: {e}")
            raise

    @staticmethod
    def encrypt_master_key(master_key: str, password: str) -> str:
        """Verschlüsselt den Master-Key mit dem User-Passwort

        DEPRECATED: Wird durch encrypt_dek() ersetzt.
        Nur für Migrations-Kompatibilität behalten.

        Wird verwendet um den Master-Key in der DB zu speichern.
        Beim Login wird dieser mit dem eingegebenen Passwort entschlüsselt.

        Args:
            master_key: Base64-kodierter Master-Key
            password: User-Passwort

        Returns:
            Base64-kodiertes Encrypted Master-Key (Format: salt:iv:ciphertext:tag)
        """
        try:
            # Separate Salt und IV generieren (kryptographisch korrekt)
            salt = os.urandom(16)  # Salt für PBKDF2
            iv = os.urandom(12)  # IV für AES-GCM

            # Key aus Passwort ableiten (mit Salt, NICHT mit IV!)
            key = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), salt, EncryptionManager.ITERATIONS
            )[:32]

            cipher = Cipher(
                algorithms.AES(key), modes.GCM(iv), backend=default_backend()
            )
            encryptor = cipher.encryptor()

            ciphertext = encryptor.update(master_key.encode()) + encryptor.finalize()

            # Format: salt:iv:ciphertext:tag (alle Base64)
            encrypted_blob = (
                base64.b64encode(salt).decode()
                + ":"
                + base64.b64encode(iv).decode()
                + ":"
                + base64.b64encode(ciphertext).decode()
                + ":"
                + base64.b64encode(encryptor.tag).decode()
            )
            return encrypted_blob

        except Exception as e:
            logger.error(f"Master-Key encryption error: {e}")
            raise

    @staticmethod
    def decrypt_master_key(encrypted_master_key: str, password: str) -> str:
        """Entschlüsselt den Master-Key mit dem User-Passwort

        Args:
            encrypted_master_key: Verschlüsselter Master-Key (Format: salt:iv:ciphertext:tag)
            password: User-Passwort

        Returns:
            Base64-kodierter Master-Key
        """
        try:
            # Parse Format: salt:iv:ciphertext:tag
            parts = encrypted_master_key.split(":")
            if len(parts) == 4:
                # Neues Format (mit separatem Salt)
                salt = base64.b64decode(parts[0])
                iv = base64.b64decode(parts[1])
                ciphertext = base64.b64decode(parts[2])
                tag = base64.b64decode(parts[3])
            else:
                # Legacy Format (IV als Salt) - backwards compatibility
                encrypted_bytes = base64.b64decode(encrypted_master_key)
                iv = encrypted_bytes[:12]
                ciphertext = encrypted_bytes[12 : -EncryptionManager.TAG_LENGTH]
                tag = encrypted_bytes[-EncryptionManager.TAG_LENGTH :]
                salt = iv[:8]  # Legacy: IV als Salt (unsicher, aber kompatibel)

            # Key aus Passwort ableiten
            key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)[:32]

            cipher = Cipher(
                algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend()
            )
            decryptor = cipher.decryptor()

            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            return plaintext.decode()

        except Exception as e:
            logger.error(f"Master-Key decryption error: {e}")
            raise


class CredentialManager:
    """Verwaltet Verschlüsslung von Zugangsdaten (IMAP-Passwörter, E-Mail-Adressen)"""

    @staticmethod
    def encrypt_imap_password(password: str, master_key: str) -> str:
        """Verschlüsselt IMAP-Passwort mit Master-Key"""
        return EncryptionManager.encrypt_data(password, master_key)

    @staticmethod
    def decrypt_imap_password(encrypted_password: str, master_key: str) -> str:
        """Entschlüsselt IMAP-Passwort mit Master-Key"""
        return EncryptionManager.decrypt_data(encrypted_password, master_key)

    @staticmethod
    def encrypt_email_address(email: str, master_key: str) -> str:
        """Verschlüsselt E-Mail-Adresse mit Master-Key (Zero-Knowledge)"""
        if not email:
            return ""
        return EncryptionManager.encrypt_data(email, master_key)

    @staticmethod
    def decrypt_email_address(encrypted_email: str, master_key: str) -> str:
        """Entschlüsselt E-Mail-Adresse mit Master-Key"""
        if not encrypted_email:
            return ""
        return EncryptionManager.decrypt_data(encrypted_email, master_key)

    @staticmethod
    def hash_email_address(email: str) -> str:
        """Hasht E-Mail-Adresse für Suche (nicht umkehrbar)"""
        if not email:
            return ""
        return hashlib.sha256(email.lower().encode()).hexdigest()

    @staticmethod
    def encrypt_server(server: str, master_key: str) -> str:
        """Verschlüsselt Server-Adresse mit Master-Key"""
        if not server:
            return ""
        return EncryptionManager.encrypt_data(server, master_key)

    @staticmethod
    def decrypt_server(encrypted_server: str, master_key: str) -> str:
        """Entschlüsselt Server-Adresse mit Master-Key"""
        if not encrypted_server:
            return ""
        return EncryptionManager.decrypt_data(encrypted_server, master_key)


class EmailDataManager:
    """Verwaltet Verschlüsslung von Email-Daten (Sender, Subject, Bodies, Summaries)"""

    @staticmethod
    def encrypt_email_body(body: str, master_key: str) -> str:
        """Verschlüsselt E-Mail-Body"""
        if not body:
            return ""
        return EncryptionManager.encrypt_data(body, master_key)

    @staticmethod
    def decrypt_email_body(encrypted_body: str, master_key: str) -> str:
        """Entschlüsselt E-Mail-Body"""
        if not encrypted_body:
            return ""
        return EncryptionManager.decrypt_data(encrypted_body, master_key)

    @staticmethod
    def encrypt_email_sender(sender: str, master_key: str) -> str:
        """Verschlüsselt E-Mail-Sender (Zero-Knowledge)"""
        if not sender:
            return ""
        return EncryptionManager.encrypt_data(sender, master_key)

    @staticmethod
    def decrypt_email_sender(encrypted_sender: str, master_key: str) -> str:
        """Entschlüsselt E-Mail-Sender"""
        if not encrypted_sender:
            return ""
        return EncryptionManager.decrypt_data(encrypted_sender, master_key)

    @staticmethod
    def encrypt_email_subject(subject: str, master_key: str) -> str:
        """Verschlüsselt E-Mail-Subject (Zero-Knowledge)"""
        if not subject:
            return ""
        return EncryptionManager.encrypt_data(subject, master_key)

    @staticmethod
    def decrypt_email_subject(encrypted_subject: str, master_key: str) -> str:
        """Entschlüsselt E-Mail-Subject"""
        if not encrypted_subject:
            return ""
        return EncryptionManager.decrypt_data(encrypted_subject, master_key)

    @staticmethod
    def encrypt_summary(summary: str, master_key: str) -> str:
        """Verschlüsselt E-Mail-Summary"""
        if not summary:
            return ""
        return EncryptionManager.encrypt_data(summary, master_key)

    @staticmethod
    def decrypt_summary(encrypted_summary: str, master_key: str) -> str:
        """Entschlüsselt E-Mail-Summary"""
        if not encrypted_summary:
            return ""
        return EncryptionManager.decrypt_data(encrypted_summary, master_key)
