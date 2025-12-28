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
    # Security: master_key NICHT hier speichern - Memory-Leak-Risiko!
    # Wird stattdessen zur Laufzeit aus Session des Users geholt
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
        provider: str,
        model: str,
        max_mails: int,
        sanitize_level: int,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        if max_mails > MAX_EMAILS_PER_REQUEST:
            raise ValueError(
                f"max_mails darf maximal {MAX_EMAILS_PER_REQUEST} sein (gegeben: {max_mails})"
            )

        job_id = uuid.uuid4().hex
        job = FetchJob(
            job_id=job_id,
            user_id=user_id,
            account_id=account_id,
            provider=provider,
            model=model,
            max_mails=max_mails,
            sanitize_level=sanitize_level,
            meta=meta or {},
        )
        try:
            self.queue.put(job, block=False)  # Don't block if queue is full
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
            except Exception:  # pragma: no cover - defensive
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

            # Security: Lade master_key aus Service-Token statt aus Job-Memory
            # Job speichert keine Secrets im RAM → Memory-Dump-Safe
            service_token = (
                session.query(models.ServiceToken)
                .filter_by(user_id=job.user_id)
                .filter(models.ServiceToken.expires_at > datetime.now(UTC))
                .first()
            )
            if not service_token:
                raise ValueError(
                    "Service-Token nicht gefunden oder abgelaufen - Background-Jobs benötigen gültigen Token"
                )

            master_key = service_token.master_key
            if not master_key:
                raise ValueError("Master-Key fehlt im Service-Token")

            raw_emails = self._fetch_raw_emails(account, master_key, job.max_mails)
            if raw_emails:
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
        except Exception as exc:  # pragma: no cover - heavy IO
            session.rollback()
            logger.error("❌ Job %s fehlgeschlagen: %s", job.job_id, exc, exc_info=True)
            self._update_status(
                job.job_id,
                {
                    "state": "error",
                    "message": "Verarbeitung fehlgeschlagen (siehe Server-Logs)",  # Layer 4: Exception Sanitization
                },
            )
        finally:
            session.close()

    def _fetch_raw_emails(
        self, account, master_key: str, limit: int
    ) -> list[Dict[str, Any]]:
        if account.oauth_provider == "google":
            decrypted_token = encryption.CredentialManager.decrypt_imap_password(
                account.encrypted_oauth_token, master_key
            )
            fetcher = google_oauth.GoogleMailFetcher(access_token=decrypted_token)
            return fetcher.fetch_new_emails(limit=limit)

        if not account.encrypted_imap_password:
            raise ValueError("Kein IMAP-Passwort gespeichert")

        # Zero-Knowledge: Entschlüssele alle IMAP-Credentials
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
            return fetcher.fetch_new_emails(limit=limit)
        finally:
            fetcher.disconnect()

    def _persist_raw_emails(
        self, session, user, account, raw_emails: list[Dict[str, Any]], master_key: str
    ) -> int:
        """Speichert RawEmails verschlüsselt in der Datenbank

        Args:
            master_key: Master-Key für Verschlüsselung (Zero-Knowledge!)
        """
        saved = 0
        for raw_email_data in raw_emails:
            existing = (
                session.query(models.RawEmail)
                .filter_by(
                    user_id=user.id,
                    mail_account_id=account.id,
                    uid=raw_email_data["uid"],
                )
                .first()
            )
            if existing:
                continue

            # Zero-Knowledge: Verschlüssele E-Mail-Inhalte
            encrypted_sender = encryption.EmailDataManager.encrypt_email_sender(
                raw_email_data["sender"], master_key
            )
            encrypted_subject = encryption.EmailDataManager.encrypt_email_subject(
                raw_email_data["subject"], master_key
            )
            encrypted_body = encryption.EmailDataManager.encrypt_email_body(
                raw_email_data["body"], master_key
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
            )
            session.add(raw_email)
            saved += 1

        if saved:
            session.commit()
        else:
            session.flush()

        return saved
