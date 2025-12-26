"""
Mail Helper - POP3 Fetcher (Future Support)
Holt E-Mails von POP3-Servern
"""

import poplib
import email
from email.header import decode_header
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class POP3MailFetcher:
    """POP3-Client zum Abholen von E-Mails (Stub für zukünftige Implementation)"""
    
    def __init__(self, server: str, username: str, password: str, port: int = 995, use_ssl: bool = True):
        """
        Initialisiert POP3-Verbindung
        
        Args:
            server: POP3-Server (z.B. "pop.gmx.net")
            username: E-Mail-Adresse
            password: Passwort
            port: POP3-Port (Standard: 995 für SSL, 110 für unverschlüsselt)
            use_ssl: Ob SSL verwendet werden soll
        """
        self.server = server
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.connection: Optional[poplib.POP3_SSL | poplib.POP3] = None
    
    def connect(self):
        """Stellt Verbindung zum POP3-Server her"""
        try:
            if self.use_ssl:
                self.connection = poplib.POP3_SSL(self.server, self.port)
            else:
                self.connection = poplib.POP3(self.server, self.port)
            
            self.connection.user(self.username)
            self.connection.pass_(self.password)
            
            logger.info(f"✅ POP3 verbunden mit {self.server}")
        except Exception as e:
            logger.error(f"❌ POP3 Verbindungsfehler: {e}")
            raise
    
    def disconnect(self):
        """Schließt POP3-Verbindung"""
        if self.connection:
            try:
                self.connection.quit()
                logger.info("🔌 POP3 Verbindung geschlossen")
            except Exception as e:
                logger.debug(f"Error closing POP3 connection: {e}")
    
    def fetch_new_emails(self, limit: int = 50, delete_after_fetch: bool = False) -> List[Dict]:
        """
        Holt E-Mails von POP3-Server
        
        WARNUNG: POP3 löscht standardmäßig Mails nach dem Abrufen!
        
        Args:
            limit: Max. Anzahl Mails
            delete_after_fetch: Ob Mails nach Abruf gelöscht werden sollen
        
        Returns:
            Liste von E-Mail-Dicts mit uid, sender, subject, body, received_at
        """
        if not self.connection:
            self.connect()
        
        try:
            # Anzahl Mails abrufen
            num_messages = len(self.connection.list()[1])
            logger.info(f"📧 {num_messages} Mails auf Server gefunden")
            
            if num_messages == 0:
                return []
            
            # Limit anwenden
            fetch_count = min(num_messages, limit)
            
            emails = []
            # POP3 nummeriert Mails von 1 bis N
            for i in range(1, fetch_count + 1):
                email_data = self._fetch_email_by_id(i)
                if email_data:
                    emails.append(email_data)
            
            # Optional: Mails löschen
            if delete_after_fetch:
                for i in range(1, fetch_count + 1):
                    self.connection.dele(i)
                logger.warning(f"🗑️  {fetch_count} Mails vom Server gelöscht!")
            
            return emails
            
        except Exception as e:
            logger.error(f"❌ POP3 Fehler beim Abrufen: {e}")
            return []
    
    def _fetch_email_by_id(self, mail_id: int) -> Optional[Dict]:
        """Holt eine einzelne E-Mail von POP3"""
        try:
            # Hole komplette Mail
            response, lines, octets = self.connection.retr(mail_id)
            
            # Konvertiere zu bytes und parse
            raw_email = b'\r\n'.join(lines)
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
            
            # POP3 hat keine UIDs wie IMAP, verwende Message-ID
            message_id = msg.get('Message-ID', f'pop3_{mail_id}')
            
            return {
                'uid': message_id,
                'sender': sender,
                'subject': subject,
                'body': body,
                'received_at': received_at
            }
            
        except Exception as e:
            logger.error(f"⚠️  POP3 Fehler bei Mail-ID {mail_id}: {e}")
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


if __name__ == "__main__":
    # Test-Code (benötigt Umgebungsvariablen)
    import os
    
    try:
        server = os.getenv('POP3_SERVER')
        username = os.getenv('POP3_USERNAME')
        password = os.getenv('POP3_PASSWORD')
        port = int(os.getenv('POP3_PORT', '995'))
        
        if not all([server, username, password]):
            print("❌ POP3 Konfiguration fehlt in Umgebungsvariablen")
            print("\nSetze:")
            print("  POP3_SERVER=pop.example.com")
            print("  POP3_USERNAME=user@example.com")
            print("  POP3_PASSWORD=password")
            exit(1)
        
        fetcher = POP3MailFetcher(server, username, password, port)
        fetcher.connect()
        
        # ACHTUNG: delete_after_fetch=False für Tests!
        emails = fetcher.fetch_new_emails(limit=5, delete_after_fetch=False)
        
        print(f"\n=== {len(emails)} Mails abgerufen ===\n")
        for mail in emails:
            print(f"Von: {mail['sender']}")
            print(f"Betreff: {mail['subject']}")
            print(f"Datum: {mail['received_at']}")
            print(f"Body: {mail['body'][:100]}...")
            print("-" * 60)
        
        fetcher.disconnect()
        
    except Exception as e:
        logger.error(f"❌ Fehler: {e}")
