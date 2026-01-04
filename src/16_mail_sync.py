"""
Phase 13: Mail Synchronization - Server-side Actions
Koordiniert IMAP-Operationen: DELETE, MOVE, FLAGS, etc.

Phase 14c: RFC 4315 UIDPLUS Support
- COPYUID parsing für MOVE operations
- MoveResult dataclass mit neuer UID + UIDVALIDITY
"""

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
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

    def __init__(self, connection: IMAPClient, logger_instance=None):
        """
        Args:
            connection: Aktive IMAPClient Verbindung
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

    def _parse_copyuid_from_untagged(self) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Parst COPYUID aus conn.untagged_responses (imaplib spezifisch)
        
        imaplib versteckt die COPYUID Response in untagged_responses['COPYUID']
        Format: [b'1 437 6'] (ohne [COPYUID ...] prefix!)
        
        Returns:
            (uidvalidity, old_uid, new_uid) oder (None, None, None)
        """
        try:
            # Check untagged_responses dict
            if hasattr(self.conn, 'untagged_responses'):
                copyuid_data = self.conn.untagged_responses.get('COPYUID', [])
                self.logger.info(f"📋 COPYUID from untagged_responses: {copyuid_data}")
                
                if copyuid_data:
                    # Parse first COPYUID entry: b'1 437 6' oder '1 437 6'
                    for item in copyuid_data:
                        try:
                            # Decode bytes
                            if isinstance(item, bytes):
                                item_str = item.decode('utf-8', errors='ignore')
                            else:
                                item_str = str(item)
                            
                            # Split: "1 437 6" → [1, 437, 6]
                            parts = item_str.strip().split()
                            if len(parts) == 3:
                                uidvalidity = int(parts[0])
                                old_uid = int(parts[1])
                                new_uid = int(parts[2])
                                
                                self.logger.info(
                                    f"✅ COPYUID decoded: UIDVALIDITY={uidvalidity}, "
                                    f"{old_uid} → {new_uid}"
                                )
                                return uidvalidity, old_uid, new_uid
                        except Exception as e:
                            self.logger.debug(f"Failed to parse COPYUID item {item}: {e}")
                            continue
            
            return None, None, None
            
        except Exception as e:
            self.logger.error(f"Fehler beim Parsen von untagged COPYUID: {e}")
            return None, None, None

    def delete_email(self, uid: int, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Löscht Mail auf Server (markiert als gelöscht + expunge)
        
        Args:
            uid: IMAP UID der Email
            folder: IMAP Folder (default: INBOX)
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select_folder(folder)
            
            # IMAPClient: set_flags() statt uid('store')
            self.conn.set_flags([uid], ['\\Deleted'])
            
            # Expunge
            self.conn.expunge()
            
            self.logger.info(f"Email {uid} aus {folder} gelöscht")
            return True, "Email gelöscht"
            
        except Exception as e:
            self.logger.error(f"DELETE fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def find_trash_folder(self) -> Optional[str]:
        try:
            # IMAPClient: list_folders() gibt (flags, delimiter, name) tuples
            mailboxes = self.conn.list_folders()
            
            for flags, delimiter, folder_name in mailboxes:
                # Check for \\Trash flag
                if b'\\Trash' in flags or '\\Trash' in str(flags):
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

    def move_to_folder(self, uid: int, target_folder: str, source_folder: str = "INBOX") -> MoveResult:
        """Phase 14c: Verschiebt Email in anderen Ordner (mit COPYUID Support)
        
        RFC 4315 UIDPLUS: COPYUID muss aus untagged_responses geholt werden!
        IMAPClient.copy() gibt nur den Response-String zurück, nicht die COPYUID.
        
        Args:
            uid: IMAP UID
            target_folder: Ziel-Ordner
            source_folder: Quell-Ordner (default: INBOX)
            
        Returns:
            MoveResult mit success, target_uid, target_uidvalidity, message
        """
        try:
            # 1. SELECT source folder
            self.conn.select_folder(source_folder)
            
            # 2. UNTAGGED_RESPONSES CLEAREN (wichtig für sauberen Test!)
            if hasattr(self.conn, '_imap'):
                self.conn._imap.untagged_responses.clear()
                self.logger.info("🧹 Cleared untagged_responses before copy()")
            
            # 3. COPY zu target folder
            self.logger.info(f"📤 Sending IMAP command: UID COPY {uid} {target_folder}")
            copy_response = self.conn.copy([uid], target_folder)
            
            # 4. RAW SERVER RESPONSE DUMPEN
            if hasattr(self.conn, '_imap'):
                self.logger.info("=" * 80)
                self.logger.info("🔥 RAW IMAP SERVER RESPONSE:")
                self.logger.info("=" * 80)
                
                # Zeige tagged response (die eigentliche Antwort auf den Befehl)
                if hasattr(self.conn._imap, 'tagged_commands'):
                    self.logger.info(f"📋 tagged_commands: {self.conn._imap.tagged_commands}")
                
                # Zeige die letzte Response
                if hasattr(self.conn._imap, 'untagged_responses'):
                    raw_untagged = self.conn._imap.untagged_responses
                    self.logger.info(f"📬 UNTAGGED RESPONSES (RAW vom Server):")
                    for key, value in raw_untagged.items():
                        self.logger.info(f"    {key}: {value}")
                
                self.logger.info("=" * 80)
            
            # 5. VOLLSTÄNDIGES LOGGING der copy() Response
            self.logger.info(f"📡 copy() response:")
            self.logger.info(f"  Type: {type(copy_response).__name__}")
            self.logger.info(f"  Value: {repr(copy_response)}")
            
            if isinstance(copy_response, dict):
                self.logger.info(f"  Dict Keys: {list(copy_response.keys())}")
                for key, val in copy_response.items():
                    self.logger.info(f"    {key}: {repr(val)}")
            
            # 5. UNTAGGED_RESPONSES VOLLSTÄNDIG DUMPEN
            if hasattr(self.conn, '_imap'):
                untagged = self.conn._imap.untagged_responses
                self.logger.info(f"📬 untagged_responses keys: {list(untagged.keys())}")
                for key in untagged:
                    self.logger.info(f"  {key}: {repr(untagged[key])}")
            
            # 6. COPYUID EXTRAHIEREN
            target_uid = None
            target_uidvalidity = None
            
            # 6a. Prüfe ob copy_response selbst die COPYUID enthält (idealer Fall)
            if isinstance(copy_response, dict) and 'COPYUID' in copy_response:
                self.logger.info("✅ COPYUID direkt in copy_response gefunden!")
                copyuid = copy_response['COPYUID']
                if isinstance(copyuid, (list, tuple)) and len(copyuid) >= 3:
                    target_uidvalidity = int(copyuid[0])
                    target_uid = int(copyuid[2])
            
            # 6b. Fallback: COPYUID aus untagged_responses holen
            if not target_uid and hasattr(self.conn, '_imap'):
                untagged = self.conn._imap.untagged_responses
                
                if 'COPYUID' in untagged and untagged['COPYUID']:
                    self.logger.info(f"✅ COPYUID in untagged_responses gefunden!")
                    # Format: [b'1 443 8'] → uidvalidity old_uid new_uid
                    copyuid_data = untagged['COPYUID'][0]
                    if isinstance(copyuid_data, bytes):
                        copyuid_str = copyuid_data.decode('utf-8')
                        parts = copyuid_str.split()
                        if len(parts) >= 3:
                            target_uidvalidity = int(parts[0])
                            target_uid = int(parts[2])
                            self.logger.info(f"✅ COPYUID parsed: UIDVAL={target_uidvalidity}, new UID={target_uid}")
                else:
                    self.logger.warning(f"⚠️ Kein COPYUID gefunden! Server unterstützt kein UIDPLUS oder Error")
            
            # 4. DELETE aus source (mark + expunge)
            try:
                self.conn.set_flags([uid], ['\\Deleted'])
                self.conn.expunge()
            except Exception as e:
                self.logger.warning(f"Expunge fehlgeschlagen (Mail ist aber schon kopiert): {e}")
            
            # 5. Erfolgreich!
            if target_uid and target_uidvalidity:
                self.logger.info(
                    f"Email {uid} verschoben: {source_folder} → {target_folder} "
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
                # COPYUID nicht verfügbar
                self.logger.info(
                    f"Email {uid} verschoben: {source_folder} → {target_folder} "
                    f"(COPYUID nicht verfügbar)"
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

    def mark_as_read(self, uid: int, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Markiert Email als gelesen
        
        Args:
            uid: IMAP UID
            folder: IMAP Folder
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select_folder(folder)
            self.conn.set_flags([uid], ['\\Seen'])
            
            self.logger.info(f"Email {uid} als gelesen markiert")
            return True, "Als gelesen markiert"
            
        except Exception as e:
            self.logger.error(f"MARK_READ fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def mark_as_unread(self, uid: int, folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Markiert Email als ungelesen
        
        Args:
            uid: IMAP UID
            folder: IMAP Folder
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select_folder(folder)
            self.conn.remove_flags([uid], ['\\Seen'])
            
            self.logger.info(f"Email {uid} als ungelesen markiert")
            return True, "Als ungelesen markiert"
            
        except Exception as e:
            self.logger.error(f"MARK_UNREAD fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def set_flag(self, uid: int, folder: str = "INBOX") -> Tuple[bool, str]:
        """Markiert Email als wichtig (\\Flagged)"""
        try:
            self.conn.select_folder(folder)
            self.conn.set_flags([uid], ['\\Flagged'])
            
            self.logger.info(f"Email {uid} geflaggt")
            return True, "Als wichtig markiert"
            
        except Exception as e:
            self.logger.error(f"SET_FLAG fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def unset_flag(self, uid: int, folder: str = "INBOX") -> Tuple[bool, str]:
        """Entfernt wichtig-Flag von Email"""
        try:
            self.conn.select_folder(folder)
            self.conn.remove_flags([uid], ['\\Flagged'])
            
            self.logger.info(f"Email {uid} entflaggt")
            return True, "Flagge entfernt"
            
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
