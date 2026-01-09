"""
Mail Helper - Authentication & 2FA
Handles Login, Register, TOTP 2FA
"""

import pyotp
import qrcode
from io import BytesIO
import base64
import logging
import importlib

logger = logging.getLogger(__name__)


class AuthManager:
    """Verwaltet Authentifizierung und 2FA"""

    @staticmethod
    def generate_totp_secret() -> str:
        """Generiert ein neues TOTP-Secret"""
        return pyotp.random_base32()

    @staticmethod
    def generate_qr_code(user_email: str, totp_secret: str) -> str:
        """Generiert QR-Code für TOTP-Setup"""
        totp = pyotp.TOTP(totp_secret)
        uri = totp.provisioning_uri(name=user_email, issuer_name="MailHelper")

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buf = BytesIO()
        # PyPNGImage (qrcode ohne PIL) vs PIL.Image haben unterschiedliche save() APIs
        try:
            img.save(buf, format="PNG")  # PIL/Pillow
        except TypeError:
            img.save(buf)  # pypng (kein format-Parameter)
        buf.seek(0)

        img_base64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{img_base64}"

    @staticmethod
    def verify_totp(totp_secret: str, token: str) -> bool:
        """Überprüft einen TOTP-Token"""
        try:
            totp = pyotp.TOTP(totp_secret)
            return totp.verify(token, valid_window=1)
        except Exception as e:
            logger.error(f"TOTP-Verifikation Fehler: {e}")
            return False

    @staticmethod
    def get_backup_codes(count: int = 10) -> list:
        """Generiert Backup-Codes"""
        import secrets

        codes = []
        for _ in range(count):
            code = secrets.token_hex(3).upper()
            codes.append(code)
        return codes


class ServiceTokenManager:
    """
    Verwaltet Service-Tokens für Background-Jobs (Phase 2).
    
    Security Model:
    - Token wird mit 384-bit Entropie generiert
    - Token-Hash wird bcrypt-gehasht (nicht reversible)
    - DEK wird mit Token gespeichert
    - Nach Expiry wird DEK automatisch gelöscht
    - last_verified_at wird für Audit-Trails aktualisiert
    """

    @staticmethod
    def create_token(user_id: int, master_key: str, session, days: int = 7) -> tuple:
        """
        Erstellt einen neuen Service-Token mit verschlüsselter DEK.
        
        Phase 2: DEK wird aus Session in Token gespeichert,
        damit Worker die DEK nicht über Prozessparameter erhalten.
        
        Args:
            user_id: User-ID
            master_key: DEK aus Session (wird hier gespeichert)
            session: SQLAlchemy Session
            days: Token-Expiry in Tagen (default: 7)
            
        Returns:
            (token_plaintext, token_object): Token und Model für Audit/Debug
            
        Security:
        - Token ist 384 Bits = 48 Bytes = 64 chars (urlsafe base64)
        - Token-Hash nicht reversible (bcrypt)
        - DEK als Plaintext speichern (sowieso RCE = Game Over)
        - TTL verhindert unbegrenzte Gültigkeit
        """
        import importlib
        from datetime import datetime, timedelta, UTC

        models = importlib.import_module(".02_models", "src")

        token = models.ServiceToken.generate_token()
        token_hash = models.ServiceToken.hash_token(token)

        service_token = models.ServiceToken(
            user_id=user_id,
            token_hash=token_hash,
            encrypted_dek=master_key,
            expires_at=datetime.now(UTC) + timedelta(days=days),
        )

        session.add(service_token)
        session.commit()

        logger.info(f"✅ Service-Token {service_token.id} erstellt (expires: {service_token.expires_at})")
        return token, service_token

    @staticmethod
    def verify_token(token: str, session) -> dict or None:
        """Verifiziert einen Service-Token

        Returns:
            User object or None
        """
        import importlib

        models = importlib.import_module(".02_models", "src")

        service_tokens = session.query(models.ServiceToken).all()

        for st in service_tokens:
            if st.is_valid() and models.ServiceToken.verify_token(token, st.token_hash):
                return st.user

        return None

    @staticmethod
    def revoke_token(token_id: int, session):
        """Sperrt einen Token"""
        import importlib

        models = importlib.import_module(".02_models", "src")

        token = session.query(models.ServiceToken).filter_by(id=token_id).first()
        if token:
            session.delete(token)
            session.commit()
            logger.info("🔒 Token *** gesperrt")


class RecoveryCodeManager:
    """Verwaltet Recovery-Codes für Passwort-Reset"""

    @staticmethod
    def create_recovery_codes(user_id: int, session, count: int = 10) -> list:
        """Erstellt Recovery-Codes für einen User

        Returns:
            Liste von ungehashten Codes
        """
        import importlib

        models = importlib.import_module(".02_models", "src")

        codes = []
        code_objects = []

        for _ in range(count):
            code = models.RecoveryCode.generate_code()
            code_hash = models.RecoveryCode.hash_code(code)

            recovery = models.RecoveryCode(user_id=user_id, code_hash=code_hash)

            session.add(recovery)
            codes.append(code)
            code_objects.append(recovery)

        session.commit()
        logger.info(f"✅ {count} Recovery-Codes erstellt für User ***")

        return codes

    @staticmethod
    def verify_recovery_code(user_id: int, code: str, session) -> bool:
        """Überprüft und verwendet einen Recovery-Code

        Returns:
            True wenn Code gültig und verwendet
        """
        import importlib

        models = importlib.import_module(".02_models", "src")

        recovery_codes = (
            session.query(models.RecoveryCode).filter_by(user_id=user_id).all()
        )

        for rc in recovery_codes:
            if rc.is_unused() and models.RecoveryCode.verify_code(code, rc.code_hash):
                rc.mark_used()
                session.commit()
                logger.info("✅ Recovery-Code verwendet für User ***")
                return True

        return False

    @staticmethod
    def get_unused_codes(user_id: int, session) -> list:
        """Gibt Anzahl der ungebrauchten Recovery-Codes"""
        models = importlib.import_module(".02_models", "src")

        unused = (
            session.query(models.RecoveryCode)
            .filter_by(user_id=user_id)
            .filter(models.RecoveryCode.used_at == None)
            .count()
        )

        return unused

    @staticmethod
    def invalidate_all_codes(user_id: int, session):
        """Invalidiert alle Recovery-Codes eines Users (Phase 8c Security Hardening)

        Verwendet für Recovery-Code Regeneration - alte Codes werden gelöscht.
        """
        models = importlib.import_module(".02_models", "src")

        deleted = session.query(models.RecoveryCode).filter_by(user_id=user_id).delete()

        session.commit()
        logger.info(f"🗑️ {deleted} Recovery-Codes invalidiert für User ***")


class MasterKeyManager:
    """Verwaltet Encryption Keys (Phase 8: DEK/KEK Pattern)"""

    @staticmethod
    def setup_dek_for_user(user_id: int, password: str, session) -> tuple:
        """Erstellt DEK beim Registrieren (Zero-Knowledge mit DEK/KEK Pattern)

        1. Generiert Salt
        2. Leitet KEK aus Passwort ab (PBKDF2)
        3. Generiert zufälligen DEK
        4. Verschlüsselt DEK mit KEK
        5. Speichert encrypted_dek in DB

        Returns:
            (salt, encrypted_dek, dek)
        """
        encryption = importlib.import_module(".08_encryption", "src")
        models = importlib.import_module(".02_models", "src")

        salt = encryption.EncryptionManager.generate_salt()
        kek = encryption.EncryptionManager.generate_master_key(
            password, salt
        )  # KEK via PBKDF2
        dek = encryption.EncryptionManager.generate_dek()  # Zufälliger DEK
        encrypted_dek = encryption.EncryptionManager.encrypt_dek(dek, kek)

        user = session.query(models.User).filter_by(id=user_id).first()
        if user:
            user.salt = salt
            user.encrypted_dek = encrypted_dek
            session.commit()
            logger.info("✅ DEK erstellt für User *** (Zero-Knowledge DEK/KEK)")

        return salt, encrypted_dek, dek

    @staticmethod
    def setup_master_key_for_user(user_id: int, password: str, session) -> tuple:
        """DEPRECATED: Verwende setup_dek_for_user() stattdessen

        Nur für Migrations-Kompatibilität behalten.
        """
        logger.warning(
            "setup_master_key_for_user() ist deprecated, verwende setup_dek_for_user()"
        )
        return MasterKeyManager.setup_dek_for_user(user_id, password, session)

    @staticmethod
    def decrypt_dek_from_password(user, password: str) -> str:
        """Entschlüsselt DEK mit Passwort (KEK wird aus Passwort abgeleitet)

        Wird beim Login verwendet:
        1. KEK aus Passwort ableiten (PBKDF2 mit User.salt)
        2. DEK mit KEK entschlüsseln
        3. DEK in Session speichern

        Args:
            user: User-Model mit salt und encrypted_dek
            password: User-Passwort

        Returns:
            Base64-kodierter DEK
        """
        encryption = importlib.import_module(".08_encryption", "src")

        try:
            # Fallback für alte User mit encrypted_master_key (vor DEK/KEK Migration)
            if user.encrypted_dek:
                kek = encryption.EncryptionManager.generate_master_key(
                    password, user.salt
                )
                dek = encryption.EncryptionManager.decrypt_dek(user.encrypted_dek, kek)
                logger.info("✅ DEK erfolgreich entschlüsselt")
                return dek
            elif user.encrypted_master_key:
                # DEPRECATED: Alte User ohne DEK
                logger.warning("User *** nutzt altes encrypted_master_key Format")
                master_key = encryption.EncryptionManager.decrypt_master_key(
                    user.encrypted_master_key, password
                )
                return master_key
            else:
                logger.error(
                    "User *** hat weder encrypted_dek noch encrypted_master_key"
                )
                return None

        except Exception as e:
            logger.error(f"❌ DEK Entschlüsselung fehlgeschlagen: {type(e).__name__}")
            return None

    @staticmethod
    def decrypt_master_key_from_password(
        password: str, encrypted_master_key: str
    ) -> str:
        """DEPRECATED: Verwende decrypt_dek_from_password() stattdessen

        Nur für Migrations-Kompatibilität behalten.
        """
        encryption = importlib.import_module(".08_encryption", "src")

        try:
            master_key = encryption.EncryptionManager.decrypt_master_key(
                encrypted_master_key, password
            )
            logger.info("✅ Master-Key erfolgreich entschlüsselt")
            return master_key
        except Exception as e:
            logger.error(
                f"❌ Master-Key Entschlüsselung fehlgeschlagen: {type(e).__name__}"
            )
            return None
