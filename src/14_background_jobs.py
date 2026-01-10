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
auth = importlib.import_module(".07_auth", "src")
# Phase 17: Semantic Search
from src.semantic_search import generate_embedding_for_email

logger = logging.getLogger(__name__)

# Layer 4 Security: Resource Exhaustion Prevention
MAX_EMAILS_PER_REQUEST = 1000


@dataclass
class FetchJob:
    """
    Job für Mail-Abruf mit AI-Verarbeitung (Phase 2: ServiceToken Pattern).
    
    Security: service_token_id statt plaintext master_key verhindert lange RAM-Speicherung.
    Worker lädt DEK erst bei Startup, nutzt sie, und löscht sie explizit.
    """
    job_id: str
    user_id: int
    account_id: int
    service_token_id: int
    provider: str
    model: str
    max_mails: int = 50
    sanitize_level: int = 2
    meta: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 2
    retry_delays: list[int] = field(default_factory=lambda: [60, 300])


@dataclass
class BatchReprocessJob:
    """
    Job für Batch-Reprocessing aller Emails (Embedding regeneration).
    Phase 2: ServiceToken Pattern für sichere DEK-Verwaltung.
    """
    job_id: str
    user_id: int
    service_token_id: int
    provider: str
    model: str
    meta: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 2
    retry_delays: list[int] = field(default_factory=lambda: [60, 300])


class BackgroundJobQueue:
    """Kleiner in-memory Job-Queue mit einem Worker-Thread."""

    # Security: Limit queue size to prevent memory exhaustion
    MAX_QUEUE_SIZE = 50

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.queue: Queue = Queue(maxsize=self.MAX_QUEUE_SIZE)  # Generic queue for all job types
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
        db_session=None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Phase 2: Enqueue Mail-Fetch Job mit ServiceToken Pattern.
        
        Args:
            user_id: User-ID
            account_id: Mail-Account-ID
            master_key: DEK aus Session (wird hier verschlüsselt in ServiceToken gespeichert)
            provider: AI-Provider
            model: AI-Model
            max_mails: Max Emails pro Fetch
            sanitize_level: Sanitization-Level
            db_session: SQLAlchemy Session für ServiceToken-Erstellung (optional, wird aus Queue erstellt)
            meta: Additional metadata
            
        Returns:
            str: Job-ID
        """
        if not master_key:
            raise ValueError("master_key ist erforderlich")
        
        if max_mails > MAX_EMAILS_PER_REQUEST:
            raise ValueError(
                f"max_mails darf maximal {MAX_EMAILS_PER_REQUEST} sein (gegeben: {max_mails})"
            )
        
        session = db_session if db_session else self._SessionFactory()
        try:
            token, service_token = auth.ServiceTokenManager.create_token(
                user_id=user_id,
                master_key=master_key,
                session=session,
                days=7
            )
            service_token_id = service_token.id
            logger.info(f"✅ ServiceToken {service_token_id} für Fetch-Job erstellt (expires: {service_token.expires_at})")
        finally:
            if not db_session:
                session.close()

        job_id = uuid.uuid4().hex
        job = FetchJob(
            job_id=job_id,
            user_id=user_id,
            account_id=account_id,
            service_token_id=service_token_id,
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
                "service_token_id": service_token_id,
            },
        )
        self.ensure_worker()
        logger.info(
            "📥 Job %s eingereiht (User %s, Account %s, Token %s)", 
            job_id, user_id, account_id, service_token_id
        )
        return job_id

    def enqueue_batch_reprocess_job(
        self,
        *,
        user_id: int,
        master_key: str,
        provider: str,
        model: str,
        db_session=None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Enqueue Batch-Reprocess Job (alle Emails neu embedden).
        Phase 2: ServiceToken Pattern für sichere DEK-Verwaltung.
        """
        if not master_key:
            raise ValueError("master_key ist erforderlich")

        session = db_session if db_session else self._SessionFactory()
        try:
            token, service_token = auth.ServiceTokenManager.create_token(
                user_id=user_id,
                master_key=master_key,
                session=session,
                days=7
            )
            service_token_id = service_token.id
            logger.info(f"✅ ServiceToken {service_token_id} für Batch-Reprocess Job erstellt")
        finally:
            if not db_session:
                session.close()

        job_id = uuid.uuid4().hex
        job = BatchReprocessJob(
            job_id=job_id,
            user_id=user_id,
            service_token_id=service_token_id,
            provider=provider,
            model=model,
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
                "provider": provider,
                "model": model,
                "job_type": "batch_reprocess",
                "service_token_id": service_token_id,
            },
        )
        self.ensure_worker()
        logger.info(
            "🔄 Batch-Reprocess Job %s eingereiht (User %s, Token %s)", job_id, user_id, service_token_id
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
                
                # Route zu spezifischer Execute-Methode basierend auf Job-Typ
                if isinstance(job, BatchReprocessJob):
                    self._execute_batch_reprocess_job(job)
                elif isinstance(job, FetchJob):
                    self._execute_fetch_job(job)
                else:
                    logger.error(f"Unknown job type: {type(job)}")
                    
            except Exception:
                logger.exception("Unerwarteter Fehler im Worker")
            finally:
                self.queue.task_done()

    def _is_transient_error(self, exc: Exception) -> bool:
        """P2-002: Erkennt ob Fehler transient ist (retry lohnt sich)
        
        Transient Errors:
        - Netzwerk-Timeouts
        - IMAP-Server temporär nicht erreichbar
        - Datenbank-Locks
        - API-Rate-Limits
        
        Permanent Errors:
        - Falsche Credentials
        - ValueError (falsche Parameter)
        - Permission Denied
        """
        error_str = str(exc).lower()
        error_type = type(exc).__name__
        
        # Transient: Netzwerk-Probleme
        transient_keywords = [
            'timeout', 'timed out', 'connection', 'network',
            'temporary', 'unavailable', 'try again',
            'rate limit', 'too many requests', 'socket',
            'ssl', 'certificate', 'refused'
        ]
        
        if any(keyword in error_str for keyword in transient_keywords):
            return True
        
        # Permanent: Auth/Permission
        permanent_keywords = [
            'authentication', 'credentials', 'password',
            'permission denied', 'unauthorized', 'forbidden',
            'invalid token', 'access denied'
        ]
        
        if any(keyword in error_str for keyword in permanent_keywords):
            return False
        
        # Permanent: Programming Errors
        if error_type in ['ValueError', 'TypeError', 'AttributeError', 'KeyError']:
            return False
        
        # Default: Bei Unsicherheit retry versuchen
        return True

    def _get_dek_from_service_token(self, job, session) -> str:
        """
        Phase 2: Lädt und verifiziert ServiceToken, gibt DEK zurück.
        
        Sicherheit: 
        - Token wird auf Gültigkeit überprüft
        - last_verified_at wird aktualisiert (Audit-Trail)
        - DEK wird aus DB geladen, nicht aus Job-Dataclass
        
        Args:
            job: FetchJob oder BatchReprocessJob mit service_token_id
            session: DB-Session
            
        Returns:
            str: DEK (Base64-encoded)
            
        Raises:
            ValueError: Token nicht gefunden/abgelaufen
        """
        service_token = session.query(models.ServiceToken).filter_by(
            id=job.service_token_id
        ).first()
        
        if not service_token:
            raise ValueError(f"ServiceToken {job.service_token_id} nicht gefunden")
        
        if not service_token.is_valid():
            raise ValueError(f"ServiceToken {job.service_token_id} abgelaufen (expires: {service_token.expires_at})")
        
        dek = service_token.encrypted_dek
        service_token.mark_verified()
        session.commit()
        
        logger.info(f"✅ DEK aus ServiceToken {job.service_token_id} geladen")
        return dek

    def _execute_fetch_job(self, job: FetchJob) -> None:
        """
        Execute Mail Fetch Job mit Phase 2 ServiceToken Pattern.
        
        DEK wird hier geladen, in RAM genutzt, dann explizit bereinigt.
        """
        session = self._SessionFactory()
        saved = 0
        processed = 0
        master_key = None
        
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

            master_key = self._get_dek_from_service_token(job, session)
            if not master_key:
                raise ValueError("DEK konnte nicht aus ServiceToken geladen werden")

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

            # ═══════════════════════════════════════════════════════════════
            # PHASE G.2: Auto-Action Rules nach Email-Fetch anwenden
            # ═══════════════════════════════════════════════════════════════
            try:
                from src.auto_rules_engine import AutoRulesEngine
                
                rules_engine = AutoRulesEngine(user.id, master_key, session)
                # Verarbeite alle neuen Mails der letzten 60 Minuten
                rules_stats = rules_engine.process_new_emails(
                    since_minutes=60,
                    limit=500
                )
                
                if rules_stats["rules_triggered"] > 0:
                    logger.info(
                        f"🤖 Auto-Rules: {rules_stats['rules_triggered']} Regeln auf "
                        f"{rules_stats['emails_checked']} E-Mails angewendet"
                    )
            except Exception as rules_err:
                # Auto-Rules sind optional - Job sollte nicht scheitern
                logger.warning(f"⚠️ Auto-Rules fehlgeschlagen: {rules_err}")
            # ═══════════════════════════════════════════════════════════════

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
            
            # P2-002: Retry-Logik mit Exponential Backoff
            should_retry = (
                job.retry_count < job.max_retries and
                self._is_transient_error(exc)
            )
            
            if should_retry:
                job.retry_count += 1
                retry_delay = job.retry_delays[min(job.retry_count - 1, len(job.retry_delays) - 1)]
                
                logger.warning(
                    f"⏰ Job {job.job_id} wird in {retry_delay}s erneut versucht "
                    f"(Versuch {job.retry_count}/{job.max_retries})"
                )
                
                self._update_status(
                    job.job_id,
                    {
                        "state": "retrying",
                        "message": f"Fehler - Retry in {retry_delay}s (Versuch {job.retry_count}/{job.max_retries})",
                        "retry_count": job.retry_count,
                        "next_retry": datetime.now(UTC).timestamp() + retry_delay,
                    },
                )
                
                # Schedule retry nach delay
                threading.Timer(retry_delay, lambda: self.queue.put(job)).start()
            else:
                # Kein Retry mehr - Job final fehlgeschlagen
                error_msg = "Verarbeitung fehlgeschlagen (siehe Server-Logs)"
                if job.retry_count >= job.max_retries:
                    error_msg += f" - {job.max_retries} Versuche fehlgeschlagen"
                
                self._update_status(
                    job.job_id,
                    {
                        "state": "error",
                        "message": error_msg,
                        "retry_count": job.retry_count,
                    },
                )
        finally:
            # 🔒 Security: Sichere Master-Key Bereinigung aus RAM
            if 'master_key' in locals() and master_key is not None:
                import gc
                master_key = b'\x00' * len(master_key) if isinstance(master_key, bytes) else '\x00' * len(master_key)
                del master_key
                gc.collect()
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
            
            # 1. Liste alle Ordner (IMAPClient: list_folders() gibt direkt Liste zurück!)
            mailboxes = fetcher.connection.list_folders()
            
            # mailboxes ist Liste von (flags, delimiter, name) Tuples
            # Format: [(flags, b'/', 'INBOX'), (flags, b'/', 'Sent'), ...]
            folders = []
            for flags, delimiter, folder_name in mailboxes:
                # IMAPClient gibt Namen schon decoded zurück!
                folders.append(folder_name)
            # mailboxes ist Liste von (flags, delimiter, name) Tuples
            # Format: [(flags, b'/', 'INBOX'), (flags, b'/', 'Sent'), ...]
            folders = []
            for flags, delimiter, folder_name in mailboxes:
                # IMAPClient gibt Namen schon decoded zurück!
                folders.append(folder_name)
            
            # Phase 13C Part 4: User Fetch-Einstellungen laden (global)
            import json
            from datetime import datetime
            
            user_use_delta = getattr(account.user, 'fetch_use_delta_sync', True)
            user_mails_per_folder = getattr(account.user, 'fetch_mails_per_folder', 100)
            
            # Phase 13C Part 6: Account-spezifische Filter
            account_since_date = getattr(account, 'fetch_since_date', None)
            account_unseen_only = getattr(account, 'fetch_unseen_only', False)
            account_include_folders_json = getattr(account, 'fetch_include_folders', None)
            account_exclude_folders_json = getattr(account, 'fetch_exclude_folders', None)
            
            # Parse JSON-Listen
            include_folders = []
            exclude_folders = []
            try:
                if account_include_folders_json:
                    include_folders = json.loads(account_include_folders_json)
                if account_exclude_folders_json:
                    exclude_folders = json.loads(account_exclude_folders_json)
            except json.JSONDecodeError:
                logger.warning("Ungültiges JSON in Ordner-Filter, ignoriere")
            
            # Log Fetch-Konfiguration
            filters_active = []
            if account_since_date:
                filters_active.append(f"SINCE {account_since_date}")
            if account_unseen_only:
                filters_active.append("UNSEEN")
            if include_folders:
                filters_active.append(f"Include: {', '.join(include_folders[:3])}{'...' if len(include_folders) > 3 else ''}")
            if exclude_folders:
                filters_active.append(f"Exclude: {', '.join(exclude_folders[:3])}{'...' if len(exclude_folders) > 3 else ''}")
            
            filter_str = f" | {', '.join(filters_active)}" if filters_active else ""
            
            if user_use_delta and account.initial_sync_done:
                logger.info(f"📁 {len(folders)} Ordner, DELTA SYNC{filter_str}")
            else:
                logger.info(f"📁 {len(folders)} Ordner, FULL SYNC{filter_str}")
            
            # Phase 13C Part 4: User-steuerbare Limits
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
            
            # Part 5: Ordner filtern
            filtered_folders = []
            for folder_name in folders:
                # Ordner-Filter anwenden
                if include_folders and folder_name not in include_folders:
                    logger.debug(f"  ⏭️  {folder_name}: Nicht in Include-Liste")
                    continue
                
                if exclude_folders and folder_name in exclude_folders:
                    logger.debug(f"  ⏭️  {folder_name}: In Exclude-Liste")
                    continue
                
                filtered_folders.append(folder_name)
            
            logger.info(f"  📂 {len(filtered_folders)}/{len(folders)} Ordner nach Filter")
            
            for folder_name in filtered_folders:
                try:
                    # Delta-Sync: Fetch nur Mails mit UID > last_known_uid
                    uid_range = None
                    if user_use_delta and folder_name in folder_max_uids:
                        last_uid = folder_max_uids[folder_name]
                        # UID-Range: (last_uid+1):* = Alle neuen Mails
                        uid_range = f"{last_uid + 1}:*"
                        logger.info(f"  🔄 {folder_name}: Delta ab UID {last_uid + 1}")
                    
                    # Phase 13C Part 6: SINCE-Datum und UNSEEN-Filter vom Account
                    # Filter werden IMMER angewendet, nicht nur beim Initial-Sync!
                    fetch_since = None
                    fetch_unseen = account_unseen_only
                    
                    # SINCE macht nur Sinn wenn KEIN Delta-Sync (uid_range) aktiv ist
                    # Bei Delta haben wir schon "nur neue" durch UID-Range
                    if not uid_range and account_since_date:
                        fetch_since = datetime.combine(account_since_date, datetime.min.time())
                    
                    # IMAPClient braucht einfach den folder_name!
                    folder_emails = fetcher.fetch_new_emails(
                        folder=folder_name,  # IMAPClient handled Namen automatisch
                        limit=mails_per_folder,
                        unseen_only=fetch_unseen,  # UNSEEN Filter (immer aktiv)
                        uid_range=uid_range,  # Phase 13C Part 4: Delta-Filter
                        since=fetch_since,  # SINCE Filter (außer bei Delta)
                        account_id=account.id,  # Phase 14b: UIDVALIDITY-Check
                        session=session  # Phase 14b: DB-Session für UIDVALIDITY
                    )
                    all_emails.extend(folder_emails)
                    logger.info(f"  ✓ {folder_name}: {len(folder_emails)} Mails")
                except Exception as e:
                    logger.warning(f"  ⚠️ Fehler in Ordner '{folder_name}': {e}")
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

        Phase 14e: RFC-konform Unique Key (account, folder, uidvalidity, uid)
        - KEINE Deduplizierungs-Checks mehr!
        - Der Unique Constraint uq_raw_emails_rfc_unique verhindert automatisch Duplikate
        - Für jedes Mail: INSERT mit (folder, uidvalidity, uid)
          * Success: Neues Mail gespeichert
          * IntegrityError: Mail existiert bereits (skip)
        - UPDATE nur bei bestehenden Mails (Flags-Änderungen)
        
        Phase 17: Semantic Search - Embedding-Generierung
        - Embedding wird VOR der Verschlüsselung generiert (Klartext verfügbar!)
        - Embeddings sind NICHT verschlüsselt (nicht reversibel)
        
        Args:
            master_key: Master-Key für Verschlüsselung (Zero-Knowledge!)
        """
        saved = 0
        skipped = 0
        updated = 0
        
        # Phase 17: AI-Client für Embeddings (User Settings EMBEDDING Model!)
        embedding_ai_client = None
        try:
            # WICHTIG: Nutze EMBEDDING Settings (nicht BASE!)
            provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
            model_embedding = user.preferred_embedding_model or "all-minilm:22m"
            resolved_model = ai_client.resolve_model(provider_embedding, model_embedding)
            
            embedding_ai_client = ai_client.build_client(provider_embedding, model=resolved_model)
            logger.debug(f"✅ Embedding AI-Client ({resolved_model}) initialisiert")
        except Exception as e:
            logger.warning(f"⚠️ Embedding AI-Client nicht verfügbar: {e}")
        
        for raw_email_data in raw_emails:
            # Phase 14e: RFC-konform Unique Key
            imap_folder = raw_email_data.get("imap_folder")
            imap_uid = raw_email_data.get("imap_uid")
            imap_uidvalidity = raw_email_data.get("imap_uidvalidity")
            
            if not imap_folder or not imap_uid or not imap_uidvalidity:
                logger.warning(
                    f"⚠️ Mail ohne folder/uid/uidvalidity: "
                    f"{raw_email_data.get('subject', 'N/A')[:30]}"
                )
                continue
            
            # Phase 14e: Optional - Check if exists for UPDATE (Flags)
            # Nur wenn wir Flags updaten wollen, sonst einfach INSERT versuchen
            existing = (
                session.query(models.RawEmail)
                .filter_by(
                    user_id=user.id,
                    mail_account_id=account.id,
                    imap_folder=imap_folder,
                    imap_uidvalidity=imap_uidvalidity,
                    imap_uid=imap_uid,
                )
                .filter(models.RawEmail.deleted_at.is_(None))
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
            
            # ════════════════════════════════════════════════════════════════
            # PHASE 17: KLARTEXT IST HIER NOCH VERFÜGBAR!
            # ════════════════════════════════════════════════════════════════
            subject_plain = raw_email_data.get("subject", "")
            body_plain = raw_email_data.get("body", "")
            
            # ════════════════════════════════════════════════════════════════
            # NEU: Embedding generieren (VOR Verschlüsselung!)
            # ════════════════════════════════════════════════════════════════
            embedding_bytes = None
            embedding_model = None
            embedding_generated_at = None
            
            if embedding_ai_client and (subject_plain or body_plain):
                try:
                    embedding_bytes, embedding_model, embedding_generated_at = \
                        generate_embedding_for_email(
                            subject=subject_plain,
                            body=body_plain,
                            ai_client=embedding_ai_client,
                            model_name=resolved_model  # Übergebe explizit das Model
                        )
                    if embedding_bytes:
                        logger.debug(f"🔍 Embedding generiert für: {subject_plain[:50]}...")
                except Exception as e:
                    logger.warning(f"⚠️ Embedding-Fehler: {e}")
            

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
                encrypted_sender=encrypted_sender,
                encrypted_subject=encrypted_subject,
                encrypted_body=encrypted_body,
                received_at=raw_email_data["received_at"],
                imap_uid=raw_email_data.get("imap_uid"),
                imap_folder=raw_email_data.get("imap_folder"),
                imap_uidvalidity=raw_email_data.get("imap_uidvalidity"),  # Phase 14e
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
                # Phase 17: Semantic Search - Embeddings (NICHT verschlüsselt!)
                email_embedding=embedding_bytes,
                embedding_model=embedding_model,
                embedding_generated_at=embedding_generated_at,
            )
            try:
                session.add(raw_email)
                session.flush()  # Force insert to trigger IntegrityError if duplicate
                saved += 1
            except Exception as e:
                session.rollback()
                # Phase 14e: IntegrityError = Duplikat (Unique Constraint)
                if "UNIQUE constraint failed" in str(e) or "IntegrityError" in str(type(e).__name__):
                    skipped += 1
                    logger.debug(
                        f"⏭️  Duplikat übersprungen: {imap_folder}/{imap_uid} "
                        f"(UIDVALIDITY={imap_uidvalidity})"
                    )
                else:
                    logger.error(f"❌ Fehler beim Speichern: {e}")
                    raise

        if saved or updated or skipped:
            session.commit()
            if updated > 0 or skipped > 0:
                logger.info(
                    f"💾 {saved} neue Mails, {updated} aktualisiert, "
                    f"{skipped} Duplikate übersprungen"
                )
            else:
                logger.info(f"💾 {saved} neue Mails gespeichert")
        else:
            session.flush()

        return saved

    def _execute_batch_reprocess_job(self, job: BatchReprocessJob) -> None:
        """
        Execute Batch-Reprocess Job (regenerate embeddings for all emails).
        Phase 2: ServiceToken Pattern für sichere DEK-Verwaltung.
        """
        session = self._SessionFactory()
        processed = 0
        failed = 0
        master_key = None
        
        try:
            user = session.query(models.User).filter_by(id=job.user_id).first()
            if not user:
                raise ValueError("User nicht gefunden")

            master_key = self._get_dek_from_service_token(job, session)
            if not master_key:
                raise ValueError("DEK konnte nicht aus ServiceToken geladen werden")

            # Hole alle RawEmails des Users
            raw_emails = (
                session.query(models.RawEmail)
                .filter(
                    models.RawEmail.user_id == user.id,
                    models.RawEmail.deleted_at == None
                )
                .all()
            )
            
            if not raw_emails:
                self._update_status(
                    job.job_id,
                    {
                        "state": "done",
                        "processed": 0,
                        "failed": 0,
                        "total_emails": 0,
                        "message": "Keine Emails vorhanden"
                    },
                )
                return
            
            total = len(raw_emails)
            logger.info(f"🔄 Batch-Reprocess: {total} Emails mit {job.model}")
            
            # Build AI Client
            resolved_model = ai_client.resolve_model(job.provider, job.model)
            embedding_client = ai_client.build_client(job.provider, model=resolved_model)
            
            # Update initial status
            self._update_status(
                job.job_id,
                {
                    "total_emails": total,
                    "current_email_index": 0,
                },
            )
            
            # Process each email
            for idx, raw_email in enumerate(raw_emails, start=1):
                try:
                    # Entschlüsseln
                    decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                        raw_email.encrypted_subject or "", master_key
                    )
                    decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                        raw_email.encrypted_body or "", master_key
                    )
                    
                    # Progress-Update
                    self._update_status(
                        job.job_id,
                        {
                            "current_email_index": idx,
                            "current_subject": decrypted_subject[:50] if decrypted_subject else "Kein Betreff",
                        },
                    )
                    
                    logger.info(f"🔄 [{idx}/{total}] Verarbeite: {decrypted_subject[:50] if decrypted_subject else 'Kein Betreff'}...")
                    
                    # Embedding generieren
                    embedding_bytes, model_name, timestamp = generate_embedding_for_email(
                        subject=decrypted_subject,
                        body=decrypted_body,
                        ai_client=embedding_client,
                        model_name=resolved_model  # Übergebe explizit das Model
                    )
                    
                    if embedding_bytes:
                        old_embedding = raw_email.email_embedding
                        raw_email.email_embedding = embedding_bytes
                        raw_email.embedding_model = model_name or resolved_model
                        raw_email.embedding_generated_at = timestamp
                        
                        # Commit nach jedem Email für bessere Fehlertoleranz
                        session.flush()
                        
                        processed += 1
                        logger.info(f"✅ [{idx}/{total}] Email {raw_email.id} embedded ({len(embedding_bytes)} bytes, Model: {model_name or resolved_model})")
                    else:
                        failed += 1
                        logger.warning(f"⚠️  [{idx}/{total}] Embedding failed for email {raw_email.id}")
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"❌ [{idx}/{total}] Failed to reprocess email {raw_email.id}: {e}")
            
            session.commit()
            
            # Tag-Embedding-Cache leeren nach Batch-Reprocess!
            # Wichtig: Tags müssen mit neuem Model re-embedded werden
            try:
                from src.services.tag_manager import TagEmbeddingCache
                TagEmbeddingCache._cache.clear()
                TagEmbeddingCache._ai_client_cache.clear()
                logger.info("🗑️  Tag-Embedding-Cache geleert (Tags werden mit neuem Model re-embedded)")
            except Exception as cache_err:
                logger.warning(f"⚠️  Konnte Tag-Cache nicht leeren: {cache_err}")
            
            self._update_status(
                job.job_id,
                {
                    "state": "done",
                    "processed": processed,
                    "failed": failed,
                    "total_emails": total,
                    "model": resolved_model,
                },
            )
            logger.info(
                "✅ Batch-Reprocess Job %s abgeschlossen (processed=%s, failed=%s)",
                job.job_id,
                processed,
                failed,
            )
            
        except Exception as exc:
            session.rollback()
            logger.error("❌ Batch-Reprocess Job %s fehlgeschlagen: %s", job.job_id, exc, exc_info=True)
            
            # P2-002: Retry-Logik auch für Batch-Jobs
            should_retry = (
                job.retry_count < job.max_retries and
                self._is_transient_error(exc)
            )
            
            if should_retry:
                job.retry_count += 1
                retry_delay = job.retry_delays[min(job.retry_count - 1, len(job.retry_delays) - 1)]
                
                logger.warning(
                    f"⏰ Batch-Job {job.job_id} wird in {retry_delay}s erneut versucht "
                    f"(Versuch {job.retry_count}/{job.max_retries})"
                )
                
                self._update_status(
                    job.job_id,
                    {
                        "state": "retrying",
                        "message": f"Fehler - Retry in {retry_delay}s (Versuch {job.retry_count}/{job.max_retries})",
                        "retry_count": job.retry_count,
                        "next_retry": datetime.now(UTC).timestamp() + retry_delay,
                    },
                )
                
                # Schedule retry
                threading.Timer(retry_delay, lambda: self.queue.put(job)).start()
            else:
                # Kein Retry mehr
                error_msg = f"Batch-Reprocess fehlgeschlagen: {str(exc)}"
                if job.retry_count >= job.max_retries:
                    error_msg += f" - {job.max_retries} Versuche fehlgeschlagen"
                
                self._update_status(
                    job.job_id,
                    {
                        "state": "error",
                        "message": error_msg,
                        "retry_count": job.retry_count,
                    },
                )
        finally:
            # 🔒 Security: Sichere Master-Key Bereinigung aus RAM
            if 'master_key' in locals() and master_key is not None:
                import gc
                master_key = b'\x00' * len(master_key) if isinstance(master_key, bytes) else '\x00' * len(master_key)
                del master_key
                gc.collect()
            session.close()
