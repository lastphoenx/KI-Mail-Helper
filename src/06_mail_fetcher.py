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


def decode_imap_folder_name(folder_name: str) -> str:
    """Dekodiert IMAP UTF-7 Ordnernamen zu UTF-8
    
    IMAP nutzt modified UTF-7 für Ordnernamen (RFC 3501):
    - 'Entw&APw-rfe' → 'Entwürfe'
    - 'Gel&APY-scht' → 'Gelöscht'
    
    Args:
        folder_name: IMAP folder name in UTF-7
        
    Returns:
        UTF-8 decoded folder name
    """
    try:
        # Python's decode mit 'imap4-utf-7' unterstützt modified UTF-7
        import codecs
        # Registriere IMAP4-UTF-7 codec falls nicht vorhanden
        try:
            codecs.lookup('imap4-utf-7')
        except LookupError:
            # Fallback: manuelles Decoding
            return folder_name.replace('&APw-', 'ü').replace('&APY-', 'ö').replace('&AOQ-', 'ä').replace('&ANY-', 'Ä').replace('&APY-', 'Ö').replace('&APs-', 'Ü')
        
        # Decode UTF-7
        return folder_name.encode('latin1').decode('imap4-utf-7')
    except Exception as e:
        logger.debug(f"Konnte Ordnername nicht dekodieren: {folder_name} - {e}")
        return folder_name


def encode_imap_folder_name(folder_name: str) -> str:
    """Enkodiert UTF-8 Ordnernamen zu IMAP UTF-7
    
    Umkehrfunktion zu decode_imap_folder_name():
    - 'Entwürfe' → 'Entw&APw-rfe'
    - 'Gelöscht' → 'Gel&APY-scht'
    
    Args:
        folder_name: UTF-8 folder name
        
    Returns:
        IMAP UTF-7 encoded folder name
    """
    try:
        import codecs
        try:
            codecs.lookup('imap4-utf-7')
            # Encode UTF-7
            return folder_name.encode('imap4-utf-7').decode('latin1')
        except LookupError:
            # Fallback: manuelles Encoding
            return folder_name.replace('ü', '&APw-').replace('ö', '&APY-').replace('ä', '&AOQ-').replace('Ä', '&ANY-').replace('Ö', '&APY-').replace('Ü', '&APs-')
    except Exception as e:
        logger.debug(f"Konnte Ordnername nicht enkodieren: {folder_name} - {e}")
        return folder_name


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

            # BUG-001-FIX: Wenn parent nicht in unserer DB, starte eigenen Thread
            if initial_in_reply_to and parent_uid is None:
                # External parent → eigener Thread statt None-Collision
                root_uid = uid
            elif initial_in_reply_to:
                # Parent bekannt, trace zurück zur Root
                root_uid = parent_uid
            else:
                # Keine In-Reply-To → ist selbst Root
                root_uid = uid

            # Trace zur Root (falls parent_uid bekannt war)
            in_reply_to = initial_in_reply_to
            visited = set()
            while in_reply_to and in_reply_to not in visited:
                visited.add(in_reply_to)
                current_uid = msg_id_to_uid.get(in_reply_to)

                if current_uid is None:
                    # Parent nicht in DB → stop tracing
                    break

                root_uid = current_uid
                parent_email = emails.get(current_uid, {})
                in_reply_to = parent_email.get('in_reply_to')

            # root_uid ist jetzt garantiert nicht None!
            root_msg_id = emails.get(root_uid, {}).get('message_id')
            
            # Fallback wenn message_id fehlt (sollte nicht passieren, aber defensiv)
            if not root_msg_id:
                root_msg_id = f"fallback_{root_uid}"
            
            if root_msg_id not in thread_id_for_root:
                thread_id_for_root[root_msg_id] = str(uuid.uuid4())

            thread_ids[uid] = thread_id_for_root[root_msg_id]
            parent_uids[uid] = parent_uid

        return thread_ids, parent_uids

    @staticmethod
    def from_imap_thread_structure(
        thread_structure
    ) -> Dict[int, str]:
        """Berechnet Thread-IDs aus nested IMAP THREAD response (RFC 5256)

        thread-member = thread-node *(SP thread-list)
        - Node mit weiteren nested lists = gleicher Thread
        - Flache list mit mehreren nodes = separate Thread von dem node davor

        Input: (1, (2, (3, (4, (5))))) → node 1 + deeply nested list → 1 Thread
        Input: (1, (2, 3, 4))         → node 1 + flat list → 2 Threads (1 separate, (2,3,4) separate)

        Returns: {1: 'uuid-a', 2: 'uuid-b', 3: 'uuid-c', ...}
        """
        result = {}

        def is_deeply_nested(structure):
            """Check if structure contains further nested tuples (not just ints)"""
            if not isinstance(structure, (list, tuple)):
                return False
            for item in structure:
                if isinstance(item, (list, tuple)):
                    return True
            return False

        def flatten_and_assign(items, thread_id: str):
            for item in items:
                if isinstance(item, (list, tuple)):
                    flatten_and_assign(item, thread_id)
                else:
                    result[item] = thread_id

        if isinstance(thread_structure, (list, tuple)):
            i = 0
            while i < len(thread_structure):
                item = thread_structure[i]
                thread_id = str(uuid.uuid4())
                
                if isinstance(item, int):
                    result[item] = thread_id
                    # Check if next item is a deeply nested list
                    if (i + 1 < len(thread_structure) and 
                        isinstance(thread_structure[i + 1], (list, tuple)) and
                        is_deeply_nested(thread_structure[i + 1])):
                        # Deeply nested list = same thread as node
                        flatten_and_assign(thread_structure[i + 1], thread_id)
                        i += 1
                else:
                    # Pure nested structure
                    flatten_and_assign(item, thread_id)
                
                i += 1
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
    
    def _invalidate_folder(self, session, account_id: int, folder: str) -> None:
        """Phase 14b: Invalidiert alle Emails eines Ordners bei UIDVALIDITY-Change
        
        RFC 3501: "If UIDVALIDITY changes, the client MUST empty its cache of
        that mailbox and get new UIDs."
        
        Args:
            session: SQLAlchemy Session
            account_id: MailAccount-ID
            folder: IMAP Folder name (UTF-8 decoded)
        """
        from src import models_02 as models
        from datetime import datetime, UTC
        
        # Soft-Delete aller Emails dieses Folders
        deleted_count = (
            session.query(models.RawEmail)
            .filter_by(
                mail_account_id=account_id,
                imap_folder=folder,
            )
            .filter(models.RawEmail.deleted_at.is_(None))
            .update({
                'deleted_at': datetime.now(UTC)
            })
        )
        
        session.commit()
        logger.warning(
            f"🗑️  UIDVALIDITY CHANGE: {deleted_count} Emails in {folder} invalidiert"
        )

    def fetch_new_emails(
        self, 
        folder: str = "INBOX", 
        limit: int = 50,
        # Phase 13C Part 2: Server-Side Filtering
        since: Optional[datetime] = None,
        before: Optional[datetime] = None,
        unseen_only: bool = False,
        flagged_only: bool = False,
        # Phase 13C Part 4: Delta-Sync UID-Range
        uid_range: Optional[str] = None,
        # Phase 14b: UIDVALIDITY Support
        account_id: Optional[int] = None,
        session = None,
    ) -> List[Dict]:
        """
        Holt E-Mails mit Threading-Informationen (Phase 12)
        + Server-Side Filtering (Phase 13C Part 2)
        + Delta-Sync (Phase 13C Part 4)
        + UIDVALIDITY-Check (Phase 14b)

        Args:
            folder: IMAP-Ordner (Standard: "INBOX")
            limit: Max. Anzahl Mails (die neuesten)
            since: Nur Mails nach diesem Datum (IMAP SEARCH SINCE)
            before: Nur Mails vor diesem Datum (IMAP SEARCH BEFORE)
            unseen_only: Nur ungelesene Mails (IMAP SEARCH UNSEEN)
            flagged_only: Nur geflaggte Mails (IMAP SEARCH FLAGGED)
            uid_range: UID-Range für Delta-Sync (z.B. "123:*" = alle ab UID 123)
            account_id: MailAccount-ID für UIDVALIDITY-Check (Phase 14b)
            session: SQLAlchemy Session für UIDVALIDITY-Lookup (Phase 14b)

        Returns:
            Liste von E-Mail-Dicts mit erweiterten Metadaten
        """
        if not self.connection:
            self.connect()

        try:
            conn = self.connection
            if conn is None:
                raise ConnectionError("IMAP connection failed")
            
            # Phase 14b: SELECT folder → UIDVALIDITY extrahieren
            status, folder_info = conn.select(folder, readonly=True)
            if status != "OK":
                print(f"⚠️  Ordner {folder} nicht gefunden")
                return []
            
            # UIDVALIDITY vom Server (in untagged responses nach SELECT)
            # imaplib speichert untagged responses in conn.untagged_responses dict
            server_uidvalidity = None
            import re
            
            # DEBUG: Log folder_info structure
            logger.debug(f"SELECT {folder}: status={status}, folder_info={folder_info}")
            
            # 1) Prüfe untagged responses (primär bei imaplib)
            # GMX, Yahoo und die meisten Server geben UIDVALIDITY hier zurück
            try:
                untagged = getattr(conn, 'untagged_responses', {})
                logger.debug(f"Untagged responses keys: {list(untagged.keys())}")
                
                # UIDVALIDITY ist typischerweise in 'OK' responses
                # Format: [b'[UIDVALIDITY 1352540700] UIDs valid']
                if 'OK' in untagged and untagged['OK']:
                    for resp in untagged['OK']:
                        resp_str = resp.decode('utf-8', errors='ignore') if isinstance(resp, bytes) else str(resp)
                        if 'UIDVALIDITY' in resp_str:
                            match = re.search(r'UIDVALIDITY\s+(\d+)', resp_str)
                            if match:
                                server_uidvalidity = int(match.group(1))
                                logger.debug(f"✅ UIDVALIDITY from untagged['OK']: {server_uidvalidity}")
                                break
            except Exception as e:
                logger.debug(f"Could not parse untagged responses: {e}")
            
            # 2) Fallback: Prüfe folder_info (manche Server geben es dort)
            if not server_uidvalidity and isinstance(folder_info, list):
                for response in folder_info:
                    if isinstance(response, bytes):
                        response_str = response.decode('utf-8', errors='ignore')
                        if 'UIDVALIDITY' in response_str:
                            match = re.search(r'UIDVALIDITY\s+(\d+)', response_str)
                            if match:
                                server_uidvalidity = int(match.group(1))
                                logger.debug(f"✅ UIDVALIDITY from folder_info: {server_uidvalidity}")
                                break
            
            # 3) Letzter Fallback: Ohne UIDVALIDITY weitermachen (suboptimal)
            if not server_uidvalidity:
                logger.warning(
                    f"⚠️  Konnte UIDVALIDITY für {folder} nicht abrufen! "
                    f"SELECT response: {folder_info}, untagged: {list(getattr(conn, 'untagged_responses', {}).keys())}"
                )
                # Continue ohne UIDVALIDITY (Mails werden skipped in persistence)
            
            # Phase 14b: UIDVALIDITY-Check wenn account_id + session gegeben
            if account_id and session and server_uidvalidity:
                from src import models_02 as models
                
                account = session.query(models.MailAccount).get(account_id)
                if account:
                    db_uidvalidity = account.get_uidvalidity(folder)
                    
                    if db_uidvalidity and db_uidvalidity != server_uidvalidity:
                        # UIDVALIDITY hat sich geändert! → Ordner invalidieren
                        logger.warning(
                            f"⚠️  UIDVALIDITY CHANGED: {folder} "
                            f"(DB: {db_uidvalidity} → Server: {server_uidvalidity})"
                        )
                        self._invalidate_folder(session, account_id, folder)
                    
                    # UIDVALIDITY speichern (auch beim ersten Mal)
                    account.set_uidvalidity(folder, server_uidvalidity)
                    session.commit()
            
            # E-Mails mit UIDVALIDITY anreichern
            folder_uidvalidity = server_uidvalidity
            # Phase 14b FIX: Setze als Instance-Variable für _fetch_email_by_id()
            self._current_folder_uidvalidity = folder_uidvalidity

            # Phase 13C Part 4: Delta-Sync via UID-Range
            search_criteria = []  # Initialisiere immer (auch für uid_range Branch)
            
            if uid_range:
                # UID-Range suche: z.B. "123:*" = alle Mails ab UID 123
                status, messages = conn.uid('search', None, f"UID {uid_range}")
            else:
                # Phase 13C Part 2: Build IMAP SEARCH criteria
                if unseen_only:
                    search_criteria.append("UNSEEN")
                
                if flagged_only:
                    search_criteria.append("FLAGGED")
                
                if since:
                    # IMAP date format: DD-Mon-YYYY (e.g., "01-Jan-2024")
                    date_str = since.strftime("%d-%b-%Y")
                    search_criteria.append(f"SINCE {date_str}")
                
                if before:
                    date_str = before.strftime("%d-%b-%Y")
                    search_criteria.append(f"BEFORE {date_str}")
                
                # Build final search string
                search_string = " ".join(search_criteria) if search_criteria else "ALL"

                # BUG-002-FIX: Nutze UID-basierte Suche (stabil nach EXPUNGE)
                status, messages = conn.uid('search', None, search_string)

            if status != "OK":
                print("⚠️  Keine Mails gefunden")
                return []

            mail_ids = messages[0].split()
            
            # Phase 13C Part 4 FIX: Leeres Ergebnis ist OK (keine neuen Mails)
            # Bei Delta-Sync mit UID-Range kann messages[0] leer sein = keine neuen Mails
            if not mail_ids:
                if uid_range:
                    # Bei Delta-Sync: Keine neuen Mails ist normal
                    print(f"📧 0 Mails gefunden (keine neuen seit UID {uid_range.split(':')[0]})")
                else:
                    print("📧 0 Mails gefunden")
                return []
            
            mail_ids = list(reversed(mail_ids))
            mail_ids = mail_ids[:limit]

            if not uid_range and search_criteria:
                print(f"🔍 Filter: {search_string}")
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
        """Holt eine einzelne E-Mail mit erweiterten Metadaten (Phase 12)
        
        FINDING-002/003: Optimierte zwei-Phasen-Strategie:
        - Phase 1: BODYSTRUCTURE + RFC822.SIZE + FLAGS + UID (schnell, <1KB)
        - Phase 2: RFC822 nur für Body-Extraktion (wenn benötigt)
        
        BUG-002-FIX: Nutzt conn.uid('FETCH') für stabile UIDs (imaplib)
        Performance: 10-100x schneller bei großen Emails mit Attachments
        """
        try:
            if self.connection is None:
                return None
            conn = self.connection
            mail_id_str = mail_id.decode(errors="ignore")
            
            # BUG-002-FIX: UID-basierter Fetch (mail_id ist bereits UID von uid-search)
            # PHASE 1: Metadaten ohne Body-Download
            status, meta_data = conn.uid(
                'fetch',
                mail_id_str, 
                "(BODYSTRUCTURE RFC822.SIZE FLAGS UID BODY.PEEK[HEADER])"
            )

            if status != "OK":
                return None

            meta = meta_data[0][0]
            meta_str = meta.decode("utf-8", errors="ignore")

            imap_flags = self._parse_imap_flags(meta_str)
            imap_uid = self._parse_imap_uid(meta_str)
            flags_dict = self._parse_flags_dict(imap_flags)
            
            # RFC822.SIZE aus Response extrahieren (FINDING-003)
            message_size = self._parse_rfc822_size(meta_str)
            
            # BODYSTRUCTURE parsen (FINDING-002)
            bodystructure_info = self._parse_bodystructure_from_response(meta_str)
            
            # BUG-002-FIX: Phase 2 auch UID-basiert
            # PHASE 2: Body laden (nur für Text-Extraktion)
            status, body_data = conn.uid('fetch', mail_id_str, "(RFC822)")
            if status != "OK":
                return None
                
            raw_email = body_data[0][1]
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

            # Envelope mit BODYSTRUCTURE-Daten anreichern (FINDING-002/003)
            envelope = self._parse_envelope(msg, bodystructure_info, message_size)

            # Phase 13C: Decode IMAP UTF-7 folder names to UTF-8
            folder_utf8 = decode_imap_folder_name(folder)
            
            # Phase 14b: UIDVALIDITY aus Closure (von fetch_new_emails gesetzt)
            uidvalidity = getattr(self, '_current_folder_uidvalidity', None)

            return {
                "uid": mail_id_str,
                "sender": sender,
                "subject": subject,
                "body": body,
                "received_at": received_at,
                "imap_uid": imap_uid,
                "imap_folder": folder_utf8,  # UTF-8 decoded
                "imap_uidvalidity": uidvalidity,  # Phase 14b
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

    def _parse_envelope(self, msg, bodystructure_info: Optional[Dict], message_size: Optional[int]) -> Dict:
        """Extrahiert erweiterte Envelope-Daten aus RFC822-Message
        
        FINDING-002/003: Nutzt BODYSTRUCTURE-Daten statt teurer Berechnungen
        ISSUE-002/WARN-003-FIX: Robustes Fallback zu msg-Parsing bei None-Werten

        Args:
            msg: Parsed email.message object
            bodystructure_info: Pre-parsed BODYSTRUCTURE vom IMAP-Server (kann None sein)
            message_size: RFC822.SIZE vom IMAP-Server (kann None sein bei Parse-Fehler)

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
            
            # FINDING-003/WARN-003-FIX: RFC822.SIZE vom Server, Fallback bei None
            envelope["message_size"] = message_size if message_size is not None else 0
            
            # FINDING-002/ISSUE-002-FIX: BODYSTRUCTURE-Daten nutzen, Fallback zu msg-Parsing
            if bodystructure_info and bodystructure_info.get("content_type"):
                envelope["content_type"] = bodystructure_info["content_type"]
                envelope["charset"] = bodystructure_info.get("charset") or msg.get_content_charset() or "utf-8"
                envelope["has_attachments"] = bodystructure_info.get("has_attachments", False)
            else:
                # Fallback zu msg-Parsing (zuverlässig aber langsamer)
                fallback = self._bodystructure_fallback(msg)
                envelope["content_type"] = fallback["content_type"]
                envelope["charset"] = fallback["charset"]
                envelope["has_attachments"] = fallback["has_attachments"]

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
        
        WARN-001-FIX: Nutzt email.utils.getaddresses für RFC-konformes Parsing
        (Vorher: naives split(',') zerstörte Namen wie 'Doe, John')
        """
        try:
            from email.utils import getaddresses

            addresses_str = msg.get(header, "").strip()
            if not addresses_str:
                return None

            # RFC2822-konform: Behandelt Quotes, Kommas in Namen, etc.
            parsed = getaddresses([addresses_str])
            
            addresses = []
            for name, email_addr in parsed:
                if email_addr:  # Nur valide Email-Adressen
                    addresses.append({
                        "name": name.strip() if name else email_addr,
                        "email": email_addr.strip()
                    })

            return json.dumps(addresses) if addresses else None
        except Exception as e:
            logger.debug(f"Error extracting address list from {header}: {e}")
            return None

    def _parse_rfc822_size(self, response_str: str) -> Optional[int]:
        """Extrahiert RFC822.SIZE aus IMAP FETCH Response
        
        FINDING-003: Server kennt exakte Größe bereits (instant, kein RAM-Overhead)
        Vorher: len(msg.as_bytes()) = teuer, Serialisierung + Memory-Allokation
        
        Args:
            response_str: FETCH Response String mit "RFC822.SIZE 12345"
            
        Returns:
            Message size in bytes, None bei Fehler (WARN-003-FIX: nicht 0!)
        """
        try:
            import re
            match = re.search(r'RFC822\.SIZE\s+(\d+)', response_str)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.debug(f"Error parsing RFC822.SIZE: {e}")
        return None  # WARN-003-FIX: None statt 0 (Unterscheidung Fehler vs. kleine Email)

    def _parse_bodystructure_from_response(self, response_str: str) -> Dict:
        """Parst BODYSTRUCTURE aus IMAP FETCH Response
        
        FINDING-002: BODYSTRUCTURE liefert Struktur-Info OHNE Body zu laden (10-100x schneller)
        ISSUE-002-FIX: Robusterer Parsing mit Fallback zu None bei komplexen Strukturen
        
        BODYSTRUCTURE Format (RFC 3501):
        - Single Part: ("text" "plain" ("charset" "utf-8") NIL NIL "7bit" 1234 52)
        - Multi Part: (("text" "plain" ...) ("image" "jpeg" ...) "mixed")
        
        Args:
            response_str: FETCH Response mit BODYSTRUCTURE
            
        Returns:
            Dict mit: content_type, charset, has_attachments
            Bei Parse-Fehler: None statt falsche Defaults (ISSUE-002-FIX)
        """
        try:
            # Extrahiere BODYSTRUCTURE Teil aus Response
            import re
            # ISSUE-002-FIX: Robusterer Regex mit besserer Klammer-Behandlung
            match = re.search(r'BODYSTRUCTURE\s+(\((?:[^()]|\([^()]*\))*\))', response_str, re.DOTALL)
            if not match:
                logger.debug("BODYSTRUCTURE not found in response, falling back")
                return None  # ISSUE-002-FIX: None statt falscher Defaults
                
            structure = match.group(1)
            
            # Vereinfachte aber robuste Parsing-Logik
            info = {
                "content_type": None,
                "charset": None,
                "has_attachments": False
            }
            
            # Check for multipart (starts with nested parens)
            if structure.startswith('(('):
                info["content_type"] = "multipart/mixed"  # Conservative default
                # Multipart → prüfe auf attachment/application/image/video types
                # ISSUE-002-FIX: Vorsichtigere Heuristik
                lower_struct = structure.lower()
                has_attachment_markers = any([
                    'attachment' in lower_struct,
                    '"application"' in lower_struct,
                    '"image"' in lower_struct and '"jpeg"' in lower_struct,
                    '"video"' in lower_struct,
                    'filename' in lower_struct
                ])
                info["has_attachments"] = has_attachment_markers
            else:
                # Single part: extrahiere content-type
                # ISSUE-002-FIX: Robusteres Parsing mit Regex statt split
                type_match = re.search(r'\("([^"]+)"\s+"([^"]+)"', structure)
                if type_match:
                    mime_type = type_match.group(1).lower()
                    mime_subtype = type_match.group(2).lower()
                    info["content_type"] = f"{mime_type}/{mime_subtype}"
                    
            # Extrahiere charset (funktioniert für single & multi)
            charset_match = re.search(r'"charset"\s+"([^"]+)"', structure, re.IGNORECASE)
            if charset_match:
                info["charset"] = charset_match.group(1)
            
            return info
            
        except Exception as e:
            logger.debug(f"Error parsing BODYSTRUCTURE: {e}")
            return None  # ISSUE-002-FIX: None statt falscher Fallback-Daten
    
    def _bodystructure_fallback(self, msg) -> Dict:
        """Fallback: Parse MIME-Struktur aus msg-Objekt (langsamer aber zuverlässig)
        
        ISSUE-002-FIX: Bei komplexen BODYSTRUCTURE-Formaten fallback zu msg.walk()
        """
        try:
            info = {
                "content_type": msg.get_content_type(),
                "charset": msg.get_content_charset() or "utf-8",
                "has_attachments": self._detect_attachments(msg)
            }
            return info
        except Exception as e:
            logger.debug(f"Fallback MIME parsing failed: {e}")
            # Letzter Fallback: Safe defaults
            return {
                "content_type": "text/plain",
                "charset": "utf-8",
                "has_attachments": False
            }

    def _detect_attachments(self, msg) -> bool:
        """Erkennt ob die Nachricht Anhänge hat
        
        OPT-001-FIX: Erkennt auch inline-Attachments mit Filename
        (z.B. PDFs, Bilder ohne explicit 'attachment' disposition)
        """
        try:
            if not msg.is_multipart():
                return False

            for part in msg.walk():
                # Explicit attachment
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" in content_disposition.lower():
                    return True
                
                # Inline mit Filename (oft PDFs, Bilder)
                if part.get_filename():
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
