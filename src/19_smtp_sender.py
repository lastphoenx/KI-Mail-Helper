"""
SMTP Sender Module - Phase H (Mail-Versand)
Versendet Emails mit korrektem Threading und synchronisiert mit IMAP.

Features:
- RFC 2822 konforme Message-ID Generierung
- Threading via In-Reply-To und References Header
- Automatisches Speichern im Sent-Ordner via IMAP APPEND
- Lokale DB-Synchronisation für konsistente Ansicht
- Zero-Knowledge: Alle Daten verschlüsselt gespeichert

Integration: Phase H - Ausgehender Mail-Versand
Status: PRODUCTION READY
"""

import smtplib
import ssl
import logging
import uuid
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate, make_msgid, formataddr, parseaddr
from datetime import datetime, UTC
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import importlib

from imapclient import IMAPClient

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

class SMTPEncryption(Enum):
    """SMTP Verschlüsselungstypen"""
    SSL = "SSL"           # Port 465 - direkte SSL-Verbindung
    STARTTLS = "STARTTLS" # Port 587 - STARTTLS Upgrade
    NONE = "NONE"         # Port 25 - unverschlüsselt (nicht empfohlen)


@dataclass
class EmailRecipient:
    """Email-Empfänger mit optionalem Display-Namen"""
    email: str
    name: Optional[str] = None
    
    def to_header(self) -> str:
        """Formatiert für Email-Header: 'Name <email>' oder 'email'"""
        if self.name:
            return formataddr((self.name, self.email))
        return self.email
    
    @classmethod
    def from_string(cls, addr_string: str) -> 'EmailRecipient':
        """Parst 'Name <email>' oder 'email' Format"""
        name, email = parseaddr(addr_string)
        return cls(email=email, name=name if name else None)


@dataclass
class EmailAttachment:
    """Email-Anhang"""
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


@dataclass
class OutgoingEmail:
    """Ausgehende Email mit allen Metadaten"""
    # Pflichtfelder
    to: List[EmailRecipient]
    subject: str
    body_text: str
    
    # Optionale Felder
    body_html: Optional[str] = None
    cc: List[EmailRecipient] = field(default_factory=list)
    bcc: List[EmailRecipient] = field(default_factory=list)
    attachments: List[EmailAttachment] = field(default_factory=list)
    
    # Threading (für Antworten)
    in_reply_to: Optional[str] = None      # Message-ID der Original-Mail
    references: Optional[str] = None        # Komplette Reference-Chain
    thread_subject: Optional[str] = None    # Original-Betreff ohne Re:
    
    # Wird beim Senden gesetzt
    message_id: Optional[str] = None
    sent_at: Optional[datetime] = None


@dataclass
class SendResult:
    """Ergebnis eines Email-Versands"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    
    # IMAP-Sync Ergebnis
    saved_to_sent: bool = False
    sent_folder: Optional[str] = None
    imap_uid: Optional[int] = None
    imap_uidvalidity: Optional[int] = None
    
    # DB-Sync Ergebnis
    saved_to_db: bool = False
    db_email_id: Optional[int] = None


# ============================================================================
# SMTP SENDER SERVICE
# ============================================================================

class SMTPSender:
    """
    SMTP Sender mit Threading-Support und IMAP-Synchronisation.
    
    Verwendung:
        sender = SMTPSender(mail_account, master_key)
        
        # Neue Email senden
        result = sender.send_email(OutgoingEmail(
            to=[EmailRecipient("empfaenger@example.com", "Max Mustermann")],
            subject="Test",
            body_text="Hallo Welt!"
        ))
        
        # Antwort senden (mit Threading)
        result = sender.send_reply(
            original_email=raw_email,  # RawEmail aus DB
            reply_text="Danke für Ihre Nachricht...",
        )
    """
    
    # Bekannte Sent-Ordner Namen pro Provider
    SENT_FOLDER_NAMES = [
        "Sent",           # Standard (Englisch)
        "INBOX.Sent",     # Dovecot-Style
        "Gesendet",       # Deutsch
        "INBOX.Gesendet",
        "Sent Items",     # Outlook
        "Sent Messages",  # Apple
        "[Gmail]/Sent Mail",  # Gmail
        "[Gmail]/Gesendet",   # Gmail Deutsch
    ]
    
    def __init__(self, mail_account, master_key: str):
        """
        Initialisiert den SMTP Sender.
        
        Args:
            mail_account: MailAccount Model-Instanz mit SMTP-Credentials
            master_key: Master-Key zum Entschlüsseln der Credentials
        """
        self.mail_account = mail_account
        self.master_key = master_key
        self._credentials: Optional[Dict[str, Any]] = None
        self._sent_folder: Optional[str] = None
    
    @property
    def credentials(self) -> Dict[str, Any]:
        """Lazy-Load und Cache der entschlüsselten Credentials"""
        if self._credentials is None:
            self._credentials = self._decrypt_credentials()
        return self._credentials
    
    def _decrypt_credentials(self) -> Dict[str, Any]:
        """Entschlüsselt SMTP und IMAP Credentials"""
        # Import hier um Circular Import zu vermeiden
        encryption = importlib.import_module(".08_encryption", "src")
        EncryptionManager = encryption.EncryptionManager
        
        # SMTP Credentials
        smtp_server = None
        smtp_username = None
        smtp_password = None
        
        if self.mail_account.encrypted_smtp_server:
            smtp_server = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_smtp_server, 
                self.master_key
            )
        
        if self.mail_account.encrypted_smtp_username:
            smtp_username = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_smtp_username,
                self.master_key
            )
        
        if self.mail_account.encrypted_smtp_password:
            smtp_password = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_smtp_password,
                self.master_key
            )
        
        # Fallback: SMTP Username/Password = IMAP Username/Password
        if not smtp_username and self.mail_account.encrypted_imap_username:
            smtp_username = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_imap_username,
                self.master_key
            )
        
        if not smtp_password and self.mail_account.encrypted_imap_password:
            smtp_password = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_imap_password,
                self.master_key
            )
        
        # IMAP Credentials (für Sent-Ordner Sync)
        imap_server = None
        imap_username = None
        imap_password = None
        
        if self.mail_account.encrypted_imap_server:
            imap_server = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_imap_server,
                self.master_key
            )
        
        if self.mail_account.encrypted_imap_username:
            imap_username = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_imap_username,
                self.master_key
            )
        
        if self.mail_account.encrypted_imap_password:
            imap_password = EncryptionManager.decrypt_data(
                self.mail_account.encrypted_imap_password,
                self.master_key
            )
        
        return {
            "smtp_server": smtp_server,
            "smtp_port": self.mail_account.smtp_port or 587,
            "smtp_username": smtp_username,
            "smtp_password": smtp_password,
            "smtp_encryption": self.mail_account.smtp_encryption or "STARTTLS",
            "imap_server": imap_server,
            "imap_port": self.mail_account.imap_port or 993,
            "imap_username": imap_username,
            "imap_password": imap_password,
            "from_email": smtp_username or imap_username,
            "from_name": self.mail_account.name,
        }
    
    def validate_configuration(self) -> Tuple[bool, str]:
        """
        Prüft ob alle nötigen SMTP-Credentials vorhanden sind.
        
        Returns:
            (is_valid, error_message)
        """
        creds = self.credentials
        
        if not creds.get("smtp_server"):
            return False, "SMTP-Server nicht konfiguriert"
        
        if not creds.get("smtp_username"):
            return False, "SMTP-Benutzername nicht konfiguriert"
        
        if not creds.get("smtp_password"):
            return False, "SMTP-Passwort nicht konfiguriert"
        
        if not creds.get("from_email"):
            return False, "Absender-Adresse nicht konfiguriert"
        
        return True, ""
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Testet die SMTP-Verbindung ohne Email zu senden.
        
        Returns:
            (success, message)
        """
        is_valid, error = self.validate_configuration()
        if not is_valid:
            return False, error
        
        try:
            with self._get_smtp_connection() as smtp:
                # NOOP Kommando um Verbindung zu testen
                smtp.noop()
                return True, f"SMTP-Verbindung zu {self.credentials['smtp_server']} erfolgreich"
        except smtplib.SMTPAuthenticationError as e:
            return False, f"Authentifizierung fehlgeschlagen: {e}"
        except smtplib.SMTPException as e:
            return False, f"SMTP-Fehler: {e}"
        except Exception as e:
            return False, f"Verbindungsfehler: {e}"
    
    def _get_smtp_connection(self) -> smtplib.SMTP:
        """
        Erstellt eine SMTP-Verbindung basierend auf Encryption-Typ.
        
        Returns:
            Authentifizierte SMTP-Verbindung
        """
        creds = self.credentials
        server = creds["smtp_server"]
        port = creds["smtp_port"]
        encryption = creds["smtp_encryption"]
        
        logger.debug(f"SMTP-Verbindung: {server}:{port} ({encryption})")
        
        # SSL-Kontext für sichere Verbindungen
        context = ssl.create_default_context()
        
        if encryption == "SSL":
            # Direkte SSL-Verbindung (Port 465)
            smtp = smtplib.SMTP_SSL(server, port, context=context, timeout=30)
        else:
            # Normale Verbindung, optional STARTTLS
            smtp = smtplib.SMTP(server, port, timeout=30)
            smtp.ehlo()
            
            if encryption == "STARTTLS":
                smtp.starttls(context=context)
                smtp.ehlo()
        
        # Authentifizierung
        smtp.login(creds["smtp_username"], creds["smtp_password"])
        
        return smtp
    
    def _generate_message_id(self) -> str:
        """
        Generiert eine RFC 2822 konforme Message-ID.
        
        Format: <uuid@hostname>
        """
        # Hostname für Message-ID
        try:
            hostname = socket.getfqdn()
        except:
            hostname = "localhost"
        
        # Falls Hostname nicht verfügbar, Domain aus Email nehmen
        if hostname == "localhost" and self.credentials.get("from_email"):
            email = self.credentials["from_email"]
            if "@" in email:
                hostname = email.split("@")[1]
        
        unique_id = uuid.uuid4().hex[:16]
        return f"<{unique_id}.{int(datetime.now(UTC).timestamp())}@{hostname}>"
    
    def _build_mime_message(self, email: OutgoingEmail) -> MIMEMultipart:
        """
        Baut eine MIME-Nachricht mit allen Headern und Inhalten.
        
        Args:
            email: OutgoingEmail mit allen Daten
            
        Returns:
            Fertige MIMEMultipart-Nachricht
        """
        creds = self.credentials
        
        # Basis-Message (multipart/alternative für Text+HTML, sonst multipart/mixed)
        if email.attachments:
            msg = MIMEMultipart("mixed")
            
            # Text/HTML als alternative Teil
            if email.body_html:
                alt_part = MIMEMultipart("alternative")
                alt_part.attach(MIMEText(email.body_text, "plain", "utf-8"))
                alt_part.attach(MIMEText(email.body_html, "html", "utf-8"))
                msg.attach(alt_part)
            else:
                msg.attach(MIMEText(email.body_text, "plain", "utf-8"))
        else:
            if email.body_html:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(email.body_text, "plain", "utf-8"))
                msg.attach(MIMEText(email.body_html, "html", "utf-8"))
            else:
                msg = MIMEMultipart()
                msg.attach(MIMEText(email.body_text, "plain", "utf-8"))
        
        # === PFLICHT-HEADER ===
        
        # Message-ID generieren falls nicht vorhanden
        if not email.message_id:
            email.message_id = self._generate_message_id()
        msg["Message-ID"] = email.message_id
        
        # Absender
        from_addr = formataddr((creds.get("from_name", ""), creds["from_email"]))
        msg["From"] = from_addr
        
        # Empfänger
        msg["To"] = ", ".join(r.to_header() for r in email.to)
        
        if email.cc:
            msg["Cc"] = ", ".join(r.to_header() for r in email.cc)
        
        # BCC wird NICHT in den Header geschrieben (sonst wäre es nicht "blind")
        
        # Betreff
        msg["Subject"] = email.subject
        
        # Datum
        msg["Date"] = formatdate(localtime=True)
        
        # === THREADING-HEADER (RFC 2822 / RFC 5322) ===
        
        if email.in_reply_to:
            msg["In-Reply-To"] = email.in_reply_to
        
        if email.references:
            msg["References"] = email.references
        elif email.in_reply_to:
            # Falls keine References aber In-Reply-To: References = In-Reply-To
            msg["References"] = email.in_reply_to
        
        # === ZUSÄTZLICHE HEADER ===
        
        # MIME-Version
        msg["MIME-Version"] = "1.0"
        
        # X-Mailer (optional, für Debugging)
        msg["X-Mailer"] = "KI-Mail-Helper/1.0"
        
        # === ANHÄNGE ===
        
        for attachment in email.attachments:
            part = MIMEBase(*attachment.mime_type.split("/", 1))
            part.set_payload(attachment.content)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename=\"{attachment.filename}\""
            )
            msg.attach(part)
        
        return msg
    
    def send_email(
        self,
        email: OutgoingEmail,
        save_to_sent: bool = True,
        save_to_db: bool = True
    ) -> SendResult:
        """
        Sendet eine Email via SMTP.
        
        Args:
            email: OutgoingEmail mit allen Daten
            save_to_sent: Email im Sent-Ordner speichern (via IMAP)
            save_to_db: Email in lokaler DB speichern
            
        Returns:
            SendResult mit Erfolg/Fehler und IDs
        """
        # Validierung
        is_valid, error = self.validate_configuration()
        if not is_valid:
            return SendResult(success=False, error=error)
        
        if not email.to:
            return SendResult(success=False, error="Keine Empfänger angegeben")
        
        # MIME-Nachricht bauen
        try:
            msg = self._build_mime_message(email)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der MIME-Nachricht: {e}")
            return SendResult(success=False, error=f"Message-Build-Fehler: {e}")
        
        # Alle Empfänger sammeln (To + Cc + Bcc)
        all_recipients = [r.email for r in email.to]
        all_recipients.extend(r.email for r in email.cc)
        all_recipients.extend(r.email for r in email.bcc)
        
        # SMTP-Versand
        try:
            with self._get_smtp_connection() as smtp:
                smtp.send_message(msg, to_addrs=all_recipients)
                email.sent_at = datetime.now(UTC)
                
                logger.info(
                    f"✉️ Email gesendet: {email.subject[:50]}... "
                    f"an {len(all_recipients)} Empfänger "
                    f"(Message-ID: {email.message_id})"
                )
        except smtplib.SMTPRecipientsRefused as e:
            return SendResult(
                success=False,
                error=f"Empfänger abgelehnt: {e.recipients}"
            )
        except smtplib.SMTPException as e:
            return SendResult(success=False, error=f"SMTP-Fehler: {e}")
        except Exception as e:
            logger.error(f"Unerwarteter SMTP-Fehler: {e}")
            return SendResult(success=False, error=str(e))
        
        # Ergebnis initialisieren
        result = SendResult(
            success=True,
            message_id=email.message_id
        )
        
        # Im Sent-Ordner speichern (via IMAP APPEND)
        if save_to_sent:
            try:
                sent_result = self._save_to_sent_folder(msg)
                result.saved_to_sent = sent_result.get("success", False)
                result.sent_folder = sent_result.get("folder")
                result.imap_uid = sent_result.get("uid")
                result.imap_uidvalidity = sent_result.get("uidvalidity")
            except Exception as e:
                logger.warning(f"Fehler beim Speichern im Sent-Ordner: {e}")
                # Kein Fehler im Result, Email wurde trotzdem gesendet
        
        # In lokaler DB speichern
        if save_to_db:
            try:
                db_result = self._save_to_database(email, msg, result)
                result.saved_to_db = db_result.get("success", False)
                result.db_email_id = db_result.get("email_id")
            except Exception as e:
                logger.warning(f"Fehler beim Speichern in DB: {e}")
        
        return result
    
    def send_reply(
        self,
        original_email,  # RawEmail Model
        reply_text: str,
        reply_html: Optional[str] = None,
        include_quote: bool = True,
        attachments: Optional[List[EmailAttachment]] = None,
        cc: Optional[List[EmailRecipient]] = None,
        save_to_sent: bool = True,
        save_to_db: bool = True
    ) -> SendResult:
        """
        Sendet eine Antwort auf eine bestehende Email mit korrektem Threading.
        
        Args:
            original_email: RawEmail aus der Datenbank
            reply_text: Antwort-Text (Plain Text)
            reply_html: Antwort-HTML (optional)
            include_quote: Original-Text zitieren
            attachments: Anhänge
            cc: CC-Empfänger
            save_to_sent: Im Sent-Ordner speichern
            save_to_db: In DB speichern
            
        Returns:
            SendResult
        """
        encryption = importlib.import_module(".08_encryption", "src")
        EncryptionManager = encryption.EncryptionManager
        
        # Original-Email entschlüsseln
        try:
            original_sender = EncryptionManager.decrypt_data(
                original_email.encrypted_sender,
                self.master_key
            )
            original_subject = EncryptionManager.decrypt_data(
                original_email.encrypted_subject,
                self.master_key
            )
            original_body = EncryptionManager.decrypt_data(
                original_email.encrypted_body,
                self.master_key
            ) if include_quote else None
        except Exception as e:
            return SendResult(
                success=False,
                error=f"Entschlüsselung fehlgeschlagen: {e}"
            )
        
        # Empfänger = Original-Absender
        recipient = EmailRecipient.from_string(original_sender)
        
        # Betreff mit Re: Prefix
        if original_subject:
            if not original_subject.lower().startswith("re:"):
                subject = f"Re: {original_subject}"
            else:
                subject = original_subject
        else:
            subject = "Re: (kein Betreff)"
        
        # Body mit Zitat erstellen
        if include_quote and original_body:
            # Zitierter Text formatieren
            quoted_lines = []
            for line in original_body.split("\n"):
                quoted_lines.append(f"> {line}")
            quoted_text = "\n".join(quoted_lines)
            
            full_body = f"{reply_text}\n\n---\nAm {original_email.received_at.strftime('%d.%m.%Y um %H:%M')} schrieb {original_sender}:\n\n{quoted_text}"
            
            # HTML-Version mit Zitat
            if reply_html:
                full_html = f"""
                {reply_html}
                <br><br>
                <hr>
                <p style="color: #666;">
                    Am {original_email.received_at.strftime('%d.%m.%Y um %H:%M')} schrieb {original_sender}:
                </p>
                <blockquote style="border-left: 2px solid #ccc; margin-left: 10px; padding-left: 10px; color: #666;">
                    {original_body.replace(chr(10), '<br>')}
                </blockquote>
                """
            else:
                full_html = None
        else:
            full_body = reply_text
            full_html = reply_html
        
        # Threading-Header vorbereiten
        in_reply_to = original_email.message_id
        
        # References-Chain aufbauen
        # Format: <original_references> <in_reply_to>
        if hasattr(original_email, 'references') and original_email.references:
            references = f"{original_email.references} {in_reply_to}"
        else:
            references = in_reply_to
        
        # OutgoingEmail erstellen
        outgoing = OutgoingEmail(
            to=[recipient],
            cc=cc or [],
            subject=subject,
            body_text=full_body,
            body_html=full_html,
            in_reply_to=in_reply_to,
            references=references,
            thread_subject=original_subject,
            attachments=attachments or []
        )
        
        return self.send_email(
            outgoing,
            save_to_sent=save_to_sent,
            save_to_db=save_to_db
        )
    
    def _find_sent_folder(self, imap: IMAPClient) -> Optional[str]:
        """
        Findet den Sent-Ordner auf dem IMAP-Server.
        
        Versucht bekannte Namen und erkennt Special-Use Flag \\Sent
        """
        if self._sent_folder:
            return self._sent_folder
        
        try:
            folders = imap.list_folders()
            
            # 1. Erst nach Special-Use Flag \\Sent suchen
            for flags, delimiter, name in folders:
                if b'\\Sent' in flags:
                    self._sent_folder = name
                    logger.debug(f"Sent-Ordner via Flag gefunden: {name}")
                    return name
            
            # 2. Nach bekannten Namen suchen
            folder_names = [name for _, _, name in folders]
            
            for candidate in self.SENT_FOLDER_NAMES:
                if candidate in folder_names:
                    self._sent_folder = candidate
                    logger.debug(f"Sent-Ordner via Name gefunden: {candidate}")
                    return candidate
            
            # 3. Fallback: Case-insensitive Suche
            for name in folder_names:
                if name.lower() in ["sent", "gesendet", "sent items"]:
                    self._sent_folder = name
                    logger.debug(f"Sent-Ordner via Case-Insensitive gefunden: {name}")
                    return name
            
            logger.warning("Kein Sent-Ordner gefunden")
            return None
            
        except Exception as e:
            logger.error(f"Fehler beim Suchen des Sent-Ordners: {e}")
            return None
    
    def _save_to_sent_folder(self, msg: MIMEMultipart) -> Dict[str, Any]:
        """
        Speichert die gesendete Email im Sent-Ordner via IMAP APPEND.
        
        Args:
            msg: Die MIME-Nachricht
            
        Returns:
            Dict mit success, folder, uid
        """
        creds = self.credentials
        
        if not creds.get("imap_server"):
            return {"success": False, "error": "IMAP nicht konfiguriert"}
        
        try:
            # IMAP-Verbindung
            context = ssl.create_default_context()
            
            with IMAPClient(
                creds["imap_server"],
                port=creds["imap_port"],
                ssl=True,
                ssl_context=context
            ) as imap:
                imap.login(creds["imap_username"], creds["imap_password"])
                
                # Sent-Ordner finden
                sent_folder = self._find_sent_folder(imap)
                if not sent_folder:
                    return {"success": False, "error": "Sent-Ordner nicht gefunden"}
                
                # Email als String
                msg_bytes = msg.as_bytes()
                
                # APPEND mit Flags (\Seen = gelesen)
                # Rückgabe: (uidvalidity, [uid]) bei UIDPLUS
                append_result = imap.append(
                    sent_folder,
                    msg_bytes,
                    flags=[b'\\Seen'],
                    msg_time=datetime.now()
                )
                
                # APPENDUID parsen falls verfügbar
                uid = None
                uidvalidity = None
                
                if append_result and isinstance(append_result, tuple):
                    # Format: (uidvalidity, [uid]) bei UIDPLUS
                    if len(append_result) >= 2:
                        uidvalidity = append_result[0]  # Erste Element ist UIDVALIDITY
                        uid_list = append_result[1]     # Zweites Element ist UID-Liste
                        if uid_list and len(uid_list) > 0:
                            uid = uid_list[0]
                
                # Fallback: Wenn Server kein UIDPLUS hat, uidvalidity per SELECT holen
                if uidvalidity is None:
                    try:
                        folder_status = imap.folder_status(sent_folder, ['UIDVALIDITY'])
                        raw_val = folder_status.get(b'UIDVALIDITY')
                        # IMAPClient gibt manchmal [value] zurück
                        if isinstance(raw_val, (list, tuple)) and len(raw_val) > 0:
                            uidvalidity = raw_val[0]
                        elif raw_val is not None:
                            uidvalidity = raw_val
                        logger.debug(f"UIDVALIDITY via folder_status: {uidvalidity} (raw: {raw_val})")
                    except Exception as e:
                        logger.warning(f"Konnte UIDVALIDITY nicht holen: {e}")
                
                logger.info(f"📁 Email im Sent-Ordner gespeichert: {sent_folder} (UID: {uid}, UIDVALIDITY: {uidvalidity})")
                
                return {
                    "success": True,
                    "folder": sent_folder,
                    "uid": uid,
                    "uidvalidity": uidvalidity
                }
                
        except Exception as e:
            logger.error(f"Fehler beim IMAP APPEND: {e}")
            return {"success": False, "error": str(e)}
    
    def _save_to_database(
        self,
        email: OutgoingEmail,
        msg: MIMEMultipart,
        send_result: SendResult
    ) -> Dict[str, Any]:
        """
        Speichert die gesendete Email in der lokalen Datenbank.
        
        Args:
            email: OutgoingEmail
            msg: MIME-Nachricht
            send_result: Bisheriges Ergebnis
            
        Returns:
            Dict mit success, email_id
        """
        models = importlib.import_module(".02_models", "src")
        encryption = importlib.import_module(".08_encryption", "src")
        web_app = importlib.import_module(".01_web_app", "src")
        
        RawEmail = models.RawEmail
        ProcessedEmail = models.ProcessedEmail
        EncryptionManager = encryption.EncryptionManager
        SessionLocal = web_app.SessionLocal
        
        try:
            # Import session factory
            db = SessionLocal()
            
            # Empfänger als String
            recipients = ", ".join(r.to_header() for r in email.to)
            
            # RawEmail erstellen (als "gesendet" markiert)
            raw_email = RawEmail(
                user_id=self.mail_account.user_id,
                mail_account_id=self.mail_account.id,
                
                # Verschlüsselte Inhalte
                encrypted_sender=EncryptionManager.encrypt_data(
                    self.credentials["from_email"],
                    self.master_key
                ),
                encrypted_subject=EncryptionManager.encrypt_data(email.subject, self.master_key),
                encrypted_body=EncryptionManager.encrypt_data(email.body_text, self.master_key),
                
                # IMAP-Metadaten (falls via APPEND gespeichert)
                imap_folder=send_result.sent_folder or "Sent",
                imap_uid=send_result.imap_uid,
                imap_uidvalidity=send_result.imap_uidvalidity,  # UIDVALIDITY aus APPEND
                imap_is_seen=True,
                
                # Email-Metadaten
                message_id=email.message_id,
                encrypted_in_reply_to=EncryptionManager.encrypt_data(
                    email.in_reply_to or "",
                    self.master_key
                ) if email.in_reply_to else None,
                encrypted_references=EncryptionManager.encrypt_data(
                    email.references or "",
                    self.master_key
                ) if email.references else None,
                
                # Empfänger (verschlüsselt speichern)
                encrypted_to=EncryptionManager.encrypt_data(recipients, self.master_key),
                
                # Timestamps
                received_at=email.sent_at or datetime.now(UTC),
                
                # Flags
                imap_has_attachments=len(email.attachments) > 0 if email.attachments else False
            )
            
            db.add(raw_email)
            db.flush()  # Um ID zu bekommen
            
            # ProcessedEmail erstellen (minimale KI-Verarbeitung für Suche)
            processed = ProcessedEmail(
                raw_email_id=raw_email.id,
                user_id=self.mail_account.user_id,
                
                # Minimale Klassifizierung für gesendete Mails
                score=5,
                kategorie_aktion="info",
                spam_flag=False,
                dringlichkeit=1,
                wichtigkeit=1,
                
                # Zusammenfassung (eigene Mail = kein Summary nötig)
                encrypted_summary_de=EncryptionManager.encrypt_data(
                    f"Gesendet an {recipients}",
                    self.master_key
                )
            )
            
            db.add(processed)
            db.commit()
            
            email_id = raw_email.id
            db.close()
            
            logger.info(f"💾 Email in DB gespeichert: ID {email_id}")
            
            return {
                "success": True,
                "email_id": email_id
            }
            
        except Exception as e:
            if 'db' in locals():
                db.rollback()
                db.close()
            logger.error(f"Fehler beim DB-Speichern: {e}")
            return {"success": False, "error": str(e)}


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_smtp_sender(mail_account, master_key: str) -> SMTPSender:
    """
    Factory-Funktion für SMTPSender.
    
    Args:
        mail_account: MailAccount Model-Instanz
        master_key: Master-Key für Credential-Entschlüsselung
        
    Returns:
        Konfigurierter SMTPSender
    """
    return SMTPSender(mail_account, master_key)


def send_reply_to_email(
    raw_email,           # RawEmail Model
    reply_text: str,
    master_key: str,
    reply_html: Optional[str] = None,
    include_quote: bool = True
) -> SendResult:
    """
    Convenience-Funktion: Sendet eine Antwort auf eine Email.
    
    Args:
        raw_email: RawEmail aus der Datenbank
        reply_text: Antwort-Text
        master_key: Master-Key
        reply_html: Optional HTML-Version
        include_quote: Original zitieren
        
    Returns:
        SendResult
    """
    models = importlib.import_module(".02_models", "src")
    web_app = importlib.import_module(".01_web_app", "src")
    
    MailAccount = models.MailAccount
    SessionLocal = web_app.SessionLocal
    
    # Mail-Account laden
    # Import session factory
    db = SessionLocal()
    account = db.query(MailAccount).get(raw_email.mail_account_id)
    db.close()
    
    if not account:
        return SendResult(success=False, error="Mail-Account nicht gefunden")
    
    # Sender erstellen und Antwort senden
    sender = SMTPSender(account, master_key)
    return sender.send_reply(
        original_email=raw_email,
        reply_text=reply_text,
        reply_html=reply_html,
        include_quote=include_quote
    )


def send_new_email(
    mail_account,
    master_key: str,
    to: List[str],
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    cc: Optional[List[str]] = None,
    attachments: Optional[List[Dict]] = None
) -> SendResult:
    """
    Convenience-Funktion: Sendet eine neue Email.
    
    Args:
        mail_account: MailAccount Model
        master_key: Master-Key
        to: Liste von Empfänger-Adressen
        subject: Betreff
        body: Text-Body
        body_html: Optional HTML-Body
        cc: Optional CC-Adressen
        attachments: Optional Liste von {"filename": str, "content": bytes, "mime_type": str}
        
    Returns:
        SendResult
    """
    sender = SMTPSender(mail_account, master_key)
    
    # Empfänger parsen
    recipients = [EmailRecipient.from_string(addr) for addr in to]
    cc_recipients = [EmailRecipient.from_string(addr) for addr in (cc or [])]
    
    # Anhänge konvertieren
    email_attachments = []
    if attachments:
        for att in attachments:
            email_attachments.append(EmailAttachment(
                filename=att["filename"],
                content=att["content"],
                mime_type=att.get("mime_type", "application/octet-stream")
            ))
    
    # Email erstellen und senden
    email = OutgoingEmail(
        to=recipients,
        cc=cc_recipients,
        subject=subject,
        body_text=body,
        body_html=body_html,
        attachments=email_attachments
    )
    
    return sender.send_email(email)
