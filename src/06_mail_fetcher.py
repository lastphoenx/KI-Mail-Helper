"""
Mail Helper - Mail Fetcher (IMAP + OAuth)
Holt E-Mails von IMAP-Servern (GMX, Gmail, etc.) & Google OAuth
"""

import imaplib
import email
from email.header import decode_header
from datetime import datetime
from typing import List, Dict, Optional
import os
import importlib
import re
import logging

logger = logging.getLogger(__name__)


class MailFetcher:
    """IMAP-Client zum Abholen von E-Mails"""
    
    def __init__(self, server: str, username: str, password: str, port: int = 993):
        """
        Initialisiert IMAP-Verbindung
        
        Args:
            server: IMAP-Server (z.B. "imap.gmx.net")
            username: E-Mail-Adresse
            password: Passwort
            port: IMAP-Port (Standard: 993 für SSL)
        """
        # Input Validation (Security Fix - Layer 2 Review)
        if not server or not isinstance(server, str) or not server.strip():
            raise ValueError("Server must be a non-empty string")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got: {port}")
        if not username or not isinstance(username, str):
            raise ValueError("Username must be a non-empty string")
        if not password or not isinstance(password, str):
            raise ValueError("Password must be a non-empty string")
        
        self.server = server.strip()
        self.username = username
        self.password = password
        self.port = port
        self.connection: Optional[imaplib.IMAP4_SSL] = None
    
    def connect(self):
        """Stellt Verbindung zum IMAP-Server her"""
        try:
            self.connection = imaplib.IMAP4_SSL(self.server, self.port)
            self.connection.login(self.username, self.password)
            print(f"✅ Verbunden mit {self.server}")
        except Exception as e:
            # Security Fix: Don't expose credentials in error messages
            logger.debug(f"Connection error details: {e}")  # Debug only
            print(f"❌ Verbindungsfehler: Authentifizierung fehlgeschlagen")
            raise ConnectionError("IMAP connection failed") from None
    
    def disconnect(self):
        """Schließt IMAP-Verbindung"""
        if self.connection:
            try:
                self.connection.logout()
                print("🔌 Verbindung geschlossen")
            except Exception as e:
                logger.debug(f"Error closing IMAP connection: {e}")
    
    def fetch_new_emails(self, folder: str = "INBOX", limit: int = 50) -> List[Dict]:
        """
        Holt E-Mails (readonly - markiert nicht als gelesen)
        Nutzt UID-Tracking für Deduplication in der DB
        
        Args:
            folder: IMAP-Ordner (Standard: "INBOX")
            limit: Max. Anzahl Mails (die neuesten)
        
        Returns:
            Liste von E-Mail-Dicts mit uid, sender, subject, body, received_at, imap_uid, imap_folder, imap_flags
        """
        if not self.connection:
            self.connect()
        
        try:
            # Ordner im readonly-Modus auswählen (nicht als gelesen markieren!)
            self.connection.select(folder, readonly=True)
            
            # Hole ALLE Mails (DB dedupliziert per UID)
            status, messages = self.connection.search(None, 'ALL')
            
            if status != 'OK':
                print("⚠️  Keine Mails gefunden")
                return []
            
            mail_ids = messages[0].split()
            # Neueste zuerst (reverse)
            mail_ids = list(reversed(mail_ids))
            # Limit anwenden
            mail_ids = mail_ids[:limit]
            
            print(f"📧 {len(mail_ids)} Mails gefunden")
            
            emails = []
            for mail_id in mail_ids:
                email_data = self._fetch_email_by_id(mail_id, folder)
                if email_data:
                    emails.append(email_data)
            
            return emails
            
        except Exception as e:
            # Security Fix: Don't expose sensitive data in error messages
            logger.debug(f"Fetch error details: {e}")  # Debug only
            print(f"❌ Fehler beim Abrufen: Operation fehlgeschlagen")
            return []
    
    def _fetch_email_by_id(self, mail_id: bytes, folder: str = "INBOX") -> Optional[Dict]:
        """Holt eine einzelne E-Mail mit IMAP-Flags"""
        try:
            status, msg_data = self.connection.fetch(mail_id, '(RFC822 FLAGS UID)')
            
            if status != 'OK':
                return None
            
            # Metadaten parsen (Flags + UID)
            meta = msg_data[0][0]
            meta_str = meta.decode('utf-8', errors='ignore')
            
            imap_flags = self._parse_imap_flags(meta_str)
            imap_uid = self._parse_imap_uid(meta_str)
            
            # E-Mail parsen
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Header dekodieren
            subject = self._decode_header(msg.get('Subject', ''))
            sender = self._decode_header(msg.get('From', ''))
            date_str = msg.get('Date', '')
            
            # Body extrahieren
            body = self._extract_body(msg)
            
            # Datum parsen
            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except Exception as e:
                logger.debug(f"Failed to parse date '{date_str}': {e}")
                received_at = datetime.now()
            
            return {
                'uid': mail_id.decode(),
                'sender': sender,
                'subject': subject,
                'body': body,
                'received_at': received_at,
                'imap_uid': imap_uid,
                'imap_folder': folder,
                'imap_flags': imap_flags
            }
            
        except Exception as e:
            # Security Fix: Don't expose mail content in error messages
            logger.debug(f"Fetch mail error for ID {mail_id}: {e}")  # Debug only
            print(f"⚠️  Fehler bei Mail-ID {mail_id}: Abruf fehlgeschlagen")
            return None
    
    def _decode_header(self, header: str) -> str:
        """Dekodiert E-Mail-Header (Betreff, Absender)"""
        if not header:
            return ""
        
        decoded_parts = decode_header(header)
        result = []
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                result.append(part)
        
        return ' '.join(result)
    
    def _extract_body(self, msg) -> str:
        """Extrahiert Text-Body aus E-Mail"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                
                # Nur Text-Parts
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        body += payload.decode(charset, errors='ignore')
                    except Exception as e:
                        logger.debug(f"Failed to decode text/plain payload: {e}")
        else:
            # Einfache (nicht-multipart) Mail
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='ignore')
            except Exception as e:
                logger.debug(f"Failed to decode email payload, falling back to string: {e}")
                body = str(msg.get_payload())
        
        return body.strip()
    
    def _parse_imap_flags(self, meta_str: str) -> str:
        """Extrahiert IMAP-Flags aus Metadaten-String
        
        Beispiel Input: '123 (UID 999 FLAGS (\\Seen \\Answered))'
        Beispiel Output: '\\Seen \\Answered'
        """
        flags_match = re.search(r'FLAGS \((.*?)\)', meta_str)
        if flags_match:
            return flags_match.group(1).strip()
        return ''
    
    def _parse_imap_uid(self, meta_str: str) -> Optional[str]:
        """Extrahiert IMAP-UID aus Metadaten-String
        
        Beispiel Input: '123 (UID 999 FLAGS (\\Seen))'
        Beispiel Output: '999'
        """
        uid_match = re.search(r'UID (\d+)', meta_str)
        if uid_match:
            return uid_match.group(1)
        return None


def get_fetcher_from_env() -> MailFetcher:
    """
    Erstellt MailFetcher aus Umgebungsvariablen
    
    Benötigt:
        IMAP_SERVER, IMAP_USERNAME, IMAP_PASSWORD, IMAP_PORT (optional)
    """
    server = os.getenv('IMAP_SERVER')
    username = os.getenv('IMAP_USERNAME')
    password = os.getenv('IMAP_PASSWORD')
    port = int(os.getenv('IMAP_PORT', '993'))
    
    if not all([server, username, password]):
        raise ValueError("IMAP-Konfiguration fehlt in Umgebungsvariablen")
    
    return MailFetcher(server, username, password, port)


def get_mail_fetcher_for_account(mail_account, master_key: str = None):
    """Factory-Funktion: Erstellt passenden Fetcher für Account-Typ
    
    Unterstützt Multi-Auth:
    - auth_type="imap": Standard IMAP/SMTP
    - auth_type="oauth": OAuth 2.0 (Gmail, Outlook)
    - auth_type="pop3": POP3 (experimental)
    
    Args:
        mail_account: MailAccount Model-Instanz
        master_key: Encrypted Master-Key um Passwörter zu decrypten
        
    Returns:
        MailFetcher (IMAP), GoogleMailFetcher (OAuth) oder POP3MailFetcher
        
    Raises:
        ValueError: Bei fehlenden Credentials oder unbekanntem auth_type
    """
    encryption = importlib.import_module('.08_encryption', 'src')
    
    # Validiere Auth-Felder
    is_valid, error_msg = mail_account.validate_auth_fields()
    if not is_valid:
        raise ValueError(f"Invalid account configuration: {error_msg}")
    
    if not master_key:
        raise ValueError("Master-Key erforderlich für Credential Decryption")
    
    # OAuth-basierte Authentifizierung (Google, Microsoft)
    if mail_account.auth_type == "oauth":
        google_oauth = importlib.import_module('.10_google_oauth', 'src')
        
        decrypted_token = encryption.CredentialManager.decrypt_imap_password(
            mail_account.encrypted_oauth_token,
            master_key
        )
        
        if mail_account.oauth_provider == "google":
            return google_oauth.GoogleMailFetcher(access_token=decrypted_token)
        elif mail_account.oauth_provider == "microsoft":
            # TODO: Microsoft OAuth Fetcher implementieren
            raise NotImplementedError("Microsoft OAuth not yet implemented")
        else:
            raise ValueError(f"Unknown OAuth provider: {mail_account.oauth_provider}")
    
    # IMAP-basierte Authentifizierung
    elif mail_account.auth_type == "imap":
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            mail_account.encrypted_imap_password,
            master_key
        )
        
        return MailFetcher(
            server=mail_account.imap_server,
            username=mail_account.imap_username,
            password=imap_password,
            port=mail_account.imap_port
        )
    
    # POP3-basierte Authentifizierung (Experimental)
    elif mail_account.auth_type == "pop3":
        pop3_fetcher = importlib.import_module('.07_pop3_fetcher', 'src')
        
        pop3_password = encryption.CredentialManager.decrypt_imap_password(
            mail_account.encrypted_pop3_password,
            master_key
        )
        
        return pop3_fetcher.POP3MailFetcher(
            server=mail_account.pop3_server,
            username=mail_account.pop3_username,
            password=pop3_password,
            port=mail_account.pop3_port
        )
    
    else:
        raise ValueError(f"Unknown auth_type: {mail_account.auth_type}")


if __name__ == "__main__":
    try:
        fetcher = get_fetcher_from_env()
        fetcher.connect()
        
        emails = fetcher.fetch_new_emails(limit=5)
        
        print(f"\n=== {len(emails)} Mails abgerufen ===\n")
        for mail in emails:
            print(f"Von: {mail['sender']}")
            print(f"Betreff: {mail['subject']}")
            print(f"Datum: {mail['received_at']}")
            print(f"Body: {mail['body'][:100]}...")
            print("-" * 60)
        
        fetcher.disconnect()
        
    except Exception as e:
        print(f"❌ Fehler: {e}")
        print("\nSetze Umgebungsvariablen:")
        print("  IMAP_SERVER=imap.gmx.net")
        print("  IMAP_USERNAME=deine@email.de")
        print("  IMAP_PASSWORD=deinpasswort")
