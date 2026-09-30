"""mail_helper - Google OAuth Integration
Handles Google OAuth 2.0 flow for Gmail access
"""

import requests
import logging
from datetime import datetime, UTC
from typing import Optional, Dict
import importlib

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_API_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class GoogleOAuthManager:
    """Verwaltet Google OAuth 2.0 Flow"""

    @staticmethod
    def get_auth_url(client_id: str, redirect_uri: str, state: str | None = None) -> str:
        """Generiert Google Authorization URL

        Args:
            client_id: Google OAuth Client ID
            redirect_uri: Redirect URI nach Auth (muss registriert sein)
            state: Optional state parameter für CSRF protection

        Returns:
            Google OAuth Authorization URL
        """
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_API_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }

        if state:
            params["state"] = state

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{GOOGLE_AUTH_URL}?{query_string}"

    @staticmethod
    def exchange_code_for_token(
        auth_code: str, client_id: str, client_secret: str, redirect_uri: str
    ) -> Optional[Dict]:
        """Tauscht Authorization Code gegen Access Token

        Args:
            auth_code: Authorization Code von Google
            client_id: Google OAuth Client ID
            client_secret: Google OAuth Client Secret
            redirect_uri: Muss exakt die registrierte URI sein

        Returns:
            Dict mit access_token, refresh_token, expires_in oder None bei Fehler
        """
        try:
            data = {
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }

            response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.info("✅ Google OAuth Token erfolgreich getauscht")
            return token_data

        except requests.exceptions.RequestException as e:
            # Security Fix: Don't expose auth codes/tokens in logs
            logger.debug(f"Token exchange error details: {e}")  # Debug only
            logger.error("❌ Token Exchange fehlgeschlagen (credentials sanitized)")
            return None

    @staticmethod
    def refresh_access_token(
        refresh_token: str, client_id: str, client_secret: str
    ) -> Optional[Dict]:
        """Erneuert Access Token mit Refresh Token

        Args:
            refresh_token: Google Refresh Token
            client_id: Google OAuth Client ID
            client_secret: Google OAuth Client Secret

        Returns:
            Dict mit neuem access_token, expires_in oder None bei Fehler
        """
        try:
            data = {
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            }

            response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.info("✅ Access Token erfolgreich erneuert")
            return token_data

        except requests.exceptions.RequestException as e:
            logger.debug(f"Token refresh error details: {e}")
            logger.error("❌ Token Refresh fehlgeschlagen (credentials sanitized)")
            return None

    @staticmethod
    def get_user_email(access_token: str) -> Optional[str]:
        """Holt User Email mit Access Token

        Args:
            access_token: Google Access Token

        Returns:
            User Email oder None bei Fehler
        """
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=10)
            response.raise_for_status()

            user_info = response.json()
            email = user_info.get("email")

            if email:
                logger.info(f"✅ User Email abgerufen: {email[:3]}***@***")
                return email

            return None

        except requests.exceptions.RequestException as e:
            logger.debug(f"User info error details: {e}")
            logger.error("❌ User Info Fehler (credentials sanitized)")
            return None


class OAuthTokenManager:
    """Verwaltet OAuth Token Refresh und Expiration"""

    @staticmethod
    def check_and_refresh_token(
        mail_account,
        client_id: str,
        client_secret: str,
        master_key: str | None = None,
        db_session=None,
    ):
        """Überprüft ob Token abgelaufen ist und erneuert falls nötig

        Args:
            mail_account: MailAccount Model instance
            client_id: Google OAuth Client ID
            client_secret: Google OAuth Client Secret
            master_key: Master-Key um Refresh-Token zu decrypten (optional wenn unverschlüsselt)
            db_session: SQLAlchemy Session für DB-Updates

        Returns:
            Boolean - True wenn Token gültig/erneuert, False bei Fehler
        """
        from datetime import datetime, timedelta

        if mail_account.oauth_provider != "google":
            return True

        if not mail_account.oauth_expires_at:
            return True

        now = datetime.now(UTC)
        if mail_account.oauth_expires_at > now + timedelta(minutes=5):
            return True

        if not mail_account.encrypted_oauth_refresh_token:
            logger.warning(f"Kein Refresh-Token für Account {mail_account.id}")
            return False

        encryption = importlib.import_module(".08_encryption", "src")

        refresh_token = mail_account.encrypted_oauth_refresh_token
        if master_key:
            try:
                refresh_token = encryption.CredentialManager.decrypt_imap_password(
                    mail_account.encrypted_oauth_refresh_token, master_key
                )
            except Exception as e:
                logger.error(f"Refresh-Token Decryption Fehler: {e}")
                return False

        token_data = GoogleOAuthManager.refresh_access_token(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )

        if not token_data:
            logger.error(f"Token Refresh fehlgeschlagen für Account {mail_account.id}")
            return False

        new_access_token = token_data.get("access_token")
        new_expires_in = token_data.get("expires_in", 3600)

        new_expires_at = datetime.now(UTC) + timedelta(seconds=new_expires_in)

        encrypted_token = new_access_token
        if master_key:
            try:
                encrypted_token = encryption.CredentialManager.encrypt_imap_password(
                    new_access_token, master_key
                )
            except Exception as e:
                logger.error(f"Token Encryption Fehler: {e}")
                return False

        mail_account.encrypted_oauth_token = encrypted_token
        mail_account.oauth_expires_at = new_expires_at

        if db_session:
            db_session.commit()
            logger.info(f"✅ OAuth Token erneuert für Account {mail_account.id}")

        return True


class GoogleMailFetcher:
    """Holt Mails von Gmail via Google API (OAuth)"""

    def __init__(self, access_token: str):
        """
        Initialisiert Gmail API Client

        Args:
            access_token: Google OAuth Access Token
        """
        self.access_token = access_token
        self.base_url = "https://www.googleapis.com/gmail/v1"

    def _make_request(
        self, endpoint: str, method: str = "GET", data: Dict | None = None
    ) -> Optional[Dict]:
        """Macht authenticated Request zu Gmail API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            url = f"{self.base_url}{endpoint}"

            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=10)
            else:
                return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Gmail API Request Fehler: {e}")
            return None

    def fetch_new_emails(self, limit: int = 50) -> list:
        """Holt neue (ungelesene) Mails von Gmail

        Args:
            limit: Max. Anzahl Mails

        Returns:
            Liste von Email-Dicts mit id, threadId, snippet, headers
        """
        try:
            query = "is:unread"
            endpoint = f"/users/me/messages?q={query}&maxResults={limit}"

            result = self._make_request(endpoint)

            if not result or "messages" not in result:
                logger.info("ℹ️ Keine neuen Mails gefunden")
                return []

            messages = result["messages"]
            logger.info(f"📧 {len(messages)} neue Mails gefunden")

            emails = []
            for msg in messages:
                email_data = self._fetch_message(msg["id"])
                if email_data:
                    emails.append(email_data)

            return emails

        except Exception as e:
            logger.error(f"❌ Fehler beim Mail-Abruf: {e}")
            return []

    def _fetch_message(self, message_id: str) -> Optional[Dict]:
        """Holt vollständige Message von Gmail

        Returns:
            Dict mit id, threadId, snippet, senderEmail, subject, body, receivedAt
        """
        try:
            endpoint = f"/users/me/messages/{message_id}"
            msg = self._make_request(endpoint)

            if not msg:
                return None

            headers = msg.get("payload", {}).get("headers", [])
            header_dict = {h["name"]: h["value"] for h in headers}

            sender = header_dict.get("From", "")
            subject = header_dict.get("Subject", "")
            date_str = header_dict.get("Date", "")

            body = self._extract_body(msg.get("payload", {}))

            try:
                from email.utils import parsedate_to_datetime

                received_at = parsedate_to_datetime(date_str)
            except Exception as e:
                logger.debug(f"Failed to parse date '{date_str}': {e}")
                received_at = datetime.now(UTC)

            return {
                "uid": msg["id"],  # Gmail Message ID als UID
                "id": msg["id"],  # Für Backward-Kompatibilität
                "threadId": msg.get("threadId"),
                "sender": sender,
                "subject": subject,
                "body": body,
                "received_at": received_at,
                "snippet": msg.get("snippet", ""),
                "imap_uid": None,  # Gmail API hat keine IMAP UIDs
                "imap_folder": "INBOX",  # Standard für Gmail API
                "imap_flags": None,  # Gmail API nutzt Labels statt IMAP Flags
            }

        except Exception as e:
            logger.error(f"⚠️ Fehler bei Message {message_id}: {e}")
            return None

    def _extract_body(self, payload: Dict) -> str:
        """Extrahiert Text-Body aus Message Payload"""
        try:
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        data = part.get("body", {}).get("data")
                        if data:
                            import base64

                            return base64.urlsafe_b64decode(data + "==").decode(
                                "utf-8", errors="ignore"
                            )
            else:
                data = payload.get("body", {}).get("data")
                if data:
                    import base64

                    return base64.urlsafe_b64decode(data + "==").decode(
                        "utf-8", errors="ignore"
                    )

            return ""

        except Exception as e:
            logger.error(f"Body extraction error: {e}")
            return ""
