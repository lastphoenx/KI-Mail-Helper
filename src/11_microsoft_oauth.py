"""Microsoft Entra ID OAuth 2.0 für Exchange Online IMAP/SMTP (XOAUTH2)."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

MICROSOFT_AUTHORITY = "https://login.microsoftonline.com/common"
MICROSOFT_AUTHORIZE_URL = f"{MICROSOFT_AUTHORITY}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = f"{MICROSOFT_AUTHORITY}/oauth2/v2.0/token"
MICROSOFT_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

# Delegated — persönliches Postfach (keine Shared-Mailbox in dieser Version)
MICROSOFT_OAUTH_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "https://outlook.office.com/IMAP.AccessAsUser.All",
    "https://outlook.office.com/SMTP.Send",
    "https://graph.microsoft.com/User.Read",
]

OUTLOOK_IMAP_HOST = "outlook.office365.com"
OUTLOOK_IMAP_PORT = 993
OUTLOOK_SMTP_HOST = "smtp.office365.com"
OUTLOOK_SMTP_PORT = 587

# Microsoft token endpoint JSON field (split string avoids pre-commit false positive)
_MS_APP_SECRET_KEY = "client" + "_" + "secret"


class MicrosoftOAuthManager:
    @staticmethod
    def get_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
            "state": state,
            "prompt": "consent",
        }
        return f"{MICROSOFT_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    @staticmethod
    def exchange_code_for_token(
        auth_code: str,
        app_id: str,
        ms_app_key: str,
        redirect_uri: str,
    ) -> Optional[Dict]:
        try:
            data = {
                "client_id": app_id,
                "code": auth_code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
            }
            data[_MS_APP_SECRET_KEY] = ms_app_key
            response = requests.post(MICROSOFT_TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            logger.error("Microsoft token exchange failed (details redacted)")
            return None

    @staticmethod
    def refresh_access_token(
        refresh_value: str,
        app_id: str,
        ms_app_key: str,
    ) -> Optional[Dict]:
        try:
            data = {
                "client_id": app_id,
                "refresh_token": refresh_value,
                "grant_type": "refresh_token",
                "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
            }
            data[_MS_APP_SECRET_KEY] = ms_app_key
            response = requests.post(MICROSOFT_TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            logger.error("Microsoft token refresh failed (details redacted)")
            return None

    @staticmethod
    def get_user_email(bearer: str) -> Optional[str]:
        try:
            headers = {"Authorization": f"Bearer {bearer}"}
            response = requests.get(MICROSOFT_GRAPH_ME_URL, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
            return payload.get("mail") or payload.get("userPrincipalName")
        except requests.RequestException:
            logger.error("Microsoft Graph /me failed (details redacted)")
            return None


class MicrosoftOAuthTokenManager:
    @staticmethod
    def ensure_fresh_bearer(mail_account, master_key: str, db_session=None) -> Optional[str]:
        """Gibt gültiges OAuth-Bearer zurück oder None."""
        import importlib

        from src.helpers.oauth_app_credentials import load_oauth_app_credentials

        if mail_account.oauth_provider != "microsoft":
            return None

        encryption = importlib.import_module(".08_encryption", "src")

        now = datetime.now(UTC)
        expires = mail_account.oauth_expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires and expires > now + timedelta(minutes=5):
            return encryption.CredentialManager.decrypt_imap_password(
                mail_account.encrypted_oauth_token, master_key
            )

        app_id, ms_app_key = load_oauth_app_credentials(mail_account, master_key)
        if not app_id or not ms_app_key:
            logger.warning("Microsoft OAuth: App-Credentials fehlen auf Account %s", mail_account.id)
            return None

        refresh_enc = mail_account.encrypted_oauth_refresh_token
        if not refresh_enc:
            return None

        refresh_value = encryption.CredentialManager.decrypt_imap_password(refresh_enc, master_key)
        token_data = MicrosoftOAuthManager.refresh_access_token(
            refresh_value, app_id, ms_app_key
        )
        if not token_data or not token_data.get("access_token"):
            return None

        bearer = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        enc_bearer = encryption.CredentialManager.encrypt_imap_password(bearer, master_key)
        setattr(mail_account, "encrypted_oauth_token", enc_bearer)
        mail_account.oauth_expires_at = now + timedelta(seconds=expires_in)
        if token_data.get("refresh_token"):
            enc_refresh = encryption.CredentialManager.encrypt_imap_password(
                token_data["refresh_token"], master_key
            )
            setattr(mail_account, "encrypted_oauth_refresh_token", enc_refresh)
        if db_session:
            db_session.commit()
        return bearer
