"""
Mail Server Sync Service

Synchronisiert den lokalen Zustand mit dem IMAP-Server:
- Scannt alle Mails auf dem Server (nur ENVELOPE, schnell!)
- Erkennt verschobene Mails (gleiche message_id, anderer folder)
- Erkennt gelöschte Mails (war in DB, nicht mehr auf Server)
- Berechnet echtes Delta (was muss noch gefetcht werden)

Flow:
    1. SCAN: Hole ENVELOPEs aller Mails → mail_server_state
    2. DETECT: Moves, Deletes, New
    3. UPDATE: raw_emails.imap_folder für verschobene Mails
"""

import hashlib
import logging
from datetime import datetime, UTC
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Ergebnis eines Sync-Vorgangs"""
    folders_scanned: int
    mails_on_server: int
    new_mails: int
    moved_mails: int
    deleted_mails: int
    already_fetched: int
    errors: List[str]
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def compute_content_hash(date_str: str, from_addr: str, subject: str) -> str:
    """Berechnet stabilen Hash aus Date+From+Subject (Fallback für fehlende Message-ID)"""
    content = f"{date_str or ''}|{from_addr or ''}|{subject or ''}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]


def extract_message_id(envelope) -> Optional[str]:
    """Extrahiert Message-ID aus ENVELOPE-Objekt"""
    if envelope is None:
        return None
    
    # IMAPClient ENVELOPE hat message_id als Attribut
    msg_id = getattr(envelope, 'message_id', None)
    if msg_id:
        if isinstance(msg_id, bytes):
            msg_id = msg_id.decode('utf-8', errors='replace')
        return msg_id.strip('<>').strip()
    return None


def extract_envelope_data(envelope) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
    """Extrahiert From, Subject, Date aus ENVELOPE"""
    from_addr = None
    subject = None
    date = None
    
    if envelope is None:
        return from_addr, subject, date
    
    # From
    if hasattr(envelope, 'from_') and envelope.from_:
        addr = envelope.from_[0]
        if hasattr(addr, 'mailbox') and hasattr(addr, 'host'):
            mailbox = addr.mailbox.decode() if isinstance(addr.mailbox, bytes) else addr.mailbox
            host = addr.host.decode() if isinstance(addr.host, bytes) else addr.host
            from_addr = f"{mailbox}@{host}" if mailbox and host else None
    
    # Subject
    if hasattr(envelope, 'subject') and envelope.subject:
        subject = envelope.subject
        if isinstance(subject, bytes):
            subject = subject.decode('utf-8', errors='replace')
    
    # Date
    if hasattr(envelope, 'date') and envelope.date:
        date = envelope.date
    
    return from_addr, subject, date


class MailServerSyncService:
    """Service für Server-Synchronisation"""
    
    def __init__(self, fetcher, db_session, user_id: int, account_id: int):
        """
        Args:
            fetcher: MailFetcher Instanz (bereits verbunden)
            db_session: SQLAlchemy Session
            user_id: User ID
            account_id: Mail Account ID
        """
        self.fetcher = fetcher
        self.session = db_session
        self.user_id = user_id
        self.account_id = account_id
        
        # Lazy import models
        import importlib
        self.models = importlib.import_module(".02_models", "src")
    
    def scan_server(self, folders: Optional[List[str]] = None, 
                   include_folders: Optional[List[str]] = None,
                   exclude_folders: Optional[List[str]] = None) -> SyncResult:
        """
        Scannt alle Mails auf dem Server und speichert in mail_server_state.
        
        Args:
            folders: Explizite Liste von Ordnern (optional)
            include_folders: Nur diese Ordner (optional)
            exclude_folders: Diese Ordner ausschließen (optional)
            
        Returns:
            SyncResult mit Statistiken
        """
        errors = []
        folders_scanned = 0
        mails_on_server = 0
        new_mails = 0
        moved_mails = 0
        deleted_mails = 0
        already_fetched = 0
        
        try:
            conn = self.fetcher.connection
            if not conn:
                return SyncResult(0, 0, 0, 0, 0, 0, ["Keine IMAP-Verbindung"])
            
            # Ordner-Liste holen
            if folders is None:
                folder_tuples = conn.list_folders()
                folders = [f[2] for f in folder_tuples]
            
            # Filter anwenden
            if include_folders:
                folders = [f for f in folders if f in include_folders]
            if exclude_folders:
                folders = [f for f in folders if f not in exclude_folders]
            
            logger.info(f"🔄 Server-Scan: {len(folders)} Ordner")
            
            # Hole existierende content_hashes aus DB für Move-Detection
            existing_hashes = self._get_existing_hashes()
            
            # Aktuelle Server-UIDs sammeln (für Delete-Detection)
            current_server_entries = set()
            
            for folder in folders:
                try:
                    folder_info = conn.select_folder(folder, readonly=True)
                    uidvalidity = folder_info.get(b'UIDVALIDITY')
                    if uidvalidity:
                        uidvalidity = int(uidvalidity[0]) if isinstance(uidvalidity, list) else int(uidvalidity)
                    
                    # Alle UIDs im Ordner
                    uids = conn.search(['ALL'])
                    if not uids:
                        folders_scanned += 1
                        continue
                    
                    # ENVELOPEs holen (Batch, schnell!)
                    # Limit auf 500 pro Batch um Server nicht zu überlasten
                    for i in range(0, len(uids), 500):
                        batch_uids = uids[i:i+500]
                        envelopes = conn.fetch(batch_uids, ['ENVELOPE', 'FLAGS'])
                        
                        for uid, data in envelopes.items():
                            mails_on_server += 1
                            envelope = data.get(b'ENVELOPE')
                            flags = data.get(b'FLAGS', [])
                            
                            # Daten extrahieren
                            message_id = extract_message_id(envelope)
                            from_addr, subject, date = extract_envelope_data(envelope)
                            date_str = date.isoformat() if date else None
                            content_hash = compute_content_hash(date_str, from_addr, subject)
                            
                            flags_str = ' '.join(
                                f.decode() if isinstance(f, bytes) else str(f) 
                                for f in flags
                            )
                            
                            # Prüfe ob lokal schon gefetcht
                            # WICHTIG: Primär nach message_id, dann folder+uid
                            local_raw_email_id = self._find_raw_email_id(message_id, folder, uid)
                            
                            # In mail_server_state speichern/updaten
                            result = self._upsert_server_state(
                                folder=folder,
                                uid=uid,
                                uidvalidity=uidvalidity,
                                message_id=message_id,
                                content_hash=content_hash,
                                envelope_from=from_addr,
                                envelope_subject=subject,
                                envelope_date=date,
                                flags=flags_str,
                                existing_hashes=existing_hashes,
                                local_raw_email_id=local_raw_email_id
                            )
                            
                            if result == 'new':
                                new_mails += 1
                            elif result == 'moved':
                                moved_mails += 1
                            elif result == 'fetched':
                                already_fetched += 1
                            
                            # Track für Delete-Detection
                            current_server_entries.add((folder, uid, uidvalidity))
                    
                    folders_scanned += 1
                    logger.debug(f"  ✓ {folder}: {len(uids)} Mails")
                    
                except Exception as e:
                    errors.append(f"{folder}: {str(e)}")
                    logger.warning(f"  ⚠️ {folder}: {e}")
            
            # Delete-Detection: Mails die nicht mehr auf Server sind
            # WICHTIG: Prüft auch auf MOVES innerhalb der gescannten Ordner!
            deleted_mails, moved_in_delete_phase = self._mark_deleted_mails(current_server_entries)
            moved_mails += moved_in_delete_phase  # Moves aus Delete-Phase addieren
            
            self.session.commit()
            
            logger.info(
                f"✅ Sync abgeschlossen: {folders_scanned} Ordner, "
                f"{mails_on_server} Mails, {new_mails} neu, "
                f"{moved_mails} verschoben, {deleted_mails} gelöscht"
            )
            
        except Exception as e:
            errors.append(f"Sync-Fehler: {str(e)}")
            logger.error(f"❌ Sync-Fehler: {e}")
        
        return SyncResult(
            folders_scanned=folders_scanned,
            mails_on_server=mails_on_server,
            new_mails=new_mails,
            moved_mails=moved_mails,
            deleted_mails=deleted_mails,
            already_fetched=already_fetched,
            errors=errors
        )
    
    def _get_existing_hashes(self) -> Dict[str, Any]:
        """Holt existierende content_hashes mit ihren Einträgen aus mail_server_state"""
        existing = self.session.query(self.models.MailServerState).filter(
            self.models.MailServerState.user_id == self.user_id,
            self.models.MailServerState.mail_account_id == self.account_id,
            self.models.MailServerState.is_deleted == False
        ).all()
        
        return {e.content_hash: e for e in existing}
    
    def _build_raw_email_lookup_caches(self):
        """Baut Lookup-Caches für raw_emails (einmal pro Sync-Session)
        
        Strategie nach User-Design:
        1. Primär: message_id → raw_email_id
        2. Fallback: folder+uid → raw_email_id (für Mails ohne message_id)
        """
        if hasattr(self, '_raw_email_by_msgid'):
            return  # Bereits gebaut
        
        RawEmail = self.models.RawEmail
        
        # Hole alle raw_emails für diesen Account
        local = self.session.query(
            RawEmail.id, 
            RawEmail.message_id, 
            RawEmail.imap_folder, 
            RawEmail.imap_uid
        ).filter(
            RawEmail.user_id == self.user_id,
            RawEmail.mail_account_id == self.account_id,
            RawEmail.deleted_at.is_(None)
        ).all()
        
        # Cache 1: message_id → raw_email_id (primär)
        self._raw_email_by_msgid = {}
        # Cache 2: (folder, uid) → raw_email_id (fallback)
        self._raw_email_by_folder_uid = {}
        
        for raw_id, msg_id, folder, uid in local:
            if msg_id:
                self._raw_email_by_msgid[msg_id] = raw_id
            if folder and uid:
                self._raw_email_by_folder_uid[(folder, uid)] = raw_id
        
        logger.debug(f"📊 Raw-Email Caches: {len(self._raw_email_by_msgid)} by message_id, "
                    f"{len(self._raw_email_by_folder_uid)} by folder+uid")
    
    def _find_raw_email_id(self, message_id: Optional[str], folder: str, uid: int) -> Optional[int]:
        """Findet raw_email_id für eine Server-Mail
        
        Strategie:
        1. Primär: message_id Match (funktioniert auch bei Moves!)
        2. Fallback: folder+uid Match (für Mails ohne message_id)
        """
        self._build_raw_email_lookup_caches()
        
        # 1. Primär: message_id
        if message_id and message_id in self._raw_email_by_msgid:
            return self._raw_email_by_msgid[message_id]
        
        # 2. Fallback: folder+uid
        return self._raw_email_by_folder_uid.get((folder, uid))
    
    def _get_raw_email_by_content_hash(self, content_hash: str) -> Optional[int]:
        """Fallback: Sucht raw_email über content_hash wenn message_id nicht matcht
        
        HINWEIS: Aktuell nicht implementiert weil raw_emails verschlüsselt sind.
        Könnte später über gespeicherten content_hash in raw_emails gelöst werden.
        Content-Hash kann nicht aus encrypted_sender/encrypted_subject berechnet werden.
        
        Für echtes Move-Detection müsste content_hash beim Fetch gespeichert werden.
        """
        # TODO: content_hash Spalte zu raw_emails hinzufügen und beim Fetch speichern
        return None
    
    def _upsert_server_state(
        self, folder: str, uid: int, uidvalidity: int,
        message_id: Optional[str], content_hash: str,
        envelope_from: Optional[str], envelope_subject: Optional[str],
        envelope_date: Optional[datetime], flags: str,
        existing_hashes: Dict[str, Any],
        local_raw_email_id: Optional[int] = None
    ) -> str:
        """
        Fügt neuen Eintrag ein oder aktualisiert bestehenden.
        
        Args:
            local_raw_email_id: Falls bekannt, die ID einer existierenden raw_email
        
        Returns:
            'new' - Neue Mail
            'moved' - Mail wurde verschoben
            'updated' - Existierender Eintrag aktualisiert
            'fetched' - Bereits gefetcht
        """
        MailServerState = self.models.MailServerState
        
        # Check: Existiert Eintrag mit gleichem folder/uid/uidvalidity?
        existing_exact = self.session.query(MailServerState).filter(
            MailServerState.user_id == self.user_id,
            MailServerState.mail_account_id == self.account_id,
            MailServerState.folder == folder,
            MailServerState.uid == uid,
            MailServerState.uidvalidity == uidvalidity
        ).first()
        
        if existing_exact:
            # Update last_seen_at und flags
            existing_exact.last_seen_at = datetime.now(UTC)
            existing_exact.flags = flags
            existing_exact.is_deleted = False
            # Verlinke raw_email falls noch nicht verlinkt
            if local_raw_email_id and not existing_exact.raw_email_id:
                existing_exact.raw_email_id = local_raw_email_id
            return 'fetched' if existing_exact.raw_email_id else 'updated'
        
        # Check: Existiert Eintrag mit gleichem content_hash in anderem Folder? (Move!)
        if content_hash in existing_hashes:
            existing_entry = existing_hashes[content_hash]
            if existing_entry.folder != folder:
                # MOVE detected!
                old_folder = existing_entry.folder
                existing_entry.folder = folder
                existing_entry.uid = uid
                existing_entry.uidvalidity = uidvalidity
                existing_entry.flags = flags
                existing_entry.last_seen_at = datetime.now(UTC)
                existing_entry.is_deleted = False
                
                # Update raw_email wenn gefetcht
                if existing_entry.raw_email_id:
                    raw_email = self.session.query(self.models.RawEmail).get(
                        existing_entry.raw_email_id
                    )
                    if raw_email:
                        raw_email.imap_folder = folder
                        raw_email.imap_uid = uid
                        raw_email.imap_uidvalidity = uidvalidity
                        logger.info(f"📁 MOVE: {old_folder} → {folder} (raw_email_id={raw_email.id})")
                
                return 'moved'
        
        # Neue Mail (für mail_server_state, kann aber lokal schon existieren!)
        
        effective_raw_email_id = local_raw_email_id
        was_moved = False
        
        # Wenn raw_email gefunden wurde aber in anderem Folder → MOVE!
        # Aktualisiere raw_email mit neuem Folder/UID
        if effective_raw_email_id:
            raw_email = self.session.query(self.models.RawEmail).get(effective_raw_email_id)
            if raw_email and raw_email.imap_folder != folder:
                old_folder = raw_email.imap_folder
                raw_email.imap_folder = folder
                raw_email.imap_uid = uid
                raw_email.imap_uidvalidity = uidvalidity
                logger.info(f"📁 MOVE (via message_id): {old_folder} → {folder} (raw_email_id={raw_email.id})")
                was_moved = True
        
        new_entry = MailServerState(
            user_id=self.user_id,
            mail_account_id=self.account_id,
            folder=folder,
            uid=uid,
            uidvalidity=uidvalidity,
            message_id=message_id,
            content_hash=content_hash,
            envelope_from=envelope_from,
            envelope_subject=envelope_subject,
            envelope_date=envelope_date,
            flags=flags,
            raw_email_id=effective_raw_email_id,  # Verlinke sofort wenn lokal bekannt
            is_deleted=False,
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC)
        )
        self.session.add(new_entry)
        
        # Update hash-dict für weitere Lookups
        existing_hashes[content_hash] = new_entry
        
        # Return-Wert: moved > fetched > new
        if was_moved:
            return 'moved'
        elif effective_raw_email_id:
            return 'fetched'
        else:
            return 'new'
    
    def _mark_deleted_mails(self, current_server_entries: set) -> Tuple[int, int]:
        """
        Markiert Mails die nicht mehr auf Server sind als gelöscht.
        
        WICHTIG: Prüft zuerst ob die message_id in einem ANDEREN Ordner existiert!
        Wenn ja → MOVE, nicht DELETE.
        
        Returns:
            Tuple[deleted_count, moved_count]
        """
        MailServerState = self.models.MailServerState
        
        # Hole alle nicht-gelöschten Einträge für gescannte Ordner
        all_local = self.session.query(MailServerState).filter(
            MailServerState.user_id == self.user_id,
            MailServerState.mail_account_id == self.account_id,
            MailServerState.is_deleted == False
        ).all()
        
        # Baue message_id → aktueller Server-Eintrag Lookup
        # (nur für Einträge die auf dem Server gesehen wurden)
        server_msgid_to_entry = {}
        for entry in all_local:
            key = (entry.folder, entry.uid, entry.uidvalidity)
            if key in current_server_entries and entry.message_id:
                server_msgid_to_entry[entry.message_id] = entry
        
        deleted_count = 0
        moved_count = 0
        
        for entry in all_local:
            key = (entry.folder, entry.uid, entry.uidvalidity)
            if key not in current_server_entries:
                # ════════════════════════════════════════════════════════════════
                # MOVE-DETECTION: Prüfe ob message_id in anderem Ordner existiert
                # ════════════════════════════════════════════════════════════════
                if entry.message_id and entry.message_id in server_msgid_to_entry:
                    new_entry = server_msgid_to_entry[entry.message_id]
                    old_folder = entry.folder
                    
                    # raw_email updaten wenn gefetcht
                    if entry.raw_email_id:
                        raw_email = self.session.query(self.models.RawEmail).get(entry.raw_email_id)
                        if raw_email and raw_email.deleted_at is None:
                            raw_email.imap_folder = new_entry.folder
                            raw_email.imap_uid = new_entry.uid
                            raw_email.imap_uidvalidity = new_entry.uidvalidity
                            logger.info(f"📁 MOVE (delete-phase): {old_folder} → {new_entry.folder} (raw_email_id={raw_email.id})")
                        
                        # raw_email_id zum neuen Entry übertragen
                        new_entry.raw_email_id = entry.raw_email_id
                    
                    # Alten Entry als gelöscht markieren (wurde ja verschoben)
                    entry.is_deleted = True
                    moved_count += 1
                else:
                    # Echtes DELETE: Mail nicht mehr auf Server
                    entry.is_deleted = True
                    deleted_count += 1
                    
                    # Soft-delete raw_email wenn gefetcht
                    if entry.raw_email_id:
                        raw_email = self.session.query(self.models.RawEmail).get(entry.raw_email_id)
                        if raw_email and raw_email.deleted_at is None:
                            raw_email.deleted_at = datetime.now(UTC)
                            logger.info(f"🗑️ DELETE: {entry.folder}/{entry.uid} (raw_email_id={raw_email.id})")
        
        return deleted_count, moved_count
    
    def get_unfetched_uids(self, folder: str) -> List[int]:
        """Gibt UIDs zurück die noch nicht gefetcht wurden"""
        MailServerState = self.models.MailServerState
        
        unfetched = self.session.query(MailServerState.uid).filter(
            MailServerState.user_id == self.user_id,
            MailServerState.mail_account_id == self.account_id,
            MailServerState.folder == folder,
            MailServerState.raw_email_id.is_(None),
            MailServerState.is_deleted == False
        ).all()
        
        return [u[0] for u in unfetched]
    
    def link_fetched_email(self, folder: str, uid: int, uidvalidity: int, raw_email_id: int):
        """Verknüpft gefetchte Mail mit server_state Eintrag"""
        MailServerState = self.models.MailServerState
        
        entry = self.session.query(MailServerState).filter(
            MailServerState.user_id == self.user_id,
            MailServerState.mail_account_id == self.account_id,
            MailServerState.folder == folder,
            MailServerState.uid == uid,
            MailServerState.uidvalidity == uidvalidity
        ).first()
        
        if entry:
            entry.raw_email_id = raw_email_id
            entry.last_seen_at = datetime.now(UTC)
