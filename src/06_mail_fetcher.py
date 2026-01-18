"""
Mail Helper - Mail Fetcher (IMAP + OAuth)
Holt E-Mails von IMAP-Servern (GMX, Gmail, etc.) & Google OAuth
"""

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
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
        # P1-006: Verbesserte UTF-7 Dekodierung
        # Versuche erst imaputf7 library (optional dependency)
        try:
            import imaputf7
            return imaputf7.decode(folder_name)
        except ImportError:
            pass  # Library nicht installiert, nutze Fallback
        
        # Fallback 1: Python's imap4-utf-7 codec
        import codecs
        try:
            codecs.lookup('imap4-utf-7')
            return folder_name.encode('latin1').decode('imap4-utf-7')
        except LookupError:
            pass  # Codec nicht verfügbar
        
        # Fallback 2: Erweitertes manuelles Mapping (häufigste Zeichen)
        # Format: &BASE64- wobei BASE64 modified Base64 ist
        replacements = {
            '&APw-': 'ü',  '&APs-': 'Ü',
            '&APY-': 'ö',  '&ANY-': 'Ö', 
            '&AOQ-': 'ä',  '&AOR-': 'Ä',
            '&APA-': 'ß',
            '&IKw-': '€',
            '&AOk-': 'é',  '&AOg-': 'è',  '&AOo-': 'ê',
            '&AOM-': 'à',  '&AOI-': 'â',
            '&APo-': 'ú',  '&APk-': 'ù',  '&APt-': 'û',
            '&APM-': 'ó',  '&API-': 'ò',  '&APQ-': 'ô',
        }
        
        decoded = folder_name
        for encoded, char in replacements.items():
            decoded = decoded.replace(encoded, char)
        
        return decoded
        
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
        self.connection: Optional[IMAPClient] = None

    def connect(self, retry_count: int = 1, timeout: float = 15.0):
        """Stellt Verbindung zum IMAP-Server her (IMAPClient)
        
        Args:
            retry_count: Anzahl Wiederholungen bei Timeout (default: 1, war vorher 2)
            timeout: TCP-Timeout in Sekunden (default: 15, war vorher 60)
            
        P1-004: Reduzierte Defaults für schnelleres Failure-Feedback
        """
        last_error = None
        
        for attempt in range(retry_count + 1):
            try:
                # Phase 1: TCP Connection (P1-004: Konfigurierbarer Timeout)
                self.connection = IMAPClient(
                    host=self.server,
                    port=self.port,
                    ssl=True,
                    timeout=timeout
                )
                print(f"✅ TCP-Verbindung zu {self.server}:{self.port} erfolgreich")
                
                # Phase 2: IMAP Login
                self.connection.login(self.username, self.password)
                print(f"✅ Login erfolgreich für {self.username}")
                return  # Erfolg - fertig!
                
            except TimeoutError as e:
                last_error = e
                if attempt < retry_count:
                    logger.warning(f"Timeout bei Verbindung zu {self.server} (Versuch {attempt + 1}/{retry_count + 1}), versuche erneut...")
                    print(f"⏳ Timeout - versuche erneut ({attempt + 2}/{retry_count + 1})...")
                    continue  # Nächster Versuch
                # Letzter Versuch fehlgeschlagen
                error_msg = f"Timeout beim Verbinden zu {self.server}:{self.port}"
                logger.error(f"{error_msg}: {e}")
                print(f"❌ {error_msg}")
                print(f"   💡 Überprüfe: Server-Adresse und Port korrekt? Firewall?")
                print(f"   💡 Server antwortet langsam - {retry_count + 1} Versuche fehlgeschlagen")
                raise ConnectionError(f"IMAP timeout: {error_msg}") from None
                
            except IMAPClientError as e:
                last_error = e
                error_str = str(e).lower()
                
                # Spezifische Fehleranalyse
                if 'auth' in error_str or 'login' in error_str or 'credentials' in error_str:
                    logger.error(f"Login fehlgeschlagen für {self.username}@{self.server}: {e}")
                    print(f"❌ Authentifizierung fehlgeschlagen")
                    print(f"   💡 Überprüfe: Benutzername = {self.username}")
                    print(f"   💡 Überprüfe: Passwort korrekt? (App-Passwort bei 2FA?)")
                    raise ConnectionError(f"Authentication failed: Wrong username or password") from None
                    
                elif 'ssl' in error_str or 'certificate' in error_str or 'tls' in error_str:
                    logger.error(f"SSL-Fehler bei {self.server}:{self.port}: {e}")
                    print(f"❌ SSL/TLS-Fehler: {e}")
                    print(f"   💡 Versuche: Port 143 (STARTTLS) statt 993 (SSL)?")
                    raise ConnectionError(f"SSL error: {e}") from None
                    
                elif 'refused' in error_str or 'port' in error_str:
                    logger.error(f"Port {self.port} bei {self.server} nicht erreichbar: {e}")
                    print(f"❌ Verbindung abgelehnt zu {self.server}:{self.port}")
                    print(f"   💡 Überprüfe: Port korrekt? (Standard: 993 oder 143)")
                    raise ConnectionError(f"Connection refused: Port {self.port}") from None
                    
                else:
                    logger.error(f"IMAP-Fehler bei {self.server}: {e}")
                    print(f"❌ IMAP-Fehler: {e}")
                    raise ConnectionError(f"IMAP error: {e}") from None
                    
            except OSError as e:
                last_error = e
                # Network-level errors (DNS, routing, etc.)
                error_msg = f"Netzwerk-Fehler: {e}"
                logger.error(f"{error_msg} bei {self.server}:{self.port}")
                print(f"❌ {error_msg}")
                print(f"   💡 Überprüfe: Server-Adresse korrekt? DNS funktioniert?")
                raise ConnectionError(f"Network error: {e}") from None
                
            except Exception as e:
                last_error = e
                logger.error(f"Unerwarteter Fehler beim Connect: {type(e).__name__}: {e}")
                print(f"❌ Fehler: {type(e).__name__}: {e}")
                raise ConnectionError(f"Connection failed: {e}") from None
            raise ConnectionError(f"Connection failed: {e}") from None

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
        import importlib; models = importlib.import_module(".02_models", "src")
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

    def search_uids(
        self,
        folder: str = "INBOX",
        since: Optional[datetime] = None,
        before: Optional[datetime] = None,
        unseen_only: bool = False,
        flagged_only: bool = False,
    ) -> List[int]:
        """
        Sucht UIDs die den Filterkriterien entsprechen (ohne Mail-Inhalt zu laden).
        
        Returns:
            Liste von UIDs die dem Filter entsprechen
        """
        if not self.connection:
            self.connect()
        
        try:
            conn = self.connection
            if conn is None:
                return []
            
            conn.select_folder(folder, readonly=True)
            
            # Build IMAP SEARCH criteria
            search_criteria = []
            
            if unseen_only:
                search_criteria.append('UNSEEN')
            
            if flagged_only:
                search_criteria.append('FLAGGED')
            
            if since:
                date_str = since.strftime("%d-%b-%Y")
                search_criteria.append('SINCE')
                search_criteria.append(date_str)
            
            if before:
                date_str = before.strftime("%d-%b-%Y")
                search_criteria.append('BEFORE')
                search_criteria.append(date_str)
            
            # IMAPClient: search() gibt direkt Liste von UIDs zurück
            messages = conn.search(search_criteria if search_criteria else ['ALL'])
            
            return list(messages) if messages else []
            
        except Exception as e:
            logger.warning(f"⚠️  search_uids fehlgeschlagen für {folder}: {e}")
            return []

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
        # NEU: Spezifische UIDs laden (für Filter-basiertes Delta)
        specific_uids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """
        Holt E-Mails mit Threading-Informationen (Phase 12)
        + Server-Side Filtering (Phase 13C Part 2)
        + Delta-Sync (Phase 13C Part 4)
        + UIDVALIDITY-Check (Phase 14b)
        + Filter-basiertes Delta (specific_uids)

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
            specific_uids: Liste spezifischer UIDs die geladen werden sollen (Filter-Delta)

        Returns:
            Liste von E-Mail-Dicts mit erweiterten Metadaten
        """
        if not self.connection:
            self.connect()

        try:
            conn = self.connection
            if conn is None:
                raise ConnectionError("IMAP connection failed")
            
            # Phase 14b: SELECT folder → UIDVALIDITY extrahieren (IMAPClient!)
            # IMAPClient gibt UIDVALIDITY direkt im Dict zurück - VIEL EINFACHER!
            folder_info = conn.select_folder(folder, readonly=True)
            
            # IMAPClient gibt Dict zurück: {b'UIDVALIDITY': 1352540700, b'EXISTS': 42, ...}
            server_uidvalidity = None
            if folder_info:
                # Direkt aus Dict holen - IMAPClient macht das Parsing!
                uidvalidity_val = folder_info.get(b'UIDVALIDITY')
                if uidvalidity_val is not None:
                    # Kann int oder list sein - normalisieren
                    if isinstance(uidvalidity_val, list):
                        server_uidvalidity = int(uidvalidity_val[0])
                    else:
                        server_uidvalidity = int(uidvalidity_val)
                    logger.debug(f"✅ UIDVALIDITY from select_folder: {server_uidvalidity}")
            
            if not server_uidvalidity:
                logger.warning(f"⚠️  Konnte UIDVALIDITY für {folder} nicht abrufen!")
                # Continue ohne UIDVALIDITY (Mails werden skipped in persistence)
            
            # Phase 14b: UIDVALIDITY-Check wenn account_id + session gegeben
            if account_id and session and server_uidvalidity:
                import importlib
                models = importlib.import_module(".02_models", "src")
                
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

            # ════════════════════════════════════════════════════════════════
            # NEU: Wenn specific_uids gegeben, nutze diese direkt
            # ════════════════════════════════════════════════════════════════
            if specific_uids:
                mail_ids = list(reversed(specific_uids))[:limit]
                print(f"📧 {len(mail_ids)} Mails aus spezifischen UIDs")
            elif uid_range:
                # Phase 13C Part 4: Delta-Sync via UID-Range (IMAPClient)
                # UID-Range suche: z.B. "8:*" = alle Mails ab UID 8
                messages = conn.search(['UID', uid_range])
                if not messages:
                    print(f"📧 0 Mails gefunden (keine neuen seit UID {uid_range.split(':')[0]})")
                    return []
                mail_ids = list(reversed(messages))[:limit]
                print(f"📧 {len(mail_ids)} Mails gefunden")
            else:
                # Phase 13C Part 2: Build IMAP SEARCH criteria
                search_criteria = []
                
                if unseen_only:
                    search_criteria.append('UNSEEN')
                
                if flagged_only:
                    search_criteria.append('FLAGGED')
                
                if since:
                    # IMAP date format: DD-Mon-YYYY
                    date_str = since.strftime("%d-%b-%Y")
                    search_criteria.append('SINCE')
                    search_criteria.append(date_str)
                
                if before:
                    date_str = before.strftime("%d-%b-%Y")
                    search_criteria.append('BEFORE')
                    search_criteria.append(date_str)
                
                # IMAPClient: search() gibt direkt Liste von UIDs zurück
                messages = conn.search(search_criteria if search_criteria else ['ALL'])
                
                if not messages:
                    print("📧 0 Mails gefunden")
                    return []
                
                mail_ids = list(reversed(messages))[:limit]
                
                if search_criteria:
                    print(f"🔍 Filter: {' '.join(str(c) for c in search_criteria)}")
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
            import traceback
            logger.error(f"❌ FETCH EXCEPTION: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            print(f"❌ Fehler beim Abrufen: {type(e).__name__}: {e}")
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
        self, mail_id: int, folder: str = "INBOX"
    ) -> Optional[Dict]:
        """Holt eine einzelne E-Mail mit erweiterten Metadaten (IMAPClient)
        
        IMAPClient macht FETCH viel einfacher:
        - fetch() gibt direkt Dict zurück
        - FLAGS als Liste
        - ENVELOPE als Objekt
        - Keine Response-Parsing-Hölle mehr!
        """
        try:
            if self.connection is None:
                return None
            conn = self.connection
            
            # IMAPClient: fetch() gibt Dict zurück: {uid: {b'FLAGS': [...], b'RFC822': ...}}
            # PHASE 1: Metadaten + Header
            meta_data = conn.fetch([mail_id], ['FLAGS', 'RFC822.SIZE', 'ENVELOPE', 'BODYSTRUCTURE', 'INTERNALDATE'])
            
            if not meta_data or mail_id not in meta_data:
                return None
            
            msg_data = meta_data[mail_id]
            
            # FLAGS extrahieren (bereits als Liste!)
            imap_flags_list = msg_data.get(b'FLAGS', [])
            imap_flags = ' '.join(str(f.decode() if isinstance(f, bytes) else f) for f in imap_flags_list)
            
            # Flags dict
            flags_dict = {
                'imap_is_seen': b'\\Seen' in imap_flags_list,
                'imap_is_answered': b'\\Answered' in imap_flags_list,
                'imap_is_flagged': b'\\Flagged' in imap_flags_list,
                'imap_is_deleted': b'\\Deleted' in imap_flags_list,
                'imap_is_draft': b'\\Draft' in imap_flags_list,
            }
            
            # Message Size
            message_size = msg_data.get(b'RFC822.SIZE', 0)
            
            # ENVELOPE extrahieren (IMAPClient parsed das schon!)
            envelope = msg_data.get(b'ENVELOPE')
            
            subject = 'N/A'
            sender = 'N/A'
            message_id_val = None
            received_at = datetime.now()
            
            if envelope:
                # Subject (MIME-Header Dekodierung!)
                if envelope.subject:
                    try:
                        # 1. Bytes → String
                        subject_raw = envelope.subject.decode('utf-8', errors='replace') if isinstance(envelope.subject, bytes) else str(envelope.subject)
                        
                        # 2. MIME-Header dekodieren (z.B. =?UTF-8?Q?...?=)
                        decoded_parts = decode_header(subject_raw)
                        subject_parts = []
                        for part, charset in decoded_parts:
                            if isinstance(part, bytes):
                                subject_parts.append(part.decode(charset or 'utf-8', errors='replace'))
                            else:
                                subject_parts.append(part)
                        subject = ''.join(subject_parts)[:200]
                    except Exception as e:
                        subject = str(envelope.subject)[:200]
                
                # Sender (from) - mit MIME-Header Dekodierung
                if envelope.from_ and len(envelope.from_) > 0:
                    try:
                        from_addr = envelope.from_[0]
                        logger.debug(f"📧 ENVELOPE.from_ raw: {envelope.from_}")
                        logger.debug(f"📧 from_addr type: {type(from_addr)}, value: {from_addr}")
                        
                        # IMAPClient gibt Address-Objekte zurück (nicht Tuples!)
                        # Address hat Attribute: .name, .route, .mailbox, .host
                        if hasattr(from_addr, 'name'):
                            # Neues Format: Address object
                            name_raw = from_addr.name.decode() if isinstance(from_addr.name, bytes) else (from_addr.name or "")
                            mailbox = from_addr.mailbox.decode() if isinstance(from_addr.mailbox, bytes) else (from_addr.mailbox or "")
                            domain = from_addr.host.decode() if isinstance(from_addr.host, bytes) else (from_addr.host or "")
                        else:
                            # Altes Format: Tuple (Fallback für alte IMAPClient Versionen)
                            name_raw = from_addr[0].decode() if from_addr[0] else ""
                            mailbox = from_addr[2].decode() if from_addr[2] else ""
                            domain = from_addr[3].decode() if from_addr[3] else ""
                        
                        # Name dekodieren (kann MIME-Header enthalten!)
                        name = ""
                        if name_raw:
                            decoded_parts = decode_header(name_raw)
                            name_parts = []
                            for part, charset in decoded_parts:
                                if isinstance(part, bytes):
                                    name_parts.append(part.decode(charset or 'utf-8', errors='replace'))
                                else:
                                    name_parts.append(part)
                            name = ''.join(name_parts)
                        
                        if name:
                            sender = f"\"{name}\" <{mailbox}@{domain}>"
                        else:
                            sender = f"{mailbox}@{domain}" if mailbox and domain else "N/A"
                        
                        logger.debug(f"✅ Parsed sender: {sender}")
                    except Exception as e:
                        logger.error(f"❌ Sender parsing failed: {type(e).__name__}: {e}, raw envelope.from_={envelope.from_}")
                        sender = 'N/A'
                else:
                    logger.warning(f"⚠️ ENVELOPE.from_ is empty or None: {envelope.from_}")
                    sender = 'N/A'
                
                # Message-ID
                if envelope.message_id:
                    try:
                        message_id_val = envelope.message_id.decode('ascii', errors='replace')
                    except:
                        message_id_val = str(envelope.message_id)
                
                # Date: Nutze INTERNALDATE (Server-Empfangsdatum, zuverlässig)
                internal_date = msg_data.get(b'INTERNALDATE')
                if internal_date:
                    # INTERNALDATE ist bereits datetime object von IMAPClient
                    received_at = internal_date
                    logger.debug(f"📅 Using INTERNALDATE: {received_at}")
                elif envelope.date:
                    # Fallback: envelope.date (kann vom Absender gefälscht sein)
                    try:
                        date_str = envelope.date.decode() if isinstance(envelope.date, bytes) else str(envelope.date)
                        received_at = email.utils.parsedate_to_datetime(date_str)
                        logger.debug(f"📅 Using envelope.date: {received_at}")
                    except Exception as e:
                        logger.error(f"❌ envelope.date parsing failed: {type(e).__name__}: {e}, raw={envelope.date}")
                        received_at = datetime.now()
                        logger.warning(f"⚠️ Fallback to now(): {received_at}")
                else:
                    received_at = datetime.now()
                    logger.warning(f"⚠️ No date found, using now(): {received_at}")
            
            # PHASE 2: RFC822 für Body + Complete Envelope Parsing
            body_data = conn.fetch([mail_id], ['RFC822'])
            body = 'N/A'
            msg = None
            
            if body_data and mail_id in body_data:
                msg_bytes = body_data[mail_id].get(b'RFC822')
                if msg_bytes:
                    msg = email.message_from_bytes(msg_bytes)
                    body = self._extract_body(msg)
                    # DEBUG: Log body extraction result
                    if not body or body == 'N/A':
                        logger.warning(f"⚠️ BODY LEER für UID {mail_id}: msg_bytes={len(msg_bytes) if msg_bytes else 0}, content_type={msg.get_content_type() if msg else 'N/A'}, is_multipart={msg.is_multipart() if msg else 'N/A'}")
                else:
                    logger.warning(f"⚠️ RFC822 LEER für UID {mail_id}")
            else:
                logger.warning(f"⚠️ FETCH FEHLGESCHLAGEN für UID {mail_id}: body_data={body_data}")
            
            # Phase E Bug-Fix: Parse complete envelope (in_reply_to, references, etc.)
            # _parse_envelope() extrahiert ALLE Header auf einmal (effizienter!)
            bodystructure = msg_data.get(b'BODYSTRUCTURE')
            envelope_data = {}
            
            if msg:
                # Prepare bodystructure_info for _parse_envelope()
                bodystructure_info = None
                if bodystructure:
                    has_attachments = self._check_attachments_in_bodystructure(bodystructure)
                    bodystructure_info = {
                        "content_type": msg.get_content_type() if msg else None,
                        "charset": msg.get_content_charset() if msg else None,
                        "has_attachments": has_attachments
                    }
                
                # Nutze _parse_envelope() statt einzelne Extraktion
                envelope_data = self._parse_envelope(msg, bodystructure_info, message_size)
                
                # Extrahiere Inline-Attachments (CID-Bilder)
                inline_attachments = self._extract_inline_attachments(msg)
                
                # Extrahiere klassische Anhänge (PDF, Word, etc.)
                classic_attachments = self._extract_classic_attachments(msg)
                
                # Phase 25: Extrahiere Kalenderdaten (Termineinladungen)
                calendar_data = self._extract_calendar_data(msg)
            else:
                inline_attachments = {}
                classic_attachments = []
                calendar_data = None
            
            # Phase 13C: Decode IMAP UTF-7 folder names to UTF-8
            folder_utf8 = decode_imap_folder_name(folder)
            
            # Phase 14b: UIDVALIDITY aus Closure
            uidvalidity = getattr(self, '_current_folder_uidvalidity', None)

            # Phase E Bug-Fix: Merge envelope_data mit base_data
            base_data = {
                "uid": str(mail_id),
                "sender": sender,
                "subject": subject,
                "body": body,
                "received_at": received_at,
                "imap_uid": mail_id,
                "imap_folder": folder_utf8,
                "imap_uidvalidity": uidvalidity,
                "imap_flags": imap_flags,
                "thread_id": None,  # Wird später von _calculate_thread_ids() gesetzt
                "parent_uid": None,  # Wird später von _calculate_thread_ids() gesetzt
                "inline_attachments": inline_attachments,  # CID-Bilder
                "attachments": classic_attachments,  # Klassische Anhänge (PDF, Word, etc.)
                # Phase 25: Kalenderdaten
                "is_calendar_invite": calendar_data is not None,
                "calendar_data": calendar_data,
                **flags_dict,  # Boolean flags (imap_is_seen, imap_is_flagged, etc.)
            }
            
            # Merge envelope_data (message_id, in_reply_to, references, to, cc, etc.)
            base_data.update(envelope_data)
            
            return base_data

        except Exception as e:
            logger.debug(f"Fetch mail error for ID {mail_id}: {e}")
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
                result.append(part.decode(encoding or "utf-8", errors="ignore"))
            else:
                result.append(part)

        return " ".join(result)

    def _extract_body(self, msg) -> str:
        """Extrahiert Text-Body aus E-Mail
        
        Priorität: text/html > text/plain
        
        WICHTIG: HTML wird bevorzugt, weil:
        1. Outlook/Exchange erzeugen oft text/plain als eine lange Zeile
        2. HTML enthält die eigentliche Formatierung (Zeilenumbrüche, Listen, etc.)
        3. Der render_email_html Endpoint rendert HTML korrekt im iframe
        4. Für AI-Analyse wird HTML später via inscriptis zu Plaintext konvertiert
        """
        body = ""
        html_body = ""
        plain_body = ""  # Fallback wenn kein HTML

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()

                if content_type == "text/html" and not html_body:
                    # HTML bevorzugen (enthält Formatierung)
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        html_body = payload.decode(charset, errors="ignore")
                    except Exception as e:
                        logger.debug(f"Failed to decode text/html payload: {e}")
                elif content_type == "text/plain" and not plain_body:
                    # Plaintext als Fallback speichern
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        plain_body = payload.decode(charset, errors="ignore")
                    except Exception as e:
                        logger.debug(f"Failed to decode text/plain payload: {e}")
            
            # HTML bevorzugen, Plaintext als Fallback
            if html_body:
                body = html_body
                logger.debug("Using text/html (preferred for display)")
            elif plain_body:
                body = plain_body
                logger.debug("Using text/plain as fallback (no text/html found)")
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

        body = body.strip()
        if not body:
            logger.warning(f"⚠️ EMPTY BODY EXTRACTED: is_multipart={msg.is_multipart()}, content_type={msg.get_content_type()}, payload_len={len(str(msg.get_payload())) if msg.get_payload() else 0}")
        
        return body

    def _extract_calendar_data(self, msg) -> Optional[Dict]:
        """Extrahiert Kalenderdaten aus text/calendar MIME Part
        
        Erkennt Termineinladungen (METHOD:REQUEST), Absagen (METHOD:CANCEL),
        Zusagen (METHOD:REPLY), etc.
        
        Returns:
            Dict mit Event-Details oder None wenn keine Kalender-Daten:
            {
                "method": "REQUEST",  # REQUEST, REPLY, CANCEL, COUNTER
                "uid": "event-uid@example.com",
                "summary": "Meeting Titel",
                "description": "Details...",
                "dtstart": "2026-01-20T14:00:00+01:00",
                "dtend": "2026-01-20T15:00:00+01:00",
                "location": "Konferenzraum 3",
                "organizer": {"name": "Max Muster", "email": "max@example.com"},
                "attendees": [{"name": "...", "email": "...", "partstat": "NEEDS-ACTION"}],
                "status": "CONFIRMED",
                "sequence": 0,
                "raw_ics": "BEGIN:VCALENDAR..."
            }
        """
        calendar_part = None
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/calendar":
                    calendar_part = part
                    break
        elif msg.get_content_type() == "text/calendar":
            calendar_part = msg
        
        if not calendar_part:
            return None
        
        try:
            payload = calendar_part.get_payload(decode=True)
            charset = calendar_part.get_content_charset() or "utf-8"
            ics_content = payload.decode(charset, errors="ignore")
            
            if not ics_content or "BEGIN:VCALENDAR" not in ics_content:
                return None
            
            # Parse iCalendar Content
            calendar_data = self._parse_icalendar(ics_content)
            if calendar_data:
                calendar_data["raw_ics"] = ics_content
                logger.info(f"📅 Kalendereinladung erkannt: {calendar_data.get('method', 'UNKNOWN')} - {calendar_data.get('summary', 'Kein Titel')}")
            
            return calendar_data
            
        except Exception as e:
            logger.warning(f"Failed to parse calendar data: {e}")
            return None

    def _parse_icalendar(self, ics_content: str) -> Optional[Dict]:
        """Parst iCalendar-Inhalt und extrahiert Event-Details
        
        Einfacher Parser ohne externe Bibliothek (icalendar optional).
        Extrahiert die wichtigsten Felder für Anzeige.
        """
        result = {
            "method": None,
            "uid": None,
            "summary": None,
            "description": None,
            "dtstart": None,
            "dtend": None,
            "location": None,
            "organizer": None,
            "attendees": [],
            "status": None,
            "sequence": 0,
        }
        
        # Versuche icalendar Library (falls installiert)
        try:
            from icalendar import Calendar
            cal = Calendar.from_ical(ics_content)
            
            # METHOD aus VCALENDAR
            result["method"] = str(cal.get("METHOD", "")).upper() or None
            
            # Erstes VEVENT finden
            for component in cal.walk():
                if component.name == "VEVENT":
                    result["uid"] = str(component.get("UID", ""))
                    result["summary"] = str(component.get("SUMMARY", ""))
                    result["description"] = str(component.get("DESCRIPTION", ""))
                    result["location"] = str(component.get("LOCATION", ""))
                    result["status"] = str(component.get("STATUS", ""))
                    result["sequence"] = int(component.get("SEQUENCE", 0))
                    
                    # Datum/Zeit
                    dtstart = component.get("DTSTART")
                    if dtstart:
                        dt = dtstart.dt
                        result["dtstart"] = dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
                    
                    dtend = component.get("DTEND")
                    if dtend:
                        dt = dtend.dt
                        result["dtend"] = dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
                    
                    # Organizer
                    organizer = component.get("ORGANIZER")
                    if organizer:
                        org_email = str(organizer).replace("mailto:", "").replace("MAILTO:", "")
                        org_name = organizer.params.get("CN", "") if hasattr(organizer, 'params') else ""
                        result["organizer"] = {"name": org_name, "email": org_email}
                    
                    # Attendees
                    for attendee in component.get("ATTENDEE", []):
                        if attendee:
                            att_email = str(attendee).replace("mailto:", "").replace("MAILTO:", "")
                            att_name = attendee.params.get("CN", "") if hasattr(attendee, 'params') else ""
                            partstat = attendee.params.get("PARTSTAT", "NEEDS-ACTION") if hasattr(attendee, 'params') else "NEEDS-ACTION"
                            result["attendees"].append({
                                "name": att_name,
                                "email": att_email,
                                "partstat": partstat
                            })
                    
                    break  # Nur erstes Event
            
            return result
            
        except ImportError:
            # Fallback: Simple Regex Parser
            logger.debug("icalendar library not installed, using regex fallback")
            return self._parse_icalendar_regex(ics_content)
        except Exception as e:
            logger.warning(f"icalendar parsing failed, using regex fallback: {e}")
            return self._parse_icalendar_regex(ics_content)

    def _parse_icalendar_regex(self, ics_content: str) -> Optional[Dict]:
        """Fallback-Parser mit Regex für iCalendar
        
        Wird verwendet wenn icalendar Library nicht installiert ist.
        """
        result = {
            "method": None,
            "uid": None,
            "summary": None,
            "description": None,
            "dtstart": None,
            "dtend": None,
            "location": None,
            "organizer": None,
            "attendees": [],
            "status": None,
            "sequence": 0,
        }
        
        # Simple line-based parsing
        lines = ics_content.replace("\r\n ", "").replace("\r\n\t", "").split("\r\n")
        if len(lines) <= 1:
            lines = ics_content.replace("\n ", "").replace("\n\t", "").split("\n")
        
        in_vevent = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line == "BEGIN:VEVENT":
                in_vevent = True
                continue
            if line == "END:VEVENT":
                in_vevent = False
                continue
            
            # Property:Value parsing
            if ":" in line:
                prop_part, value = line.split(":", 1)
                prop = prop_part.split(";")[0].upper()
                
                if prop == "METHOD":
                    result["method"] = value.upper()
                elif in_vevent:
                    if prop == "UID":
                        result["uid"] = value
                    elif prop == "SUMMARY":
                        result["summary"] = value
                    elif prop == "DESCRIPTION":
                        result["description"] = value[:500]  # Limit
                    elif prop == "LOCATION":
                        result["location"] = value
                    elif prop == "STATUS":
                        result["status"] = value
                    elif prop == "SEQUENCE":
                        try:
                            result["sequence"] = int(value)
                        except ValueError:
                            pass
                    elif prop == "DTSTART":
                        result["dtstart"] = self._parse_ical_datetime(value)
                    elif prop == "DTEND":
                        result["dtend"] = self._parse_ical_datetime(value)
                    elif prop == "ORGANIZER":
                        email = value.replace("mailto:", "").replace("MAILTO:", "")
                        # CN aus prop_part extrahieren
                        cn_match = re.search(r'CN=([^;:]+)', prop_part, re.IGNORECASE)
                        name = cn_match.group(1).strip('"') if cn_match else ""
                        result["organizer"] = {"name": name, "email": email}
                    elif prop == "ATTENDEE":
                        email = value.replace("mailto:", "").replace("MAILTO:", "")
                        cn_match = re.search(r'CN=([^;:]+)', prop_part, re.IGNORECASE)
                        name = cn_match.group(1).strip('"') if cn_match else ""
                        partstat_match = re.search(r'PARTSTAT=([^;:]+)', prop_part, re.IGNORECASE)
                        partstat = partstat_match.group(1) if partstat_match else "NEEDS-ACTION"
                        result["attendees"].append({
                            "name": name,
                            "email": email,
                            "partstat": partstat
                        })
        
        return result if result["uid"] or result["summary"] else None

    def _parse_ical_datetime(self, value: str) -> Optional[str]:
        """Parst iCalendar Datum/Zeit-Werte zu ISO-Format"""
        try:
            # Entferne TZID Parameter falls vorhanden
            if ":" in value:
                value = value.split(":")[-1]
            
            # Format: YYYYMMDDTHHMMSS oder YYYYMMDDTHHMMSSZ
            value = value.strip()
            
            if len(value) == 8:  # YYYYMMDD (ganztägig)
                return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
            elif len(value) >= 15:  # YYYYMMDDTHHMMSS
                base = f"{value[:4]}-{value[4:6]}-{value[6:8]}T{value[9:11]}:{value[11:13]}:{value[13:15]}"
                if value.endswith("Z"):
                    base += "Z"
                return base
            return value
        except Exception:
            return value

    def _extract_inline_attachments(self, msg) -> Dict[str, Dict[str, str]]:
        """Extrahiert Inline-Attachments (CID-Bilder) aus E-Mail
        
        CID (Content-ID) wird in HTML als src="cid:uuid@domain" referenziert.
        Diese Funktion extrahiert die Bilder und gibt sie als Dict zurück.
        
        Limits:
            - Max 2 MB Gesamtgröße pro E-Mail
            - Max 500 KB pro einzelnes Attachment
            - Nur Bilder (image/*)
        
        Returns:
            Dict mit Content-ID als Key: {
                "uuid@domain": {
                    "mime_type": "image/png",
                    "data": "base64-encoded-data"
                }
            }
        """
        inline_attachments = {}
        total_size = 0
        MAX_TOTAL_SIZE = 2 * 1024 * 1024  # 2 MB Gesamtlimit
        MAX_SINGLE_SIZE = 500 * 1024  # 500 KB pro Attachment
        
        if not msg.is_multipart():
            return inline_attachments
            
        for part in msg.walk():
            content_disposition = part.get_content_disposition()
            content_id = part.get("Content-ID")
            content_type = part.get_content_type()
            
            # Nur Inline-Attachments mit Content-ID (CID)
            # content_disposition kann 'inline', None, oder 'attachment' sein
            if content_id and content_type.startswith("image/"):
                try:
                    # Content-ID Format: <uuid@domain> oder uuid@domain
                    cid = content_id.strip("<>")
                    
                    payload = part.get_payload(decode=True)
                    if payload:
                        payload_size = len(payload)
                        
                        # Size-Limits prüfen
                        if payload_size > MAX_SINGLE_SIZE:
                            logger.warning(
                                f"Inline attachment {cid} too large ({payload_size} bytes), skipping (limit: {MAX_SINGLE_SIZE})"
                            )
                            continue
                            
                        if total_size + payload_size > MAX_TOTAL_SIZE:
                            logger.warning(
                                f"Total inline attachments size exceeded ({total_size + payload_size} bytes), skipping remaining"
                            )
                            break
                        
                        import base64
                        base64_data = base64.b64encode(payload).decode("ascii")
                        
                        inline_attachments[cid] = {
                            "mime_type": content_type,
                            "data": base64_data
                        }
                        total_size += payload_size
                        logger.debug(f"Extracted inline attachment: cid={cid}, type={content_type}, size={payload_size}")
                except Exception as e:
                    logger.warning(f"Failed to extract inline attachment {content_id}: {e}")
        
        if total_size > 0:
            logger.info(f"Extracted {len(inline_attachments)} inline attachments, total size: {total_size} bytes")
        
        return inline_attachments

    def _extract_classic_attachments(self, msg) -> List[Dict[str, any]]:
        """Extrahiert klassische Anhänge (PDF, Word, Excel, Bilder, etc.)
        
        Unterschied zu Inline-Attachments:
        - Inline: Hat Content-ID (cid:...), wird im HTML-Body referenziert
        - Klassisch: Hat Content-Disposition: attachment, wird als separate Datei angehängt
        
        Limits:
            - Max 25 MB pro Datei (darüber → S3 in Phase 2)
            - Max 100 MB Gesamtgröße pro E-Mail
        
        Returns:
            Liste von Dicts: [
                {
                    "filename": "rechnung.pdf",
                    "mime_type": "application/pdf",
                    "size": 12345,
                    "data": "base64-encoded-data",
                    "content_id": None  # oder cid für inline
                },
                ...
            ]
        """
        attachments = []
        total_size = 0
        MAX_TOTAL_SIZE = 100 * 1024 * 1024  # 100 MB Gesamtlimit
        MAX_SINGLE_SIZE = 25 * 1024 * 1024  # 25 MB pro Datei
        
        if not msg.is_multipart():
            return attachments
        
        import base64
        
        for part in msg.walk():
            # Prüfe Content-Disposition
            content_disposition = part.get_content_disposition()
            content_id = part.get("Content-ID")
            content_type = part.get_content_type()
            filename = part.get_filename()
            
            # Klassischer Anhang: Hat Disposition "attachment" ODER hat Dateinamen aber keine CID
            is_attachment = (
                content_disposition == "attachment" or
                (filename and not content_id and content_type not in ["text/plain", "text/html"])
            )
            
            if not is_attachment:
                continue
            
            if not filename:
                # Generiere Dateinamen aus Content-Type
                ext = content_type.split("/")[-1] if "/" in content_type else "bin"
                filename = f"attachment.{ext}"
            
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                
                payload_size = len(payload)
                
                # Size-Limits prüfen
                if payload_size > MAX_SINGLE_SIZE:
                    logger.warning(
                        f"Attachment '{filename}' too large ({payload_size / (1024*1024):.1f} MB), "
                        f"skipping (limit: {MAX_SINGLE_SIZE / (1024*1024):.0f} MB)"
                    )
                    # TODO: S3 Upload für große Dateien
                    continue
                
                if total_size + payload_size > MAX_TOTAL_SIZE:
                    logger.warning(
                        f"Total attachments size exceeded ({(total_size + payload_size) / (1024*1024):.1f} MB), "
                        f"skipping remaining"
                    )
                    break
                
                base64_data = base64.b64encode(payload).decode("ascii")
                
                attachments.append({
                    "filename": filename,
                    "mime_type": content_type,
                    "size": payload_size,
                    "data": base64_data,
                    "content_id": content_id.strip("<>") if content_id else None
                })
                total_size += payload_size
                logger.debug(f"Extracted attachment: {filename} ({payload_size} bytes, {content_type})")
                
            except Exception as e:
                logger.warning(f"Failed to extract attachment '{filename}': {e}")
        
        if attachments:
            logger.info(
                f"📎 Extracted {len(attachments)} attachments, "
                f"total size: {total_size / 1024:.1f} KB"
            )
        
        return attachments

    def _check_attachments_in_bodystructure(self, bodystructure) -> bool:
        """Prüft ob BODYSTRUCTURE Attachments enthält (IMAPClient)"""
        if not bodystructure:
            return False
        
        # Rekursiv durch BODYSTRUCTURE gehen und nach "attachment" disposition suchen
        def check_part(part):
            if isinstance(part, (list, tuple)):
                for item in part:
                    if check_part(item):
                        return True
            elif isinstance(part, bytes):
                part_str = part.decode('utf-8', errors='ignore').lower()
                if 'attachment' in part_str:
                    return True
            elif isinstance(part, str):
                if 'attachment' in part.lower():
                    return True
            return False
        
        return check_part(bodystructure)

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

    Args:
        mail_account: MailAccount Model-Instanz
        master_key: Encrypted Master-Key um Passwörter zu decrypten

    Returns:
        MailFetcher (IMAP) oder GoogleMailFetcher (OAuth)

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
