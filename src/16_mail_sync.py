"""
Phase 13: Mail Synchronization - Server-side Actions
Koordiniert IMAP-Operationen: DELETE, MOVE, FLAGS, etc.
"""

import imaplib
import logging
from typing import Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


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

    def move_to_trash(self, uid: str, source_folder: str = "INBOX") -> Tuple[bool, str]:
        """
        Verschiebt Email in Papierkorb durch Verschieben in Trash-Folder
        """
        try:
            trash_folder = self.find_trash_folder()
            if not trash_folder:
                return False, "Papierkorb-Ordner nicht gefunden"
            
            self.conn.select(source_folder)
            typ, resp = self.conn.uid('copy', uid, trash_folder)
            if typ != 'OK':
                return False, f"Fehler beim Kopieren nach {trash_folder}: {resp}"
            
            typ, resp = self.conn.uid('store', uid, '+FLAGS', '\\Deleted')
            if typ != 'OK':
                return False, f"Fehler beim Setzen von \\Deleted Flag: {resp}"
            
            typ, resp = self.conn.expunge()
            if typ != 'OK':
                return False, f"Fehler beim Expunge: {resp}"
            
            self.logger.info(f"Email {uid} aus {source_folder} nach {trash_folder} verschoben")
            return True, f"In {trash_folder} verschoben"
            
        except Exception as e:
            self.logger.error(f"MOVE_TO_TRASH fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

    def move_to_folder(
        self, uid: str, target_folder: str, source_folder: str = "INBOX"
    ) -> Tuple[bool, str]:
        """
        Verschiebt Email in anderen Ordner
        
        Args:
            uid: IMAP UID
            target_folder: Ziel-Ordner (z.B. "Spam", "[Gmail]/Spam")
            source_folder: Quell-Ordner (default: INBOX)
            
        Returns:
            (success, message)
        """
        try:
            self.conn.select(source_folder)
            
            typ, resp = self.conn.uid('copy', uid, target_folder)
            if typ != 'OK':
                return False, f"Fehler beim Copy nach {target_folder}: {resp}"
            
            typ, resp = self.conn.uid('store', uid, '+FLAGS', '\\Deleted')
            if typ != 'OK':
                return False, f"Fehler beim Setzen von \\Deleted: {resp}"
            
            typ, resp = self.conn.expunge()
            if typ != 'OK':
                return False, f"Fehler beim Expunge: {resp}"
            
            self.logger.info(f"Email {uid} von {source_folder} nach {target_folder} verschoben")
            return True, f"Email zu {target_folder} verschoben"
            
        except Exception as e:
            self.logger.error(f"MOVE fehlgeschlagen für UID {uid}: {e}")
            return False, f"Fehler: {str(e)}"

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
        """
        Universelle Methode für alle Sync-Aktionen
        
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
            return self.move_to_folder(uid, target, folder)
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
