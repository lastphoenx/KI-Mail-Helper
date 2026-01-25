"""
Email Action Service - Zentraler Service für alle Email-Aktionen (Single + Bulk)

Prinzip: "Single Point of Truth" für Email-Operationen
- Routes rufen diesen Service auf (dünn, nur HTTP-Handling)
- Service enthält die gesamte Geschäftslogik
- Bulk-Operationen gruppieren nach Account für IMAP-Effizienz

Aktionen:
    DB-only (schnell):
        - mark_done / mark_undone
    
    IMAP + DB (benötigt master_key):
        - move_to_trash
        - delete_permanent
        - move_to_folder
        - mark_read / mark_unread
        - toggle_flag
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any, Tuple
import importlib

logger = logging.getLogger(__name__)


# =============================================================================
# Result Dataclasses
# =============================================================================

@dataclass
class ActionResult:
    """Ergebnis einer einzelnen Email-Aktion"""
    raw_email_id: int
    success: bool
    message: str = ""
    error: Optional[str] = None


@dataclass
class BulkActionResult:
    """Ergebnis einer Bulk-Aktion über mehrere Emails"""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[ActionResult] = field(default_factory=list)
    
    @property
    def all_success(self) -> bool:
        return self.failed == 0 and self.succeeded > 0
    
    @property
    def partial_success(self) -> bool:
        return self.succeeded > 0 and self.failed > 0
    
    def add_success(self, raw_email_id: int, message: str = "OK"):
        self.total += 1
        self.succeeded += 1
        self.results.append(ActionResult(raw_email_id, True, message))
    
    def add_failure(self, raw_email_id: int, error: str):
        self.total += 1
        self.failed += 1
        self.results.append(ActionResult(raw_email_id, False, error=error))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "all_success": self.all_success,
            "partial_success": self.partial_success,
            "results": [
                {
                    "raw_email_id": r.raw_email_id,
                    "success": r.success,
                    "message": r.message,
                    "error": r.error
                }
                for r in self.results
            ]
        }


# =============================================================================
# Lazy Imports (wie in email_actions.py)
# =============================================================================

_models = None
_encryption = None
_mail_fetcher_mod = None
_mail_sync = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


def _get_encryption():
    global _encryption
    if _encryption is None:
        _encryption = importlib.import_module(".08_encryption", "src")
    return _encryption


def _get_mail_fetcher_mod():
    global _mail_fetcher_mod
    if _mail_fetcher_mod is None:
        _mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
    return _mail_fetcher_mod


def _get_mail_sync():
    global _mail_sync
    if _mail_sync is None:
        _mail_sync = importlib.import_module(".16_mail_sync", "src")
    return _mail_sync


# =============================================================================
# Helper Functions
# =============================================================================

def _get_imap_fetcher(account, master_key):
    """Helper: Erstellt IMAP-Fetcher mit entschlüsselten Credentials.
    
    Args:
        account: MailAccount model instance
        master_key: Decrypted master key from session
        
    Returns:
        MailFetcher instance
    """
    encryption = _get_encryption()
    mail_fetcher_mod = _get_mail_fetcher_mod()
    
    imap_server = encryption.CredentialManager.decrypt_server(
        account.encrypted_imap_server, master_key
    )
    imap_username = encryption.CredentialManager.decrypt_email_address(
        account.encrypted_imap_username, master_key
    )
    imap_password = encryption.CredentialManager.decrypt_imap_password(
        account.encrypted_imap_password, master_key
    )
    
    fetcher = mail_fetcher_mod.MailFetcher(
        server=imap_server,
        username=imap_username,
        password=imap_password,
        port=account.imap_port,
    )
    return fetcher


def _validate_email_ownership(db, user_id: int, raw_email_ids: List[int]) -> Tuple[List, List[int]]:
    """Validiert dass alle Email-IDs dem User gehören.
    
    Returns:
        Tuple of (valid_emails, invalid_ids)
        - valid_emails: List of (ProcessedEmail, RawEmail) tuples
        - invalid_ids: List of raw_email_ids that don't belong to user
    """
    models = _get_models()
    
    # Hole alle angefragten Emails in einer Query
    emails = (
        db.query(models.ProcessedEmail, models.RawEmail)
        .join(models.RawEmail)
        .filter(
            models.RawEmail.id.in_(raw_email_ids),
            models.RawEmail.user_id == user_id,
        )
        .all()
    )
    
    found_ids = {raw.id for proc, raw in emails}
    invalid_ids = [eid for eid in raw_email_ids if eid not in found_ids]
    
    return emails, invalid_ids


def _group_emails_by_account(emails) -> Dict[int, List]:
    """Gruppiert Emails nach mail_account_id für effiziente IMAP-Batches.
    
    Args:
        emails: List of (ProcessedEmail, RawEmail) tuples
        
    Returns:
        Dict: {account_id: [(processed, raw), ...]}
    """
    grouped = defaultdict(list)
    for processed, raw in emails:
        grouped[raw.mail_account_id].append((processed, raw))
    return dict(grouped)


def _group_by_folder(emails) -> Dict[str, List]:
    """Gruppiert Emails nach IMAP-Folder.
    
    Args:
        emails: List of (ProcessedEmail, RawEmail) tuples
        
    Returns:
        Dict: {folder_name: [(processed, raw), ...]}
    """
    grouped = defaultdict(list)
    for processed, raw in emails:
        folder = raw.imap_folder or "INBOX"
        grouped[folder].append((processed, raw))
    return dict(grouped)


def _execute_single_imap_action(
    db,
    user_id: int,
    raw_email_id: int,
    master_key: str,
    action_fn,
    action_name: str = "IMAP-Aktion"
) -> ActionResult:
    """Generische Ausführung einer Single-Email IMAP-Aktion.
    
    Kapselt das komplette Boilerplate:
    - Email-Validierung
    - Account-Lookup
    - IMAP-Verbindung aufbauen/schließen
    - Error-Handling
    
    Args:
        db: Database session
        user_id: Current user ID
        raw_email_id: ID der Email
        master_key: Decrypted master key
        action_fn: Callable(synchronizer, processed, raw) -> ActionResult
        action_name: Name für Logging
        
    Returns:
        ActionResult
    """
    models = _get_models()
    mail_sync = _get_mail_sync()
    
    try:
        emails, invalid_ids = _validate_email_ownership(db, user_id, [raw_email_id])
        
        if invalid_ids:
            return ActionResult(raw_email_id, False, error="Email nicht gefunden oder kein Zugriff")
        
        if not emails:
            return ActionResult(raw_email_id, False, error="Email nicht gefunden")
        
        processed, raw = emails[0]
        
        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw.mail_account_id,
                models.MailAccount.user_id == user_id,
            )
            .first()
        )
        
        if not account or account.auth_type != "imap":
            return ActionResult(raw_email_id, False, error="IMAP-Account nicht verfügbar")
        
        fetcher = _get_imap_fetcher(account, master_key)
        
        try:
            fetcher.connect()
            
            if not fetcher.connection:
                return ActionResult(raw_email_id, False, error="IMAP-Verbindung fehlgeschlagen")
            
            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
            
            # Führe die eigentliche Aktion aus
            result = action_fn(synchronizer, processed, raw)
            
            if result.success:
                db.commit()
            
            return result
                
        finally:
            fetcher.disconnect()
            
    except Exception as e:
        db.rollback()
        logger.error(f"❌ {action_name} Fehler: {type(e).__name__}: {e}")
        return ActionResult(raw_email_id, False, error=str(e))


def _execute_bulk_imap_action(
    db,
    user_id: int,
    raw_email_ids: List[int],
    master_key: str,
    action_fn,
    action_name: str = "Bulk-IMAP-Aktion"
) -> BulkActionResult:
    """Generische Ausführung einer Bulk-Email IMAP-Aktion.
    
    Kapselt das komplette Boilerplate:
    - Email-Validierung
    - Gruppierung nach Account
    - IMAP-Verbindung pro Account aufbauen/schließen
    - Gruppierung nach Folder
    - Error-Handling
    
    Args:
        db: Database session
        user_id: Current user ID
        raw_email_ids: Liste der Email-IDs
        master_key: Decrypted master key
        action_fn: Callable(synchronizer, folder, folder_emails) -> List[Tuple[raw_id, success, message]]
        action_name: Name für Logging
        
    Returns:
        BulkActionResult
    """
    models = _get_models()
    mail_sync = _get_mail_sync()
    result = BulkActionResult()
    
    try:
        # 1. Validierung
        emails, invalid_ids = _validate_email_ownership(db, user_id, raw_email_ids)
        
        for invalid_id in invalid_ids:
            result.add_failure(invalid_id, "Email nicht gefunden oder kein Zugriff")
        
        if not emails:
            return result
        
        # 2. Gruppieren nach Account
        by_account = _group_emails_by_account(emails)
        
        # 3. Pro Account: Eine IMAP-Verbindung
        for account_id, account_emails in by_account.items():
            account = (
                db.query(models.MailAccount)
                .filter(
                    models.MailAccount.id == account_id,
                    models.MailAccount.user_id == user_id,
                )
                .first()
            )
            
            if not account or account.auth_type != "imap":
                for processed, raw in account_emails:
                    result.add_failure(raw.id, "IMAP-Account nicht verfügbar")
                continue
            
            fetcher = None
            try:
                fetcher = _get_imap_fetcher(account, master_key)
                fetcher.connect()
                
                if not fetcher.connection:
                    for processed, raw in account_emails:
                        result.add_failure(raw.id, "IMAP-Verbindung fehlgeschlagen")
                    continue
                
                synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
                
                # Gruppieren nach Folder
                by_folder = _group_by_folder(account_emails)
                
                for folder, folder_emails in by_folder.items():
                    try:
                        # Führe die eigentliche Aktion aus
                        action_results = action_fn(synchronizer, folder, folder_emails)
                        
                        for raw_id, success, message in action_results:
                            if success:
                                result.add_success(raw_id, message)
                            else:
                                result.add_failure(raw_id, message)
                                
                    except Exception as e:
                        logger.error(f"{action_name} für folder {folder}: {e}")
                        for _, raw in folder_emails:
                            result.add_failure(raw.id, str(e))
                
            finally:
                if fetcher:
                    fetcher.disconnect()
        
        db.commit()
        logger.info(f"📦 {action_name}: {result.succeeded}/{result.total} erfolgreich")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ {action_name} Fehler: {type(e).__name__}: {e}")
        for eid in raw_email_ids:
            if not any(r.raw_email_id == eid for r in result.results):
                result.add_failure(eid, f"Fehler: {str(e)}")
    
    return result


# =============================================================================
# DB-Only Actions (kein IMAP benötigt)
# =============================================================================

class EmailActionService:
    """Zentraler Service für Email-Aktionen"""
    
    # =========================================================================
    # Mark Done / Undone (DB-only, schnell)
    # =========================================================================
    
    @staticmethod
    def mark_done(db, user_id: int, raw_email_ids: List[int]) -> BulkActionResult:
        """Markiert Emails als erledigt (nur DB, kein IMAP).
        
        Args:
            db: Database session
            user_id: Current user ID
            raw_email_ids: List of raw_email IDs to mark as done
            
        Returns:
            BulkActionResult with success/failure per email
        """
        result = BulkActionResult()
        
        try:
            emails, invalid_ids = _validate_email_ownership(db, user_id, raw_email_ids)
            
            # Füge invalide IDs als Fehler hinzu
            for invalid_id in invalid_ids:
                result.add_failure(invalid_id, "Email nicht gefunden oder kein Zugriff")
            
            # Markiere valide Emails als done
            now = datetime.now(UTC)
            for processed, raw in emails:
                try:
                    if not processed.done:
                        processed.done = True
                        processed.done_at = now
                    result.add_success(raw.id, "Als erledigt markiert")
                except Exception as e:
                    result.add_failure(raw.id, str(e))
            
            db.commit()
            logger.info(f"✅ mark_done: {result.succeeded}/{result.total} erfolgreich")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ mark_done Fehler: {type(e).__name__}: {e}")
            # Alle als fehlgeschlagen markieren
            for eid in raw_email_ids:
                if not any(r.raw_email_id == eid for r in result.results):
                    result.add_failure(eid, f"DB-Fehler: {str(e)}")
        
        return result
    
    @staticmethod
    def mark_undone(db, user_id: int, raw_email_ids: List[int]) -> BulkActionResult:
        """Macht 'erledigt'-Markierung rückgängig (nur DB, kein IMAP).
        
        Args:
            db: Database session
            user_id: Current user ID
            raw_email_ids: List of raw_email IDs to mark as undone
            
        Returns:
            BulkActionResult with success/failure per email
        """
        result = BulkActionResult()
        
        try:
            emails, invalid_ids = _validate_email_ownership(db, user_id, raw_email_ids)
            
            for invalid_id in invalid_ids:
                result.add_failure(invalid_id, "Email nicht gefunden oder kein Zugriff")
            
            for processed, raw in emails:
                try:
                    if processed.done:
                        processed.done = False
                        processed.done_at = None
                    result.add_success(raw.id, "Als offen markiert")
                except Exception as e:
                    result.add_failure(raw.id, str(e))
            
            db.commit()
            logger.info(f"↩️ mark_undone: {result.succeeded}/{result.total} erfolgreich")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ mark_undone Fehler: {type(e).__name__}: {e}")
            for eid in raw_email_ids:
                if not any(r.raw_email_id == eid for r in result.results):
                    result.add_failure(eid, f"DB-Fehler: {str(e)}")
        
        return result
    
    # =========================================================================
    # IMAP Actions (benötigen master_key)
    # =========================================================================
    
    @staticmethod
    def move_to_trash(
        db, 
        user_id: int, 
        raw_email_ids: List[int], 
        master_key: str
    ) -> BulkActionResult:
        """Verschiebt Emails in den Papierkorb (IMAP + DB).
        
        Gruppiert nach Account für effiziente IMAP-Verbindungen.
        
        Args:
            db: Database session
            user_id: Current user ID
            raw_email_ids: List of raw_email IDs to move to trash
            master_key: Decrypted master key for IMAP credentials
            
        Returns:
            BulkActionResult with success/failure per email
        """
        models = _get_models()
        mail_sync = _get_mail_sync()
        result = BulkActionResult()
        
        try:
            # 1. Validierung
            emails, invalid_ids = _validate_email_ownership(db, user_id, raw_email_ids)
            
            for invalid_id in invalid_ids:
                result.add_failure(invalid_id, "Email nicht gefunden oder kein Zugriff")
            
            if not emails:
                return result
            
            # 2. Gruppieren nach Account
            by_account = _group_emails_by_account(emails)
            
            # 3. Pro Account: Eine IMAP-Verbindung, alle Emails verarbeiten
            for account_id, account_emails in by_account.items():
                account = (
                    db.query(models.MailAccount)
                    .filter(
                        models.MailAccount.id == account_id,
                        models.MailAccount.user_id == user_id,
                    )
                    .first()
                )
                
                if not account or account.auth_type != "imap":
                    for processed, raw in account_emails:
                        result.add_failure(raw.id, "IMAP-Account nicht verfügbar")
                    continue
                
                fetcher = None
                try:
                    fetcher = _get_imap_fetcher(account, master_key)
                    fetcher.connect()
                    
                    if not fetcher.connection:
                        for processed, raw in account_emails:
                            result.add_failure(raw.id, "IMAP-Verbindung fehlgeschlagen")
                        continue
                    
                    synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
                    
                    # Trash-Folder einmalig ermitteln für diesen Account
                    trash_folder = synchronizer.find_trash_folder()
                    
                    # Gruppieren nach Folder für Bulk-Operationen
                    by_folder = _group_by_folder(account_emails)
                    
                    for folder, folder_emails in by_folder.items():
                        # Separiere: bereits im Trash vs. zu verschieben
                        emails_to_move = []
                        email_lookup = {}  # imap_uid -> (processed, raw)
                        
                        for processed, raw in folder_emails:
                            # Edge-Case: Bereits im Trash?
                            current_folder = raw.imap_folder or "INBOX"
                            if trash_folder and current_folder.lower() == trash_folder.lower():
                                # Bereits im Papierkorb - nur DB-Status aktualisieren
                                if not processed.deleted_at:
                                    processed.deleted_at = datetime.now(UTC)
                                result.add_success(raw.id, "Bereits im Papierkorb")
                                logger.debug(f"⏭️ Email {raw.id} bereits im Trash, übersprungen")
                            else:
                                emails_to_move.append((processed, raw))
                                email_lookup[raw.imap_uid] = (processed, raw, raw.id)
                        
                        if not emails_to_move:
                            continue
                        
                        # TRUE BULK IMAP: Ein Befehl für alle UIDs im Folder!
                        uids_to_move = [raw.imap_uid for _, raw in emails_to_move]
                        logger.info(f"🚀 BULK move_to_trash: {len(uids_to_move)} UIDs aus {folder}")
                        
                        try:
                            bulk_results = synchronizer.move_to_trash_bulk(uids_to_move, folder)
                            
                            # Verarbeite Bulk-Ergebnisse
                            for uid, move_result in bulk_results.items():
                                if uid in email_lookup:
                                    processed, raw, raw_id = email_lookup[uid]
                                    
                                    if move_result.success:
                                        # DB-Update
                                        raw.imap_folder = move_result.target_folder
                                        if move_result.target_uid is not None:
                                            raw.imap_uid = move_result.target_uid
                                        if move_result.target_uidvalidity is not None:
                                            raw.imap_uidvalidity = move_result.target_uidvalidity
                                        processed.deleted_at = datetime.now(UTC)
                                        
                                        result.add_success(raw_id, move_result.message)
                                    else:
                                        result.add_failure(raw_id, move_result.message)
                        except Exception as e:
                            logger.error(f"Bulk move_to_trash für folder {folder}: {e}")
                            for _, raw in emails_to_move:
                                result.add_failure(raw.id, str(e))
                    
                finally:
                    if fetcher:
                        fetcher.disconnect()
            
            db.commit()
            logger.info(f"🗑️ move_to_trash: {result.succeeded}/{result.total} erfolgreich")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ move_to_trash Fehler: {type(e).__name__}: {e}")
            for eid in raw_email_ids:
                if not any(r.raw_email_id == eid for r in result.results):
                    result.add_failure(eid, f"Fehler: {str(e)}")
        
        return result
    
    @staticmethod
    def delete_permanent(
        db, 
        user_id: int, 
        raw_email_ids: List[int], 
        master_key: str
    ) -> BulkActionResult:
        """Löscht Emails permanent auf dem Server (IMAP EXPUNGE + DB).
        
        Args:
            db: Database session
            user_id: Current user ID
            raw_email_ids: List of raw_email IDs to delete permanently
            master_key: Decrypted master key for IMAP credentials
            
        Returns:
            BulkActionResult with success/failure per email
        """
        models = _get_models()
        mail_sync = _get_mail_sync()
        result = BulkActionResult()
        
        try:
            # 1. Validierung
            emails, invalid_ids = _validate_email_ownership(db, user_id, raw_email_ids)
            
            for invalid_id in invalid_ids:
                result.add_failure(invalid_id, "Email nicht gefunden oder kein Zugriff")
            
            if not emails:
                return result
            
            # 2. Gruppieren nach Account
            by_account = _group_emails_by_account(emails)
            
            # 3. Pro Account: Eine IMAP-Verbindung
            for account_id, account_emails in by_account.items():
                account = (
                    db.query(models.MailAccount)
                    .filter(
                        models.MailAccount.id == account_id,
                        models.MailAccount.user_id == user_id,
                    )
                    .first()
                )
                
                if not account or account.auth_type != "imap":
                    for processed, raw in account_emails:
                        result.add_failure(raw.id, "IMAP-Account nicht verfügbar")
                    continue
                
                fetcher = None
                try:
                    fetcher = _get_imap_fetcher(account, master_key)
                    fetcher.connect()
                    
                    if not fetcher.connection:
                        for processed, raw in account_emails:
                            result.add_failure(raw.id, "IMAP-Verbindung fehlgeschlagen")
                        continue
                    
                    synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
                    
                    # Gruppieren nach Folder
                    by_folder = _group_by_folder(account_emails)
                    
                    for folder, folder_emails in by_folder.items():
                        for processed, raw in folder_emails:
                            try:
                                success, message = synchronizer.delete_email(
                                    raw.imap_uid,
                                    folder
                                )
                                
                                if success:
                                    processed.deleted_at = datetime.now(UTC)
                                    result.add_success(raw.id, message)
                                else:
                                    result.add_failure(raw.id, message)
                                    
                            except Exception as e:
                                logger.error(f"delete_permanent für {raw.id}: {e}")
                                result.add_failure(raw.id, str(e))
                    
                finally:
                    if fetcher:
                        fetcher.disconnect()
            
            db.commit()
            logger.info(f"🗑️ delete_permanent: {result.succeeded}/{result.total} erfolgreich")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ delete_permanent Fehler: {type(e).__name__}: {e}")
            for eid in raw_email_ids:
                if not any(r.raw_email_id == eid for r in result.results):
                    result.add_failure(eid, f"Fehler: {str(e)}")
        
        return result
    
    @staticmethod
    def move_to_folder(
        db, 
        user_id: int, 
        raw_email_id: int,
        target_folder: str,
        master_key: str
    ) -> ActionResult:
        """Verschiebt eine Email in einen bestimmten Ordner (IMAP + DB)."""
        
        def action(synchronizer, processed, raw):
            source_folder = raw.imap_folder or "INBOX"
            move_result = synchronizer.move_to_folder(
                raw.imap_uid, target_folder, source_folder
            )
            
            if move_result.success:
                raw.imap_folder = move_result.target_folder
                if move_result.target_uid is not None:
                    raw.imap_uid = move_result.target_uid
                if move_result.target_uidvalidity is not None:
                    raw.imap_uidvalidity = move_result.target_uidvalidity
                raw.imap_last_seen_at = datetime.now(UTC)
                logger.info(f"📁 Email {raw.id} zu {target_folder} verschoben")
                return ActionResult(raw.id, True, move_result.message)
            else:
                return ActionResult(raw.id, False, error=move_result.message)
        
        return _execute_single_imap_action(
            db, user_id, raw_email_id, master_key, action, "move_to_folder"
        )
    
    @staticmethod
    def toggle_read(
        db, 
        user_id: int, 
        raw_email_id: int,
        master_key: str
    ) -> ActionResult:
        """Togglet Gelesen/Ungelesen Status einer Email (IMAP + DB)."""
        
        def action(synchronizer, processed, raw):
            folder = raw.imap_folder or "INBOX"
            
            if raw.imap_is_seen:
                success, message = synchronizer.mark_as_unread(raw.imap_uid, folder)
                new_state = False
            else:
                success, message = synchronizer.mark_as_read(raw.imap_uid, folder)
                new_state = True
            
            if success:
                raw.imap_is_seen = new_state
                logger.info(f"👁️ Email {raw.id} toggle-read: is_seen={new_state}")
                return ActionResult(raw.id, True, f"is_seen:{new_state}")
            else:
                return ActionResult(raw.id, False, error=message)
        
        return _execute_single_imap_action(
            db, user_id, raw_email_id, master_key, action, "toggle_read"
        )
    
    @staticmethod
    def mark_read(
        db, 
        user_id: int, 
        raw_email_id: int,
        master_key: str
    ) -> ActionResult:
        """Markiert eine Email als gelesen (IMAP + DB)."""
        
        def action(synchronizer, processed, raw):
            folder = raw.imap_folder or "INBOX"
            success, message = synchronizer.mark_as_read(raw.imap_uid, folder)
            
            if success:
                raw.imap_is_seen = True
                logger.info(f"👁️ Email {raw.id} als gelesen markiert")
                return ActionResult(raw.id, True, message)
            else:
                return ActionResult(raw.id, False, error=message)
        
        return _execute_single_imap_action(
            db, user_id, raw_email_id, master_key, action, "mark_read"
        )
    
    @staticmethod
    def toggle_flag(
        db, 
        user_id: int, 
        raw_email_id: int,
        master_key: str
    ) -> ActionResult:
        """Togglet Wichtig-Flag einer Email (IMAP + DB)."""
        
        def action(synchronizer, processed, raw):
            folder = raw.imap_folder or "INBOX"
            
            if raw.imap_is_flagged:
                success, message = synchronizer.unset_flag(raw.imap_uid, folder)
                new_state = False
            else:
                success, message = synchronizer.set_flag(raw.imap_uid, folder)
                new_state = True
            
            if success:
                raw.imap_is_flagged = new_state
                logger.info(f"🚩 Email {raw.id} toggle-flag: flagged={new_state}")
                return ActionResult(raw.id, True, f"flagged:{new_state}")
            else:
                return ActionResult(raw.id, False, error=message)
        
        return _execute_single_imap_action(
            db, user_id, raw_email_id, master_key, action, "toggle_flag"
        )
    
    # =========================================================================
    # Convenience Methods für Single-Email (Wrapper)
    # =========================================================================
    
    @staticmethod
    def mark_done_single(db, user_id: int, raw_email_id: int) -> ActionResult:
        """Convenience: Markiert eine einzelne Email als erledigt."""
        bulk_result = EmailActionService.mark_done(db, user_id, [raw_email_id])
        if bulk_result.results:
            return bulk_result.results[0]
        return ActionResult(raw_email_id, False, error="Unbekannter Fehler")
    
    @staticmethod
    def mark_undone_single(db, user_id: int, raw_email_id: int) -> ActionResult:
        """Convenience: Macht 'erledigt' für eine Email rückgängig."""
        bulk_result = EmailActionService.mark_undone(db, user_id, [raw_email_id])
        if bulk_result.results:
            return bulk_result.results[0]
        return ActionResult(raw_email_id, False, error="Unbekannter Fehler")
    
    @staticmethod
    def move_to_trash_single(
        db, user_id: int, raw_email_id: int, master_key: str
    ) -> ActionResult:
        """Convenience: Verschiebt eine Email in den Papierkorb."""
        bulk_result = EmailActionService.move_to_trash(
            db, user_id, [raw_email_id], master_key
        )
        if bulk_result.results:
            return bulk_result.results[0]
        return ActionResult(raw_email_id, False, error="Unbekannter Fehler")
    
    @staticmethod
    def delete_permanent_single(
        db, user_id: int, raw_email_id: int, master_key: str
    ) -> ActionResult:
        """Convenience: Löscht eine Email permanent."""
        bulk_result = EmailActionService.delete_permanent(
            db, user_id, [raw_email_id], master_key
        )
        if bulk_result.results:
            return bulk_result.results[0]
        return ActionResult(raw_email_id, False, error="Unbekannter Fehler")
