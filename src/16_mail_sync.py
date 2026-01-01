"""
Phase 13: Mail Synchronization - Server-side Actions
Koordiniert IMAP-Operationen: DELETE, MOVE, FLAGS, etc.

Phase 14c: RFC 4315 UIDPLUS Support
- COPYUID parsing für MOVE operations
- MoveResult dataclass mit neuer UID + UIDVALIDITY
"""

import imaplib
import logging
import re
from typing import Optional, Tuple
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MoveResult:
    """Phase 14c: Ergebnis einer MOVE-Operation
    
    RFC 4315 UIDPLUS: Nach COPY/MOVE gibt Server COPYUID zurück:
    * OK [COPYUID <uidvalidity> <old-uid> <new-uid>]
    
    Attributes:
        success: Operation erfolgreich?
        target_folder: Ziel-Ordner
        target_uid: Neue UID im Ziel-Ordner (None wenn Parsing fehlschlägt)
        target_uidvalidity: UIDVALIDITY des Ziel-Ordners (None wenn nicht verfügbar)
        message: Erfolgs- oder Fehlermeldung
    """
    success: bool
    target_folder: str
    target_uid: Optional[int] = None
    target_uidvalidity: Optional[int] = None
    message: str = ""


class SyncAction(Enum):
    """Verfügbare Server-Sync Aktionen"""
    DELETE = "delete"
    MOVE = "move"
    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    FLAG = "flag"
    UNFLAG = "unflag"


class MailSynchronizer:
    """Synchronisiert Änderungen mit IMAP-Server"""

    def __init__(self, connection: imaplib.IMAP4_SSL, logger_instance=None):
        """
        Args:
            connection: Aktive IMAP4_SSL Verbindung
            logger_instance: Optional logger instance
        """
        self.conn = connection
        self.logger = logger_instance or logger
    
    def _parse_copyuid(self, response_data) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Phase 14c: Parst COPYUID aus IMAP Response (RFC 4315 UIDPLUS)
        
        COPYUID Format: [COPYUID <uidvalidity> <old-uid-set> <new-uid-set>]
        Beispiele:
        - * OK [COPYUID 1 424 17]
        - * OK [COPYUID 1702396800 123 456]
        - (\\Deleted) [COPYUID 1 424 17]
        
        Args:
            response_data: IMAP response (bytes oder tuple)
            
        Returns:
            (uidvalidity, old_uid, new_uid) oder (None, None, None)
        """
        try:
            # Response kann verschiedene Formate haben
            response_str = ""
            
            if isinstance(response_data, (list, tuple)):
                for item in response_data:
                    if isinstance(item, bytes):
                        response_str += item.decode('utf-8', errors='ignore') + " "
                    elif isinstance(item, str):
                        response_str += item + " "
            elif isinstance(response_data, bytes):
                response_str = response_data.decode('utf-8', errors='ignore')
            elif isinstance(response_data, str):
                response_str = response_data
            
            # COPYUID Pattern: [COPYUID <uidvalidity> <old-uid> <new-uid>]
            # Flexibles Pattern für verschiedene Server
            patterns = [
                r'\[COPYUID\s+(\d+)\s+(\d+)\s+(\d+)\]',  # Standard
                r'COPYUID\s+(\d+)\s+(\d+)\s+(\d+)',      # Ohne Brackets
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response_str)
                if match:
                    uidvalidity = int(match.group(1))
                    old_uid = int(match.group(2))
                    new_uid = int(match.group(3))
                    
                    self.logger.debug(
                        f"COPYUID parsed: UIDVALIDITY={uidvalidity}, "
                        f"{old_uid} → {new_uid}"
                    )
                    
                    return uidvalidity, old_uid, new_uid
            
            # Kein COPYUID gefunden (Server unterstützt UIDPLUS nicht)
            self.logger.debug(f"Kein COPYUID in Response: {response_str[:200]}")
            return None, None, None
            
        except Exception as e:
            self.logger.error(f"Fehler beim Parsen von COPYUID: {e}")
            return None, None, None

    def delete_email(self, uid: str, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Löscht Mail auf Server (markiert als gelöscht + expunge)
        
        Args:
            uid: IMAP UID der Email
            folder: IMAP Folder (default: INBOX)
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select(folder)
            
            typ, resp = self.conn.uid('store', uid, '+FLAGS', '\\Deleted')
            if typ != 'OK':
                return False, f"Fehler beim Setzen von \\Deleted Flag: {resp}"
            
            typ, resp = self.conn.expunge()
            if typ != 'OK':
                return False, f"Fehler beim Expunge: {resp}"
            
            self.logger.info(f"Email {uid} aus {folder} gelöscht")
            return True, "Email gelöscht"
            
        except Exception as e:
            self.logger.error(f"DELETE fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def find_trash_folder(self) -> Optional[str]:
        try:
            typ, mailboxes = self.conn.list()
            if typ != 'OK':
                return None
            for mailbox in mailboxes:
                if not mailbox:
                    continue
                mailbox_str = mailbox.decode('utf-8') if isinstance(mailbox, bytes) else str(mailbox)
                if '\\Trash' in mailbox_str:
                    parts = mailbox_str.split('" ', 1)
                    if len(parts) > 1:
                        folder_name = parts[1].strip()
                        if folder_name.startswith('"') and folder_name.endswith('"'):
                            folder_name = folder_name[1:-1]
                        return folder_name
            return None
        except Exception as e:
            self.logger.error(f"Fehler beim Suchen von Trash-Folder: {e}")
            return None

    def move_to_trash(self, uid: str, source_folder: str = "INBOX") -> MoveResult:
        """Phase 14c: Verschiebt Email in Papierkorb (mit COPYUID Support)
        
        Returns:
            MoveResult statt (bool, str) Tuple
        """
        try:
            trash_folder = self.find_trash_folder()
            if not trash_folder:
                return MoveResult(
                    success=False,
                    target_folder="Trash",
                    message="Papierkorb-Ordner nicht gefunden"
                )
            
            # Nutze move_to_folder (gibt jetzt MoveResult zurück)
            return self.move_to_folder(uid, trash_folder, source_folder)
            
        except Exception as e:
            self.logger.error(f"MOVE_TO_TRASH fehlgeschlagen für UID {uid}: {e}")
            return MoveResult(
                success=False,
                target_folder="Trash",
                message=f"Fehler: {str(e)}"
            )

    def move_to_folder(
        self, uid: str, target_folder: str, source_folder: str = "INBOX"
    ) -> MoveResult:
        """Phase 14c: Verschiebt Email in anderen Ordner (mit COPYUID Support)
        
        RFC 4315 UIDPLUS: Nach COPY gibt Server neue UID zurük:
        * OK [COPYUID <uidvalidity> <old-uid> <new-uid>]
        
        Args:
            uid: IMAP UID (kann str oder int sein)
            target_folder: Ziel-Ordner (z.B. "Spam", "[Gmail]/Spam")
            source_folder: Quell-Ordner (default: INBOX)
            
        Returns:
            MoveResult mit success, target_uid, target_uidvalidity, message
        """
        try:
            # Sicherstellen dass UID ein String ist
            uid_str = str(uid)
            
            # 1. SELECT source folder
            self.conn.select(source_folder)
            
            # 2. COPY to target folder
            typ, copy_resp = self.conn.uid('copy', uid_str, target_folder)
            if typ != 'OK':
                return MoveResult(
                    success=False,
                    target_folder=target_folder,
                    message=f"Fehler beim Copy nach {target_folder}: {copy_resp}"
                )
            
            # 3. Parse COPYUID aus Response (RFC 4315)
            target_uidvalidity, old_uid, target_uid = self._parse_copyuid(copy_resp)
            
            # 4. DELETE from source (mark + expunge)
            typ, store_resp = self.conn.uid('store', uid_str, '+FLAGS', '\\Deleted')
            if typ != 'OK':
                self.logger.warning(
                    f"Copy erfolgreich aber Deleted-Flag setzen fehlgeschlagen: {store_resp}"
                )
                return MoveResult(
                    success=False,
                    target_folder=target_folder,
                    target_uid=target_uid,
                    target_uidvalidity=target_uidvalidity,
                    message=f"Fehler beim Setzen von \\Deleted: {store_resp}"
                )
            
            typ, expunge_resp = self.conn.expunge()
            if typ != 'OK':
                self.logger.warning(f"Expunge fehlgeschlagen: {expunge_resp}")
                # Nicht kritisch, Mail ist schon kopiert
            
            # 5. Erfolgreich!
            if target_uid and target_uidvalidity:
                self.logger.info(
                    f"Email {uid_str} verschoben: {source_folder} → {target_folder} "
                    f"(neue UID: {target_uid}, UIDVALIDITY: {target_uidvalidity})"
                )
                return MoveResult(
                    success=True,
                    target_folder=target_folder,
                    target_uid=target_uid,
                    target_uidvalidity=target_uidvalidity,
                    message=f"Email zu {target_folder} verschoben (UID: {target_uid})"
                )
            else:
                # COPYUID nicht verfügbar (Server ohne UIDPLUS)
                self.logger.info(
                    f"Email {uid_str} verschoben: {source_folder} → {target_folder} "
                    f"(COPYUID nicht verfügbar, Server unterstützt UIDPLUS nicht)"
                )
                return MoveResult(
                    success=True,
                    target_folder=target_folder,
                    message=f"Email zu {target_folder} verschoben (neue UID unbekannt)"
                )
            
        except Exception as e:
            self.logger.error(f"MOVE fehlgeschlagen für UID {uid}: {e}")
            return MoveResult(
                success=False,
                target_folder=target_folder,
                message=f"Fehler: {str(e)}"
            )

    def mark_as_read(self, uid: str, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Markiert Email als gelesen
        
        Args:
            uid: IMAP UID
            folder: IMAP Folder
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select(folder)
            
            typ, resp = self.conn.uid('store', uid, '+FLAGS', '\\Seen')
            if typ != 'OK':
                return False, f"Fehler beim Setzen von \\Seen: {resp}"
            
            self.logger.info(f"Email {uid} als gelesen markiert")
            return True, "Als gelesen markiert"
            
        except Exception as e:
            self.logger.error(f"MARK_READ fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def mark_as_unread(self, uid: str, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Markiert Email als ungelesen
        
        Args:
            uid: IMAP UID
            folder: IMAP Folder
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select(folder)
            
            typ, resp = self.conn.uid('store', uid, '-FLAGS', '\\Seen')
            if typ != 'OK':
                return False, f"Fehler beim Entfernen von \\Seen: {resp}"
            
            self.logger.info(f"Email {uid} als ungelesen markiert")
            return True, "Als ungelesen markiert"
            
        except Exception as e:
            self.logger.error(f"MARK_UNREAD fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def set_flag(self, uid: str, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Markiert Email als wichtig (\\Flagged)
        
        Args:
            uid: IMAP UID
            folder: IMAP Folder
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select(folder)
            
            typ, resp = self.conn.uid('store', uid, '+FLAGS', '\\Flagged')
            if typ != 'OK':
                return False, f"Fehler beim Setzen von \\Flagged: {resp}"
            
            self.logger.info(f"Email {uid} als wichtig markiert")
            return True, "Als wichtig markiert"
            
        except Exception as e:
            self.logger.error(f"SET_FLAG fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def unset_flag(self, uid: str, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Entfernt wichtig-Markierung (\\Flagged)
        
        Args:
            uid: IMAP UID
            folder: IMAP Folder
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select(folder)
            
            typ, resp = self.conn.uid('store', uid, '-FLAGS', '\\Flagged')
            if typ != 'OK':
                return False, f"Fehler beim Entfernen von \\Flagged: {resp}"
            
            self.logger.info(f"Email {uid} als nicht-wichtig markiert")
            return True, "Wichtig-Markierung entfernt"
            
        except Exception as e:
            self.logger.error(f"UNSET_FLAG fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def perform_action(
        self, action: SyncAction, uid: str, folder: str = "INBOX", **kwargs
    ) -> Tuple[bool, str]:
        """Universelle Methode für alle Sync-Aktionen
        
        Phase 14c: MOVE gibt jetzt MoveResult zurück, wird hier zu (bool, str) konvertiert
        
        Args:
            action: SyncAction enum
            uid: IMAP UID
            folder: Source folder
            **kwargs: z.B. target_folder für MOVE
            
        Returns:
            (success, message)
        """
        if action == SyncAction.DELETE:
            return self.delete_email(uid, folder)
        elif action == SyncAction.MOVE:
            target = kwargs.get('target_folder')
            if not target:
                return False, "target_folder erforderlich für MOVE"
            result = self.move_to_folder(uid, target, folder)
            return result.success, result.message  # MoveResult → Tuple
        elif action == SyncAction.MARK_READ:
            return self.mark_as_read(uid, folder)
        elif action == SyncAction.MARK_UNREAD:
            return self.mark_as_unread(uid, folder)
        elif action == SyncAction.FLAG:
            return self.set_flag(uid, folder)
        elif action == SyncAction.UNFLAG:
            return self.unset_flag(uid, folder)
        else:
            return False, f"Unbekannte Aktion: {action}"
