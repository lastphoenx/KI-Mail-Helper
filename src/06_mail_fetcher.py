"""
Mail Helper - Mail Fetcher (IMAP + OAuth)
Holt E-Mails von IMAP-Servern (GMX, Gmail, etc.) & Google OAuth
"""

import imaplib
import email
from email.header import decode_header
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import os
import importlib
import re
import logging
import json
import uuid

logger = logging.getLogger(__name__)


class ThreadCalculator:
    """Berechnet Thread-IDs aus verschiedenen Quellen (Phase 12)"""

    @staticmethod
    def from_message_id_chain(
        emails: Dict[str, Dict]
    ) -> Tuple[Dict[str, str], Dict[str, Optional[str]]]:
        """Berechnet Thread-IDs aus Message-ID Chain (In-Reply-To)

        Input: {
            'uid1': {'message_id': 'msg1@server', 'in_reply_to': None},
            'uid2': {'message_id': 'msg2@server', 'in_reply_to': 'msg1@server'},
            'uid3': {'message_id': 'msg3@server', 'in_reply_to': 'msg2@server'},
        }

        Returns:
            (thread_ids, parent_uids) Tuple mit:
            - thread_ids: {uid: thread_id, ...}
            - parent_uids: {uid: parent_uid or None, ...}
        """
        msg_id_to_uid = {}
        for uid, email_data in emails.items():
            if email_data.get('message_id'):
                msg_id_to_uid[email_data['message_id']] = uid

        thread_ids = {}
        parent_uids = {}
        thread_id_for_root = {}

        for uid, email_data in emails.items():
            initial_in_reply_to = email_data.get('in_reply_to')
            parent_uid = None

            if initial_in_reply_to:
                parent_uid = msg_id_to_uid.get(initial_in_reply_to)

            root_uid = (
                uid if not initial_in_reply_to
                else msg_id_to_uid.get(initial_in_reply_to)
            )

            in_reply_to = initial_in_reply_to
            visited = set()
            while in_reply_to and in_reply_to not in visited:
                visited.add(in_reply_to)
                current_uid = msg_id_to_uid.get(in_reply_to)

                if current_uid is None:
                    break

                root_uid = current_uid
                parent_email = emails.get(current_uid, {})
                in_reply_to = parent_email.get('in_reply_to')

            root_msg_id = emails.get(root_uid, {}).get('message_id')
            if root_msg_id not in thread_id_for_root:
                thread_id_for_root[root_msg_id] = str(uuid.uuid4())

            thread_ids[uid] = thread_id_for_root[root_msg_id]
            parent_uids[uid] = parent_uid

        return thread_ids, parent_uids

    @staticmethod
    def from_imap_thread_structure(
        thread_structure
    ) -> Dict[int, str]:
        """Berechnet Thread-IDs aus nested IMAP THREAD response

        IMAP THREAD response Struktur:
        - Top-level items sind separate Threads
        - Nested items sind Replies

        Input: (1, 2, (3, 4, (5)), 6)
        Bedeutung:
          - Thread 1: UID 1
          - Thread 2: UID 2
          - Thread 3: UIDs 3, 4, 5
          - Thread 4: UID 6

        Returns: {1: 'uuid-a', 2: 'uuid-b', 3: 'uuid-c', ...}
        """
        result = {}

        def process_items(items, current_thread_id=None):
            for item in items:
                if isinstance(item, (list, tuple)):
                    if current_thread_id is None:
                        current_thread_id = str(uuid.uuid4())
                    process_items(item, current_thread_id)
                else:
                    if current_thread_id is None:
                        current_thread_id = str(uuid.uuid4())
                    result[item] = current_thread_id
                    current_thread_id = None

        if isinstance(thread_structure, (list, tuple)):
            for item in thread_structure:
                if isinstance(item, (list, tuple)):
                    new_thread_id = str(uuid.uuid4())
                    process_items(item, new_thread_id)
                else:
                    new_thread_id = str(uuid.uuid4())
                    result[item] = new_thread_id
        else:
            result[thread_structure] = str(uuid.uuid4())

        return result


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
            logger.debug(f"Connection error details: {e}")
            print("❌ Verbindungsfehler: Authentifizierung fehlgeschlagen")
            raise ConnectionError("IMAP connection failed") from None

    def disconnect(self):
        """Schließt IMAP-Verbindung"""
        if self.connection:
            try:
                self.connection.logout()
                print("🔌 Verbindung geschlossen")
            except Exception as e:
                logger.debug(f"Error closing IMAP connection: {e}")

    def fetch_new_emails(
        self, folder: str = "INBOX", limit: int = 50
    ) -> List[Dict]:
        """
        Holt E-Mails mit Threadin-Informationen (Phase 12)

        Args:
            folder: IMAP-Ordner (Standard: "INBOX")
            limit: Max. Anzahl Mails (die neuesten)

        Returns:
            Liste von E-Mail-Dicts mit erweiterten Metadaten
        """
        if not self.connection:
            self.connect()

        try:
            conn = self.connection
            if conn is None:
                raise ConnectionError("IMAP connection failed")
            conn.select(folder, readonly=True)

            status, messages = conn.search(None, "ALL")

            if status != "OK":
                print("⚠️  Keine Mails gefunden")
                return []

            mail_ids = messages[0].split()
            mail_ids = list(reversed(mail_ids))
            mail_ids = mail_ids[:limit]

            print(f"📧 {len(mail_ids)} Mails gefunden")

            emails = []
            for mail_id in mail_ids:
                email_data = self._fetch_email_by_id(mail_id, folder)
                if email_data:
                    emails.append(email_data)

            if emails:
                self._calculate_thread_ids(emails)

            return emails

        except Exception as e:
            logger.debug(f"Fetch error details: {e}")
            print("❌ Fehler beim Abrufen: Operation fehlgeschlagen")
            return []

    def _calculate_thread_ids(self, emails: List[Dict]) -> None:
        """Berechnet Thread-IDs für alle geholten E-Mails

        Modifiziert die emails List in-place um thread_id & parent_uid zu setzen
        """
        email_dict = {email['uid']: email for email in emails}

        thread_ids, parent_uids = ThreadCalculator.from_message_id_chain(
            email_dict
        )

        for email_item in emails:
            uid = email_item['uid']
            email_item['thread_id'] = thread_ids.get(uid)
            email_item['parent_uid'] = parent_uids.get(uid)

    def _fetch_email_by_id(
        self, mail_id: bytes, folder: str = "INBOX"
    ) -> Optional[Dict]:
        """Holt eine einzelne E-Mail mit erweiterten Metadaten (Phase 12)"""
        try:
            if self.connection is None:
                return None
            conn = self.connection
            mail_id_str = mail_id.decode(errors="ignore")
            status, msg_data = conn.fetch(mail_id_str, "(RFC822 FLAGS UID)")

            if status != "OK":
                return None

            meta = msg_data[0][0]
            meta_str = meta.decode("utf-8", errors="ignore")

            imap_flags = self._parse_imap_flags(meta_str)
            imap_uid = self._parse_imap_uid(meta_str)
            flags_dict = self._parse_flags_dict(imap_flags)

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = self._decode_header(msg.get("Subject", ""))
            sender = self._decode_header(msg.get("From", ""))
            date_str = msg.get("Date", "")

            body = self._extract_body(msg)

            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except Exception as e:
                logger.debug(f"Failed to parse date '{date_str}': {e}")
                received_at = datetime.now()

            envelope = self._parse_envelope(msg)

            return {
                "uid": mail_id_str,
                "sender": sender,
                "subject": subject,
                "body": body,
                "received_at": received_at,
                "imap_uid": imap_uid,
                "imap_folder": folder,
                "imap_flags": imap_flags,
                "message_id": envelope.get("message_id"),
                "in_reply_to": envelope.get("in_reply_to"),
                "to": envelope.get("to"),
                "cc": envelope.get("cc"),
                "bcc": envelope.get("bcc"),
                "reply_to": envelope.get("reply_to"),
                "references": envelope.get("references"),
                "message_size": envelope.get("message_size"),
                "content_type": envelope.get("content_type"),
                "charset": envelope.get("charset"),
                "has_attachments": envelope.get("has_attachments"),
                "imap_is_seen": flags_dict.get("imap_is_seen"),
                "imap_is_answered": flags_dict.get("imap_is_answered"),
                "imap_is_flagged": flags_dict.get("imap_is_flagged"),
                "imap_is_deleted": flags_dict.get("imap_is_deleted"),
                "imap_is_draft": flags_dict.get("imap_is_draft"),
                "thread_id": None,
                "parent_uid": None,
            }

        except Exception as e:
            logger.debug(
                f"Fetch mail error for ID {mail_id.decode(errors='ignore')}: {e}"
            )
            print(
                f"⚠️  Fehler bei Mail-ID {mail_id.decode(errors='ignore')}: "
                f"Abruf fehlgeschlagen"
            )
            return None

    def _decode_header(self, header: str) -> str:
        """Dekodiert E-Mail-Header (Betreff, Absender)"""
        if not header:
            return ""

        decoded_parts = decode_header(header)
        result = []

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="ignore"))
            else:
                result.append(part)

        return " ".join(result)

    def _extract_body(self, msg) -> str:
        """Extrahiert Text-Body aus E-Mail"""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()

                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body += payload.decode(charset, errors="ignore")
                    except Exception as e:
                        logger.debug(f"Failed to decode text/plain payload: {e}")
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="ignore")
            except Exception as e:
                logger.debug(
                    f"Failed to decode email payload, falling back to string: {e}"
                )
                body = str(msg.get_payload())

        return body.strip()

    def _parse_envelope(self, msg) -> Dict:
        """Extrahiert erweiterte Envelope-Daten aus RFC822-Message

        Returns:
            Dict mit message_id, in_reply_to, references, to, cc, bcc, reply_to,
            message_size, content_type, charset, has_attachments
        """
        try:
            envelope = {}

            envelope["message_id"] = self._extract_message_id(msg)
            envelope["in_reply_to"] = self._extract_in_reply_to(msg)
            envelope["references"] = self._extract_references(msg)
            envelope["to"] = self._extract_address_list(msg, "To")
            envelope["cc"] = self._extract_address_list(msg, "Cc")
            envelope["bcc"] = self._extract_address_list(msg, "Bcc")
            envelope["reply_to"] = self._extract_address_list(msg, "Reply-To")
            envelope["message_size"] = self._estimate_message_size(msg)
            envelope["content_type"] = msg.get_content_type()
            envelope["charset"] = msg.get_content_charset() or "utf-8"
            envelope["has_attachments"] = self._detect_attachments(msg)

            return envelope
        except Exception as e:
            logger.debug(f"Error parsing envelope: {e}")
            return {}

    def _extract_message_id(self, msg) -> Optional[str]:
        """Extrahiert Message-ID Header (RFC 5322)"""
        try:
            msg_id = msg.get("Message-ID", "").strip()
            if msg_id:
                msg_id = msg_id.strip("<>")
                if "@" in msg_id:
                    return msg_id
        except Exception as e:
            logger.debug(f"Error extracting Message-ID: {e}")
        return None

    def _extract_in_reply_to(self, msg) -> Optional[str]:
        """Extrahiert In-Reply-To Header (RFC 5322)"""
        try:
            in_reply = msg.get("In-Reply-To", "").strip()
            if in_reply:
                in_reply = in_reply.strip("<>")
                if "@" in in_reply:
                    return in_reply
        except Exception as e:
            logger.debug(f"Error extracting In-Reply-To: {e}")
        return None

    def _extract_references(self, msg) -> Optional[str]:
        """Extrahiert References Header (RFC 5322)"""
        try:
            refs = msg.get("References", "").strip()
            if refs:
                return refs
        except Exception as e:
            logger.debug(f"Error extracting References: {e}")
        return None

    def _extract_address_list(self, msg, header: str) -> Optional[str]:
        """Extrahiert Adressliste aus Header (To, Cc, Bcc, Reply-To)

        Returns: JSON string mit List von {name, email} dicts
        """
        try:
            from email.utils import parseaddr

            addresses_str = msg.get(header, "").strip()
            if not addresses_str:
                return None

            addresses = []
            for item in addresses_str.split(","):
                item = item.strip()
                if item:
                    name, email_addr = parseaddr(item)
                    if email_addr:
                        addresses.append({
                            "name": name.strip() or email_addr,
                            "email": email_addr
                        })

            return json.dumps(addresses) if addresses else None
        except Exception as e:
            logger.debug(f"Error extracting address list from {header}: {e}")
            return None

    def _estimate_message_size(self, msg) -> int:
        """Schätzt Nachrichtengröße in Bytes"""
        try:
            return len(msg.as_bytes())
        except Exception as e:
            logger.debug(f"Error estimating message size: {e}")
            return 0

    def _detect_attachments(self, msg) -> bool:
        """Erkennt ob die Nachricht Anhänge hat"""
        try:
            if not msg.is_multipart():
                return False

            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" in content_disposition:
                    return True
            return False
        except Exception as e:
            logger.debug(f"Error detecting attachments: {e}")
            return False

    def _parse_flags_dict(self, imap_flags: str) -> Dict[str, bool]:
        """Konvertiert IMAP-Flags String zu Dictionary mit boolean Werten

        Beispiel Input: '\\Seen \\Answered \\Flagged'
        Beispiel Output: {
            'imap_is_seen': True,
            'imap_is_answered': True,
            'imap_is_flagged': True,
            'imap_is_deleted': False,
            'imap_is_draft': False
        }
        """
        flags_dict = {
            "imap_is_seen": False,
            "imap_is_answered": False,
            "imap_is_flagged": False,
            "imap_is_deleted": False,
            "imap_is_draft": False,
        }

        if not imap_flags:
            return flags_dict

        flags_lower = imap_flags.lower()

        if "\\seen" in flags_lower:
            flags_dict["imap_is_seen"] = True
        if "\\answered" in flags_lower:
            flags_dict["imap_is_answered"] = True
        if "\\flagged" in flags_lower:
            flags_dict["imap_is_flagged"] = True
        if "\\deleted" in flags_lower:
            flags_dict["imap_is_deleted"] = True
        if "\\draft" in flags_lower:
            flags_dict["imap_is_draft"] = True

        return flags_dict

    def _parse_imap_flags(self, meta_str: str) -> str:
        """Extrahiert IMAP-Flags aus Metadaten-String

        Beispiel Input: '123 (UID 999 FLAGS (\\Seen \\Answered))'
        Beispiel Output: '\\Seen \\Answered'
        """
        flags_match = re.search(r"FLAGS \((.*?)\)", meta_str)
        if flags_match:
            return flags_match.group(1).strip()
        return ""

    def _parse_imap_uid(self, meta_str: str) -> Optional[str]:
        """Extrahiert IMAP-UID aus Metadaten-String

        Beispiel Input: '123 (UID 999 FLAGS (\\Seen))'
        Beispiel Output: '999'
        """
        uid_match = re.search(r"UID (\d+)", meta_str)
        if uid_match:
            return uid_match.group(1)
        return None


def get_fetcher_from_env() -> MailFetcher:
    """
    Erstellt MailFetcher aus Umgebungsvariablen

    Benötigt:
        IMAP_SERVER, IMAP_USERNAME, IMAP_PASSWORD, IMAP_PORT (optional)
    """
    server = os.getenv("IMAP_SERVER")
    username = os.getenv("IMAP_USERNAME")
    password = os.getenv("IMAP_PASSWORD")
    port = int(os.getenv("IMAP_PORT", "993"))

    if not all([server, username, password]):
        raise ValueError("IMAP-Konfiguration fehlt in Umgebungsvariablen")

    return MailFetcher(server, username, password, port)


def get_mail_fetcher_for_account(mail_account, master_key: str | None = None):
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
    encryption = importlib.import_module(".08_encryption", "src")

    is_valid, error_msg = mail_account.validate_auth_fields()
    if not is_valid:
        raise ValueError(f"Invalid account configuration: {error_msg}")

    if not master_key:
        raise ValueError("Master-Key erforderlich für Credential Decryption")

    if mail_account.auth_type == "oauth":
        google_oauth = importlib.import_module(".10_google_oauth", "src")

        decrypted_token = encryption.CredentialManager.decrypt_imap_password(
            mail_account.encrypted_oauth_token, master_key
        )

        if mail_account.oauth_provider == "google":
            return google_oauth.GoogleMailFetcher(access_token=decrypted_token)
        elif mail_account.oauth_provider == "microsoft":
            raise NotImplementedError("Microsoft OAuth not yet implemented")
        else:
            raise ValueError(f"Unknown OAuth provider: {mail_account.oauth_provider}")

    elif mail_account.auth_type == "imap":
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            mail_account.encrypted_imap_password, master_key
        )

        return MailFetcher(
            server=mail_account.imap_server,
            username=mail_account.imap_username,
            password=imap_password,
            port=mail_account.imap_port,
        )

    elif mail_account.auth_type == "pop3":
        pop3_fetcher = importlib.import_module(".07_pop3_fetcher", "src")

        pop3_password = encryption.CredentialManager.decrypt_imap_password(
            mail_account.encrypted_pop3_password, master_key
        )

        return pop3_fetcher.POP3MailFetcher(
            server=mail_account.pop3_server,
            username=mail_account.pop3_username,
            password=pop3_password,
            port=mail_account.pop3_port,
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
