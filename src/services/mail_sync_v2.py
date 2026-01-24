"""
Mail Server Sync Service v2 - Sauberer 3-Schritt-Workflow

Workflow:
═══════════════════════════════════════════════════════════════════════════

SCHRITT 1: STATE = SERVER-ABBILD (sync_state_with_server)
    Für jeden Filter-Ordner:
        a) Server scannen → alle Mails in RAM
        b) DELETE FROM mail_server_state WHERE folder = X
        c) INSERT alle Server-Mails in mail_server_state
    
    → Kein UPDATE nötig! Einfach DELETE + INSERT
    → State ist danach 1:1 Abbild vom Server (für die Filter-Ordner)

SCHRITT 2: FETCH (insert_fetched_mail)
    Was ist in State aber nicht in raw_emails?
        → Fetch diese Mails vom Server
        → INSERT in raw_emails (stable_identifier für MOVE-Erkennung)
    
    KEINE State-Arbeit hier! Das macht Schritt 3.

SCHRITT 3: RAW SYNC (sync_raw_emails_with_state)
    Für jede Mail in raw_emails:
        → Existiert in State? 
            JA → UPDATE folder/uid/flags in raw_emails
                 UPDATE state.raw_email_id (Verlinkung)
            NEIN → DELETE aus raw_emails (deleted_at=NOW)

═══════════════════════════════════════════════════════════════════════════
"""

import hashlib
import logging
from datetime import datetime, UTC
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Statistiken eines Sync-Vorgangs"""
    # Schritt 1: State mit Server (DELETE + INSERT pro Ordner)
    folders_scanned: int = 0
    mails_on_server: int = 0
    state_inserted: int = 0
    state_deleted: int = 0
    
    # Schritt 2: Fetch
    fetch_candidates: int = 0
    fetched: int = 0
    
    # Schritt 3: Raw mit State
    raw_updated: int = 0
    raw_deleted: int = 0
    raw_linked: int = 0  # raw_email_id in State gesetzt
    
    errors: List[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@dataclass
class ServerMail:
    """Eine Mail wie sie auf dem Server existiert"""
    folder: str
    uid: int
    uidvalidity: int
    message_id: Optional[str]
    content_hash: str  # Fallback wenn keine message_id
    flags: str
    envelope_from: Optional[str] = None
    envelope_subject: Optional[str] = None
    envelope_date: Optional[datetime] = None


def compute_content_hash(date_str: str, from_addr: str, subject: str) -> str:
    """Berechnet stabilen Hash aus Date+From+Subject (Fallback für fehlende Message-ID)"""
    content = f"{date_str or ''}|{from_addr or ''}|{subject or ''}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]


def get_stable_id(message_id: Optional[str], content_hash: str) -> str:
    """Gibt den stabilen Identifier zurück: message_id wenn vorhanden, sonst content_hash"""
    return message_id if message_id else f"hash:{content_hash}"


class MailSyncServiceV2:
    """
    Sauberer Mail-Sync Service nach dem 3-Schritt-Workflow.
    
    Prinzip: Server → State → Raw
    """
    
    def __init__(self, imap_connection, db_session, user_id: int, account_id: int):
        """
        Args:
            imap_connection: IMAPClient Instanz (bereits verbunden)
            db_session: SQLAlchemy Session
            user_id: User ID
            account_id: Mail Account ID
        """
        self.conn = imap_connection
        self.session = db_session
        self.user_id = user_id
        self.account_id = account_id
        
        # Lazy import models
        import importlib
        self.models = importlib.import_module(".02_models", "src")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SCHRITT 1: STATE-TABELLE MIT SERVER ABGLEICHEN
    # ═══════════════════════════════════════════════════════════════════════════
    
    def sync_state_with_server(
        self, 
        include_folders: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> SyncStats:
        """
        Schritt 1: Filter-Ordner scannen und mail_server_state aktualisieren.
        
        PRO ORDNER:
          a) Server scannen → alle Mails in RAM
          b) DELETE FROM mail_server_state WHERE folder = X
          c) INSERT alle Server-Mails in mail_server_state
        
        → Kein UPDATE nötig! Einfach DELETE + INSERT pro Ordner
        → State ist danach 1:1 Abbild vom Server
        
        Args:
            include_folders: Ordner die gescannt werden sollen (aus Filter).
                           Wenn None, werden bekannte Ordner aus State verwendet.
            progress_callback: Optional callback(phase, message, **kwargs) für Progress-Updates.
        
        Returns:
            SyncStats mit Statistiken
        """
        stats = SyncStats()
        
        logger.info(f"🔄 Schritt 1 gestartet: include_folders={include_folders}")
        
        try:
            # 1. Welche Ordner scannen?
            if include_folders:
                folders_to_scan = include_folders
                logger.info(f"📁 Scan Filter-Ordner: {folders_to_scan}")
            else:
                # Fallback: Bekannte Ordner aus State
                folders_to_scan = self._get_known_folders()
                if not folders_to_scan:
                    logger.info("📭 Keine Ordner zum Scannen - Schritt 1 übersprungen")
                    return stats
            
            # 2. Pro Ordner: DELETE + INSERT (simpel und robust!)
            total_folders = len(folders_to_scan)
            
            logger.info(f"🔍 DEBUG: progress_callback ist {'GESETZT' if progress_callback else 'NICHT GESETZT'}")
            
            for idx, folder in enumerate(folders_to_scan, 1):
                # Progress: Ordner startet
                if progress_callback:
                    logger.info(f"📤 DEBUG: Sende Progress-Update für Ordner {idx}/{total_folders}: {folder}")
                    progress_callback(
                        phase="state_sync_folder_start",
                        message=f"Scanne Ordner '{folder}'...",
                        folder_idx=idx,
                        total_folders=total_folders,
                        folder=folder
                    )
                    logger.info(f"✅ DEBUG: Progress-Update gesendet")
                
                # Sync Ordner (mit Batch-Updates)
                folder_mail_count = self._sync_folder_state(folder, stats, progress_callback)
                
                # Progress: Ordner fertig
                if progress_callback:
                    progress_callback(
                        phase="state_sync_folder_complete",
                        message=f"✅ Ordner '{folder}' abgeschlossen",
                        folder_name=folder,
                        mails_in_folder=folder_mail_count
                    )
            
            self.session.commit()
            
            logger.info(
                f"✅ Schritt 1 abgeschlossen: {stats.folders_scanned} Ordner, "
                f"{stats.mails_on_server} Server-Mails, "
                f"+{stats.state_inserted} inserted, {stats.state_deleted}🗑 deleted"
            )
            
        except Exception as e:
            stats.errors.append(f"State-Sync Fehler: {str(e)}")
            logger.error(f"❌ Schritt 1 fehlgeschlagen: {e}")
            self.session.rollback()
        
        return stats
    
    def _sync_folder_state(
        self, 
        folder: str, 
        stats: SyncStats,
        progress_callback: Optional[callable] = None
    ):
        """
        Synchronisiert mail_server_state für EINEN Ordner.
        
        Simpel: DELETE alle für diesen Ordner, dann INSERT alle vom Server.
        
        Args:
            folder: Ordner-Name (z.B. "INBOX")
            stats: SyncStats-Objekt zum Aktualisieren
            progress_callback: Optional callback für Batch-Progress
        """
        MailServerState = self.models.MailServerState
        now = datetime.now(UTC)
        
        try:
            # a) Server scannen für diesen Ordner
            folder_info = self.conn.select_folder(folder, readonly=True)
            uidvalidity = folder_info.get(b'UIDVALIDITY')
            if uidvalidity:
                uidvalidity = int(uidvalidity[0]) if isinstance(uidvalidity, list) else int(uidvalidity)
            
            uids = self.conn.search(['ALL'])
            server_mails = []
            
            if uids:
                # Batch-Fetch ENVELOPEs
                total_uids = len(uids)
                
                for i in range(0, total_uids, 500):
                    # Progress: Batch-Update (nur wenn >500 Mails im Ordner)
                    if total_uids > 500 and progress_callback:
                        processed = min(i + 500, total_uids)
                        percent = int((processed / total_uids) * 100)
                        progress_callback(
                            phase="state_sync_batch",
                            message=f"Scanne Mails... {percent}%",
                            processed=processed,
                            total=total_uids,
                            folder=folder
                        )
                    
                    batch_uids = uids[i:i+500]
                    envelopes = self.conn.fetch(batch_uids, ['ENVELOPE', 'FLAGS'])
                    
                    for uid, data in envelopes.items():
                        envelope = data.get(b'ENVELOPE')
                        flags = data.get(b'FLAGS', [])
                        
                        message_id = self._extract_message_id(envelope)
                        from_addr, subject, date = self._extract_envelope_data(envelope)
                        date_str = date.isoformat() if date else None
                        content_hash = compute_content_hash(date_str, from_addr, subject)
                        
                        flags_str = ' '.join(
                            f.decode() if isinstance(f, bytes) else str(f) 
                            for f in flags
                        )
                        
                        server_mails.append(ServerMail(
                            folder=folder,
                            uid=uid,
                            uidvalidity=uidvalidity,
                            message_id=message_id,
                            content_hash=content_hash,
                            flags=flags_str,
                            envelope_from=from_addr,
                            envelope_subject=subject,
                            envelope_date=date
                        ))
            
            stats.mails_on_server += len(server_mails)
            
            # b) DELETE alle State-Einträge für diesen Ordner
            deleted = self.session.query(MailServerState).filter(
                MailServerState.user_id == self.user_id,
                MailServerState.mail_account_id == self.account_id,
                MailServerState.folder == folder
            ).delete()
            stats.state_deleted += deleted
            
            # c) INSERT alle Server-Mails
            for mail in server_mails:
                new_entry = MailServerState(
                    user_id=self.user_id,
                    mail_account_id=self.account_id,
                    folder=mail.folder,
                    uid=mail.uid,
                    uidvalidity=mail.uidvalidity,
                    message_id=mail.message_id,
                    content_hash=mail.content_hash,
                    envelope_from=mail.envelope_from,
                    envelope_subject=mail.envelope_subject,
                    envelope_date=mail.envelope_date,
                    flags=mail.flags,
                    is_deleted=False,
                    first_seen_at=now,
                    last_seen_at=now
                )
                self.session.add(new_entry)
                stats.state_inserted += 1
            
            stats.folders_scanned += 1
            logger.debug(f"  ✓ {folder}: {len(server_mails)} Mails (deleted {deleted}, inserted {len(server_mails)})")
            
            # Return mail count für Progress-Callback
            return len(server_mails)
            
        except IntegrityError as e:
            # UniqueViolation: Parallel läuft ein anderer Worker!
            # WICHTIG: Session rollback sonst sind alle weiteren Ordner kaputt
            self.session.rollback()
            stats.errors.append(f"{folder}: Concurrent sync detected, skipping folder")
            logger.warning(f"  ⚠️ {folder}: Parallel Worker erkannt (UniqueViolation) → Session rollback + skip")
            return 0  # Return 0 bei Conflict
        except Exception as e:
            stats.errors.append(f"{folder}: {str(e)}")
            logger.warning(f"  ⚠️ {folder}: {e}")
            return 0  # Return 0 bei Fehler
    
    def _get_known_folders(self) -> List[str]:
        """
        Gibt die Ordner zurück die bereits in mail_server_state bekannt sind.
        
        SELECT DISTINCT folder FROM mail_server_state WHERE account_id = X
        """
        MailServerState = self.models.MailServerState
        
        result = self.session.query(MailServerState.folder).filter(
            MailServerState.user_id == self.user_id,
            MailServerState.mail_account_id == self.account_id,
            MailServerState.is_deleted == False
        ).distinct().all()
        
        folders = [r[0] for r in result]
        logger.debug(f"📁 Bekannte Ordner: {folders}")
        return folders
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SCHRITT 3: RAW_EMAILS MIT STATE ABGLEICHEN
    # ═══════════════════════════════════════════════════════════════════════════
    
    def sync_raw_emails_with_state(self) -> SyncStats:
        """
        Schritt 3: raw_emails mit State abgleichen.
        
        State = Wahrheit!
        
        1) Duplikate in raw_emails finden → DELETE den der NICHT im State ist
        2) Rest: UPDATE falls nicht identisch mit State
        3) Nicht in State → DELETE
        """
        stats = SyncStats()
        now = datetime.now(UTC)
        
        try:
            RawEmail = self.models.RawEmail
            MailServerState = self.models.MailServerState
            
            # State als Lookup laden (WAHRHEIT!)
            state_entries = self.session.query(MailServerState).filter(
                MailServerState.user_id == self.user_id,
                MailServerState.mail_account_id == self.account_id,
                MailServerState.is_deleted == False
            ).all()
            
            state_by_msgid = {}
            for entry in state_entries:
                if entry.message_id:
                    if entry.message_id not in state_by_msgid:
                        state_by_msgid[entry.message_id] = []
                    state_by_msgid[entry.message_id].append(entry)
            
            # Alle raw_emails laden
            raw_emails = self.session.query(RawEmail).filter(
                RawEmail.user_id == self.user_id,
                RawEmail.mail_account_id == self.account_id,
                RawEmail.deleted_at.is_(None)
            ).all()
            
            logger.info(f"🔄 Schritt 3: {len(raw_emails)} raw_emails gegen {len(state_entries)} State-Einträge")
            
            # ═════════════════════════════════════════════════════════════════
            # SCHRITT 3a: DUPLIKATE BEREINIGEN
            # ═════════════════════════════════════════════════════════════════
            # Gruppiere raw_emails nach message_id
            raws_by_msgid = {}
            for raw in raw_emails:
                if raw.message_id:
                    if raw.message_id not in raws_by_msgid:
                        raws_by_msgid[raw.message_id] = []
                    raws_by_msgid[raw.message_id].append(raw)
            
            # Finde Duplikate und bereinige
            for msgid, raw_list in raws_by_msgid.items():
                if len(raw_list) > 1:
                    # Duplikat gefunden!
                    logger.info(f"🔀 Duplikat erkannt: message_id={msgid}, {len(raw_list)}x in raw_emails")
                    
                    # Welcher passt zu State?
                    state_list = state_by_msgid.get(msgid, [])
                    if state_list:
                        state_entry = state_list[0]
                        logger.info(f"   State sagt: folder={state_entry.folder}, uid={state_entry.uid}")
                        
                        for raw in raw_list:
                            # Passt zu State (folder + uid)?
                            if raw.imap_folder == state_entry.folder and raw.imap_uid == state_entry.uid:
                                logger.info(f"   ✓ raw.id={raw.id} (folder={raw.imap_folder}, uid={raw.imap_uid}) passt → BEHALTEN")
                            else:
                                logger.info(f"   ✗ raw.id={raw.id} (folder={raw.imap_folder}, uid={raw.imap_uid}) passt NICHT → DELETE")
                                raw.deleted_at = now
                                stats.raw_deleted += 1
                        
                        # EDGE-CASE: Wenn KEINER der Duplikate zu State passt (z.B. nach EXPUNGE 
                        # mit neuer UID), werden alle gelöscht. Das ist gewollt!
                        # → Der nächste Fetch holt die Mail mit korrektem folder/uid
                        # → State = Wahrheit, kein "Reparatur-Code" nötig
            
            # ═════════════════════════════════════════════════════════════════
            # SCHRITT 3b: REST AKTUALISIEREN
            # ═════════════════════════════════════════════════════════════════
            # Lade raw_emails neu (nach Duplikat-Cleanup)
            raw_emails = self.session.query(RawEmail).filter(
                RawEmail.user_id == self.user_id,
                RawEmail.mail_account_id == self.account_id,
                RawEmail.deleted_at.is_(None)
            ).all()
            
            for raw in raw_emails:
                if not raw.message_id:
                    continue
                
                state_list = state_by_msgid.get(raw.message_id, [])
                if state_list:
                    state_entry = state_list[0]
                    
                    changed = False
                    
                    # UPDATE folder/uid falls anders
                    if raw.imap_folder != state_entry.folder:
                        logger.info(f"📁 Raw MOVE: {raw.imap_folder} → {state_entry.folder} (id={raw.id})")
                        raw.imap_folder = state_entry.folder
                        changed = True
                    
                    if raw.imap_uid != state_entry.uid:
                        raw.imap_uid = state_entry.uid
                        changed = True
                    
                    if raw.imap_uidvalidity != state_entry.uidvalidity:
                        raw.imap_uidvalidity = state_entry.uidvalidity
                        changed = True
                    
                    # Flags synchronisieren
                    if state_entry.flags:
                        flags_lower = state_entry.flags.lower()
                        raw.imap_is_seen = '\\seen' in flags_lower
                        raw.imap_is_flagged = '\\flagged' in flags_lower
                        raw.imap_is_answered = '\\answered' in flags_lower
                    
                    # Link State mit Raw
                    if state_entry.raw_email_id != raw.id:
                        state_entry.raw_email_id = raw.id
                        stats.raw_linked += 1
                    
                    if changed:
                        stats.raw_updated += 1
                else:
                    # Nicht in State → DELETE
                    logger.info(f"🗑️ Raw DELETE: {raw.imap_folder}/{raw.imap_uid} (id={raw.id}, msgid={raw.message_id})")
                    raw.deleted_at = now
                    stats.raw_deleted += 1
            
            self.session.commit()
            
            logger.info(
                f"✅ Schritt 3: {stats.raw_deleted} Duplikate/Orphans gelöscht, "
                f"{stats.raw_updated} MOVE erkannt, {stats.raw_linked} verlinkt"
            )
            
        except Exception as e:
            stats.errors.append(f"Raw-Sync Fehler: {str(e)}")
            logger.error(f"❌ Schritt 3 fehlgeschlagen: {e}")
            self.session.rollback()
        
        return stats
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SCHRITT 2 HELPER: Delta berechnen für Fetch
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_fetch_delta(
        self,
        include_folders: Optional[List[str]] = None,
        since_date: Optional[datetime] = None,
        unseen_only: bool = False
    ) -> Dict[str, List[int]]:
        """
        Berechnet welche Mails noch gefetcht werden müssen.
        
        WICHTIG: Prüft auf ACCOUNT-Ebene, nicht Ordner-Ebene!
        Eine Mail in Archiv ist "vorhanden" auch wenn Filter nur INBOX will.
        
        Args:
            include_folders: Nur aus diesen Ordnern fetchen
            since_date: Nur Mails seit diesem Datum
            unseen_only: Nur ungelesene Mails
        
        Returns:
            Dict[folder, List[uid]] - UIDs die gefetcht werden müssen
        """
        MailServerState = self.models.MailServerState
        RawEmail = self.models.RawEmail
        
        # 1. Was habe ich schon? (message_ids auf ACCOUNT-Ebene!)
        existing_msgids = set()
        existing = self.session.query(RawEmail.message_id).filter(
            RawEmail.user_id == self.user_id,
            RawEmail.mail_account_id == self.account_id,
            RawEmail.deleted_at.is_(None),
            RawEmail.message_id.isnot(None)
        ).all()
        existing_msgids = {r[0] for r in existing if r[0]}
        
        # 2. Was ist auf dem Server? (aus State, gefiltert)
        query = self.session.query(MailServerState).filter(
            MailServerState.user_id == self.user_id,
            MailServerState.mail_account_id == self.account_id,
            MailServerState.is_deleted == False,
            MailServerState.raw_email_id.is_(None)  # Noch nicht gefetcht
        )
        
        if include_folders:
            query = query.filter(MailServerState.folder.in_(include_folders))
        
        if since_date:
            query = query.filter(MailServerState.envelope_date >= since_date)
        
        if unseen_only:
            # State.flags enthält keine \Seen
            query = query.filter(
                ~MailServerState.flags.contains('\\Seen')
            )
        
        candidates = query.all()
        
        # 3. Delta: Kandidaten minus bereits vorhanden (auf Account-Ebene!)
        delta: Dict[str, List[int]] = {}
        
        for entry in candidates:
            # Skip wenn message_id schon in raw_emails existiert (in IRGENDEINEM Ordner!)
            if entry.message_id and entry.message_id in existing_msgids:
                continue
            
            if entry.folder not in delta:
                delta[entry.folder] = []
            delta[entry.folder].append(entry.uid)
        
        total = sum(len(uids) for uids in delta.values())
        logger.info(f"📊 Fetch-Delta: {total} Mails in {len(delta)} Ordnern (Filter: {include_folders or 'alle'})")
        
        return delta
    
    def insert_fetched_mail(
        self,
        folder: str,
        uid: int,
        uidvalidity: int,
        message_id: Optional[str],
        content_hash: str,
        # Verschlüsselte Felder für INSERT (vom Fetch-Worker befüllt)
        encrypted_sender: str,
        encrypted_subject: Optional[str] = None,
        encrypted_body: Optional[str] = None,
        received_at: Optional[datetime] = None,
        flags: Optional[str] = None
    ) -> int:
        """
        SCHRITT 2: INSERT für gefetchte Mail - NUR in raw_emails!
        
        KEINE State-Arbeit! Das macht Schritt 3:
        - raw_email_id in State setzen → Schritt 3
        - folder/uid updates → Schritt 3
        
        WICHTIG: Der Caller muss die verschlüsselten Felder übergeben!
        Diese Methode macht keine Verschlüsselung.
        
        Args:
            folder: IMAP Ordner
            uid: IMAP UID
            uidvalidity: UIDVALIDITY
            message_id: Message-ID Header
            content_hash: Hash aus Date+From+Subject
            encrypted_sender: Verschlüsselter Absender
            encrypted_subject: Verschlüsselter Betreff
            encrypted_body: Verschlüsselter Body
            received_at: Empfangsdatum
            flags: IMAP Flags
        
        Returns:
            raw_email_id
        """
        RawEmail = self.models.RawEmail
        now = datetime.now(UTC)
        
        stable_id = get_stable_id(message_id, content_hash)
        
        # INSERT: Neue Mail mit verschlüsselten Feldern
        new_raw = RawEmail(
            user_id=self.user_id,
            mail_account_id=self.account_id,
            imap_folder=folder,
            imap_uid=uid,
            imap_uidvalidity=uidvalidity,
            message_id=message_id,
            stable_identifier=stable_id,
            content_hash=content_hash,
            # Verschlüsselte Felder
            encrypted_sender=encrypted_sender,
            encrypted_subject=encrypted_subject,
            encrypted_body=encrypted_body,
            received_at=received_at or now,
            # Flags
            imap_is_seen='\\seen' in (flags or '').lower(),
            imap_is_flagged='\\flagged' in (flags or '').lower(),
            imap_is_answered='\\answered' in (flags or '').lower()
        )
        self.session.add(new_raw)
        self.session.flush()  # Get ID
        
        logger.debug(f"📥 Fetch INSERT: {folder}/{uid} (id={new_raw.id})")
        
        return new_raw.id
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _extract_message_id(self, envelope) -> Optional[str]:
        """Extrahiert Message-ID aus ENVELOPE-Objekt"""
        if envelope is None:
            return None
        
        msg_id = getattr(envelope, 'message_id', None)
        if msg_id:
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode('utf-8', errors='replace')
            return msg_id.strip('<>').strip()
        return None
    
    def _extract_envelope_data(self, envelope) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
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


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION: Kompletter Sync-Workflow
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_sync(
    imap_connection,
    db_session,
    user_id: int,
    account_id: int,
    include_folders: Optional[List[str]] = None
) -> SyncStats:
    """
    Führt den kompletten Sync-Workflow aus (Schritt 1 + 3).
    
    Schritt 1: Filter-Ordner scannen → UPDATE/DELETE in state
    Schritt 2: (Fetch) wird separat im Background-Worker gemacht
    Schritt 3: raw_emails mit State synchronisieren
    
    Args:
        imap_connection: IMAPClient Instanz
        db_session: SQLAlchemy Session
        user_id: User ID
        account_id: Mail Account ID
        include_folders: Filter-Ordner die gescannt werden sollen
    
    Returns:
        Kombinierte SyncStats
    """
    service = MailSyncServiceV2(imap_connection, db_session, user_id, account_id)
    
    # Schritt 1: State mit Server synchronisieren (Filter-Ordner!)
    stats1 = service.sync_state_with_server(include_folders)
    
    # Schritt 3: raw_emails mit State synchronisieren
    stats3 = service.sync_raw_emails_with_state()
    
    # Kombinierte Stats
    combined = SyncStats(
        folders_scanned=stats1.folders_scanned,
        mails_on_server=stats1.mails_on_server,
        state_inserted=stats1.state_inserted,
        state_deleted=stats1.state_deleted,
        raw_updated=stats3.raw_updated,
        raw_deleted=stats3.raw_deleted,
        raw_linked=stats3.raw_linked,
        errors=stats1.errors + stats3.errors
    )
    
    return combined
