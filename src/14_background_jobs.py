"""Simple Background Worker Queue for Mail Fetch + KI-Verarbeitung."""

from __future__ import annotations

import importlib
import logging
import threading
import uuid
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Dict, Optional
from datetime import datetime, UTC

models = importlib.import_module(".02_models", "src")
mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
google_oauth = importlib.import_module(".10_google_oauth", "src")
encryption = importlib.import_module(".08_encryption", "src")
processing = importlib.import_module(".12_processing", "src")
ai_client = importlib.import_module(".03_ai_client", "src")

logger = logging.getLogger(__name__)

# Layer 4 Security: Resource Exhaustion Prevention
MAX_EMAILS_PER_REQUEST = 1000


@dataclass
class FetchJob:
    job_id: str
    user_id: int
    account_id: int
    master_key: str
    provider: str
    model: str
    max_mails: int = 50
    sanitize_level: int = 2
    meta: Dict[str, Any] = field(default_factory=dict)


class BackgroundJobQueue:
    """Kleiner in-memory Job-Queue mit einem Worker-Thread."""

    # Security: Limit queue size to prevent memory exhaustion
    MAX_QUEUE_SIZE = 50

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.queue: Queue[FetchJob] = Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._status: Dict[str, Dict[str, Any]] = {}
        self._status_lock = threading.Lock()
        self._SessionFactory = self._init_session_factory()

    def _init_session_factory(self):
        _, Session = models.init_db(self.db_path)
        return Session

    def ensure_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run, name="mail-helper-worker", daemon=True
        )
        self._worker.start()
        logger.info("🧵 Hintergrund-Worker gestartet")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2)

    def enqueue_fetch_job(
        self,
        *,
        user_id: int,
        account_id: int,
        master_key: str,
        provider: str,
        model: str,
        max_mails: int,
        sanitize_level: int,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not master_key:
            raise ValueError("master_key ist erforderlich")
        
        if max_mails > MAX_EMAILS_PER_REQUEST:
            raise ValueError(
                f"max_mails darf maximal {MAX_EMAILS_PER_REQUEST} sein (gegeben: {max_mails})"
            )

        job_id = uuid.uuid4().hex
        job = FetchJob(
            job_id=job_id,
            user_id=user_id,
            account_id=account_id,
            master_key=master_key,
            provider=provider,
            model=model,
            max_mails=max_mails,
            sanitize_level=sanitize_level,
            meta=meta or {},
        )
        try:
            self.queue.put(job, block=False)
        except Exception:
            raise ValueError(
                f"Job-Queue ist voll ({self.MAX_QUEUE_SIZE} Jobs). Bitte warten..."
            )
        self._update_status(
            job_id,
            {
                "state": "queued",
                "user_id": user_id,
                "account_id": account_id,
                "provider": provider,
            },
        )
        self.ensure_worker()
        logger.info(
            "📥 Job %s eingereiht (User %s, Account %s)", job_id, user_id, account_id
        )
        return job_id

    def get_status(self, job_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        with self._status_lock:
            status = self._status.get(job_id)
            if not status or status.get("user_id") != user_id:
                return None
            filtered = status.copy()
            filtered.pop("user_id", None)
            return filtered

    def _update_status(self, job_id: str, payload: Dict[str, Any]) -> None:
        with self._status_lock:
            self._status[job_id] = {**self._status.get(job_id, {}), **payload}

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self.queue.get(timeout=1)
            except Empty:
                continue
            try:
                self._update_status(job.job_id, {"state": "running"})
                self._execute_job(job)
            except Exception:
                logger.exception("Unerwarteter Fehler im Worker")
            finally:
                self.queue.task_done()

    def _execute_job(self, job: FetchJob) -> None:
        session = self._SessionFactory()
        saved = 0
        processed = 0
        try:
            user = session.query(models.User).filter_by(id=job.user_id).first()
            if not user:
                raise ValueError("User nicht gefunden")

            account = (
                session.query(models.MailAccount)
                .filter_by(id=job.account_id, user_id=job.user_id)
                .first()
            )
            if not account:
                raise ValueError("Mail-Account nicht gefunden")

            master_key = job.master_key
            if not master_key:
                raise ValueError("Master-Key fehlt im Job")

            # Phase 13C Part 3: FULL SYNC Mode - keine Filter mehr!
            # Problem: UNSEEN-Filter führt zu unvollständigem Sync (nur 2/20 Mails in INBOX)
            # Lösung: ALLE Mails aus ALLEN Ordnern fetchen (Server = Single Source of Truth)
            
            raw_emails = self._fetch_raw_emails(
                account, master_key, job.max_mails
            )
            
            # Phase 13C Part 3 FINAL: Keine Deduplizierung nötig!
            # IMAP UID ist eindeutig pro (account, folder, uid)
            # INBOX/UID=123 ≠ Archiv/UID=123 (verschiedene IMAP-Objekte!)
            # → _persist_raw_emails() macht INSERT/UPDATE per (account, folder, uid)
            
            if raw_emails:
                logger.info(f"📧 {len(raw_emails)} Mails abgerufen, speichere in DB...")
                saved = self._persist_raw_emails(
                    session, user, account, raw_emails, master_key
                )

            ai_instance = ai_client.build_client(job.provider, model=job.model)

            def progress_callback(idx: int, total: int, subject: str) -> None:
                self._update_status(
                    job.job_id,
                    {
                        "current_email_index": idx,
                        "total_emails": total,
                        "current_subject": subject,
                    },
                )

            processed = processing.process_pending_raw_emails(
                session=session,
                user=user,
                master_key=master_key,
                mail_account=account,
                limit=job.max_mails,
                ai=ai_instance,
                sanitize_level=job.sanitize_level,
                progress_callback=progress_callback,
            )

            account.last_fetch_at = datetime.now(UTC)
            
            if not account.initial_sync_done:
                account.initial_sync_done = True
                logger.info(f"🎉 Initialer Sync für Account {account.id} abgeschlossen")
            
            session.commit()

            self._update_status(
                job.job_id,
                {
                    "state": "done",
                    "saved": saved,
                    "processed": processed,
                    "account_id": job.account_id,
                },
            )
            logger.info(
                "✅ Job %s abgeschlossen (saved=%s, processed=%s)",
                job.job_id,
                saved,
                processed,
            )
        except Exception as exc:
            session.rollback()
            logger.error("❌ Job %s fehlgeschlagen: %s", job.job_id, exc, exc_info=True)
            self._update_status(
                job.job_id,
                {
                    "state": "error",
                    "message": "Verarbeitung fehlgeschlagen (siehe Server-Logs)",
                },
            )
        finally:
            session.close()

    def _fetch_raw_emails(
        self, account, master_key: str, limit: int
    ) -> list[Dict[str, Any]]:
        """
        Fetcht Mails aus ALLEN Ordnern (Phase 13C: Multi-Folder FULL SYNC)
        
        Phase 13C Part 3: KEIN UNSEEN-Filter mehr!
        Problem: UNSEEN-Filter führte zu unvollständigem Sync (nur 2/20 Mails)
        Lösung: Server = Single Source of Truth → ALLE Mails fetchen
        
        Phase 13C Part 4: Delta-Sync Option
        - Wenn user.fetch_use_delta_sync=True: Nur neue Mails seit letztem Sync
        - Sonst: FULL SYNC (alle Mails)
        
        Warum? Mails können manuell (außerhalb App) verschoben werden.
        Wir müssen alle Ordner scannen, um DB mit Server zu synchronisieren.
        """
        if account.oauth_provider == "google":
            decrypted_token = encryption.CredentialManager.decrypt_imap_password(
                account.encrypted_oauth_token, master_key
            )
            fetcher = google_oauth.GoogleMailFetcher(access_token=decrypted_token)
            # Google OAuth: Nur INBOX (Gmail nutzt Labels, nicht Folders)
            return fetcher.fetch_new_emails(limit=limit)

        if not account.encrypted_imap_password:
            raise ValueError("Kein IMAP-Passwort gespeichert")

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
        fetcher.connect()
        try:
            # Phase 13C: Fetch aus ALLEN Ordnern, nicht nur INBOX
            all_emails = []
            
            # 1. Liste alle Ordner
            typ, mailboxes = fetcher.connection.list()
            if typ != "OK":
                logger.warning("Konnte Ordner nicht listen, falle zurück auf INBOX")
                return fetcher.fetch_new_emails(folder="INBOX", limit=limit, unseen_only=False)
            
            # Phase 13C Part 4 FIX: Speichere RAW + DECODED Namen
            # WICHTIG: IMAP Commands (SELECT, STATUS) brauchen RAW UTF-7 Namen!
            #          Aber DB und Logs nutzen DECODED UTF-8 Namen!
            folders = []  # Liste von (raw_name, decoded_name) Tuples
            for mailbox in mailboxes:
                if not mailbox:
                    continue
                mailbox_str = (
                    mailbox.decode("utf-8") if isinstance(mailbox, bytes) else str(mailbox)
                )
                parts = mailbox_str.split('" ')
                if len(parts) >= 2:
                    folder_name_raw = parts[1].strip()
                    if folder_name_raw.startswith('"') and folder_name_raw.endswith('"'):
                        folder_name_raw = folder_name_raw[1:-1]
                    # Decode für Display/DB
                    folder_name_decoded = mail_fetcher_mod.decode_imap_folder_name(folder_name_raw)
                    folders.append((folder_name_raw, folder_name_decoded))
            
            # Phase 13C Part 4: Delta-Sync wenn aktiviert
            user_use_delta = getattr(account.user, 'fetch_use_delta_sync', True)
            
            if user_use_delta and account.initial_sync_done:
                logger.info(f"📁 {len(folders)} Ordner, DELTA SYNC (nur neue Mails)")
            else:
                logger.info(f"📁 {len(folders)} Ordner, FULL SYNC (alle Mails)")
            
            # Phase 13C Part 4: User-steuerbare Limits
            user_mails_per_folder = getattr(account.user, 'fetch_mails_per_folder', 100)
            mails_per_folder = max(100, limit // len(folders)) if folders else limit
            mails_per_folder = min(mails_per_folder, user_mails_per_folder)
            
            # Phase 13C Part 4: Delta-Sync: Hole highest UID per folder aus DB
            session = object.__getattribute__(account, "_sa_instance_state").session
            folder_max_uids = {}
            
            if user_use_delta and account.initial_sync_done:
                # Query: SELECT imap_folder, MAX(imap_uid) FROM raw_emails WHERE account_id=X GROUP BY imap_folder
                from sqlalchemy import func
                results = (
                    session.query(
                        models.RawEmail.imap_folder,
                        func.max(func.cast(models.RawEmail.imap_uid, models.Integer)).label('max_uid')
                    )
                    .filter(
                        models.RawEmail.mail_account_id == account.id,
                        models.RawEmail.deleted_at.is_(None)
                    )
                    .group_by(models.RawEmail.imap_folder)
                    .all()
                )
                folder_max_uids = {folder: max_uid for folder, max_uid in results if max_uid}
                logger.info(f"  📊 Max UIDs: {folder_max_uids}")
            
            for folder_raw, folder_decoded in folders:
                try:
                    # Delta-Sync: Fetch nur Mails mit UID > last_known_uid
                    uid_range = None
                    if user_use_delta and folder_decoded in folder_max_uids:
                        last_uid = folder_max_uids[folder_decoded]
                        # UID-Range: (last_uid+1):* = Alle neuen Mails
                        uid_range = f"{last_uid + 1}:*"
                        logger.info(f"  🔄 {folder_decoded}: Delta ab UID {last_uid + 1}")
                    
                    # WICHTIG: IMAP SELECT braucht RAW UTF-7 Name!
                    folder_emails = fetcher.fetch_new_emails(
                        folder=folder_raw,  # RAW UTF-7 für IMAP Command
                        limit=mails_per_folder,
                        unseen_only=False,  # Immer alle Mails!
                        uid_range=uid_range  # Phase 13C Part 4: Delta-Filter
                    )
                    all_emails.extend(folder_emails)
                    logger.info(f"  ✓ {folder_decoded}: {len(folder_emails)} Mails")
                except Exception as e:
                    logger.warning(f"  ⚠️ Fehler in Ordner '{folder_decoded}': {e}")
                    continue
            
            logger.info(f"📧 Gesamt: {len(all_emails)} Mails aus {len(folders)} Ordnern")
            
            # Phase 13C Part 4: User-steuerbare Gesamt-Begrenzung
            user_max_total = getattr(account.user, 'fetch_max_total', 0)
            if user_max_total > 0:
                all_emails = all_emails[:user_max_total]
                logger.info(f"  ✂️ Auf {user_max_total} Mails begrenzt (user_prefs)")
            
            return all_emails
            
        finally:
            fetcher.disconnect()

    def _persist_raw_emails(
        self, session, user, account, raw_emails: list[Dict[str, Any]], master_key: str
    ) -> int:
        """Speichert RawEmails verschlüsselt in der Datenbank

        Phase 13C Part 3 FINAL: Korrekte IMAP-Sync-Logik
        - IMAP UID ist eindeutig pro (account, folder, uid)
        - INBOX/UID=123 ≠ Archiv/UID=123 (verschiedene IMAP-Objekte!)
        - Für jedes Mail: SELECT by (account_id, imap_folder, imap_uid)
          * Exists? → UPDATE (Flags können sich geändert haben)
          * Not Exists? → INSERT (neues Mail)
        - KEINE MESSAGE-ID-basierte Deduplizierung!
        
        Args:
            master_key: Master-Key für Verschlüsselung (Zero-Knowledge!)
        """
        saved = 0
        updated = 0
        
        # Phase 13C CRITICAL FIX: no_autoflush verhindert IntegrityError
        # Problem: SQLAlchemy flusht neue Objekte VOR der Query → Constraint-Fehler
        # Lösung: Autoflush deaktivieren während der Lookup-Phase
        with session.no_autoflush:
            for raw_email_data in raw_emails:
                # Phase 13C: Lookup per (account, folder, imap_uid) - das ist die IMAP-Identität!
                imap_folder = raw_email_data.get("imap_folder")
                imap_uid = raw_email_data.get("imap_uid")
                
                if not imap_folder or not imap_uid:
                    logger.warning(f"⚠️ Mail ohne folder/uid: {raw_email_data.get('subject', 'N/A')[:30]}")
                    continue
                
                existing = (
                    session.query(models.RawEmail)
                    .filter_by(
                        user_id=user.id,
                        mail_account_id=account.id,
                        imap_folder=imap_folder,
                        imap_uid=imap_uid,
                    )
                    .first()
                )
                
                if existing:
                    # UPDATE: Mail existiert bereits, aktualisiere Flags/Status
                    existing.imap_flags = raw_email_data.get("imap_flags")
                    existing.imap_is_seen = raw_email_data.get("imap_is_seen", False)
                    existing.imap_is_flagged = raw_email_data.get("imap_is_flagged", False)
                    existing.imap_is_answered = raw_email_data.get("imap_is_answered", False)
                    existing.imap_last_seen_at = datetime.now(UTC)
                    updated += 1
                    logger.debug(f"🔄 UPDATE: {imap_folder}/{imap_uid}")
                    continue
                
                # INSERT: Neues Mail, verschlüssele und speichere

                encrypted_sender = encryption.EmailDataManager.encrypt_email_sender(
                    raw_email_data["sender"], master_key
                )
                encrypted_subject = encryption.EmailDataManager.encrypt_email_subject(
                    raw_email_data["subject"], master_key
                )
                encrypted_body = encryption.EmailDataManager.encrypt_email_body(
                    raw_email_data["body"], master_key
                )

                encrypted_in_reply_to = None
                if raw_email_data.get("in_reply_to"):
                    encrypted_in_reply_to = encryption.EncryptionManager.encrypt_data(
                        raw_email_data["in_reply_to"], master_key
                    )

                encrypted_to = None
                if raw_email_data.get("to"):
                    encrypted_to = encryption.EncryptionManager.encrypt_data(
                        raw_email_data["to"], master_key
                    )

                encrypted_cc = None
                if raw_email_data.get("cc"):
                    encrypted_cc = encryption.EncryptionManager.encrypt_data(
                        raw_email_data["cc"], master_key
                    )

                encrypted_bcc = None
                if raw_email_data.get("bcc"):
                    encrypted_bcc = encryption.EncryptionManager.encrypt_data(
                        raw_email_data["bcc"], master_key
                    )

                encrypted_reply_to = None
                if raw_email_data.get("reply_to"):
                    encrypted_reply_to = encryption.EncryptionManager.encrypt_data(
                        raw_email_data["reply_to"], master_key
                    )

                encrypted_references = None
                if raw_email_data.get("references"):
                    encrypted_references = encryption.EncryptionManager.encrypt_data(
                        raw_email_data["references"], master_key
                    )

                raw_email = models.RawEmail(
                    user_id=user.id,
                    mail_account_id=account.id,
                    uid=raw_email_data["uid"],
                    encrypted_sender=encrypted_sender,
                    encrypted_subject=encrypted_subject,
                    encrypted_body=encrypted_body,
                    received_at=raw_email_data["received_at"],
                    imap_uid=raw_email_data.get("imap_uid"),
                    imap_folder=raw_email_data.get("imap_folder"),
                    imap_flags=raw_email_data.get("imap_flags"),
                    message_id=raw_email_data.get("message_id"),
                    encrypted_in_reply_to=encrypted_in_reply_to,
                    parent_uid=raw_email_data.get("parent_uid"),
                    thread_id=raw_email_data.get("thread_id"),
                    imap_is_seen=raw_email_data.get("imap_is_seen"),
                    imap_is_answered=raw_email_data.get("imap_is_answered"),
                    imap_is_flagged=raw_email_data.get("imap_is_flagged"),
                    imap_is_deleted=raw_email_data.get("imap_is_deleted"),
                    imap_is_draft=raw_email_data.get("imap_is_draft"),
                    encrypted_to=encrypted_to,
                    encrypted_cc=encrypted_cc,
                    encrypted_bcc=encrypted_bcc,
                    encrypted_reply_to=encrypted_reply_to,
                    message_size=raw_email_data.get("message_size"),
                    encrypted_references=encrypted_references,
                    content_type=raw_email_data.get("content_type"),
                    charset=raw_email_data.get("charset"),
                    has_attachments=raw_email_data.get("has_attachments"),
                )
                session.add(raw_email)
                saved += 1

        if saved or updated:
            session.commit()
            if updated > 0:
                logger.info(f"💾 {saved} neue Mails, {updated} aktualisiert (Flags/Status)")
            else:
                logger.info(f"💾 {saved} neue Mails gespeichert")
        else:
            session.flush()

        return saved
