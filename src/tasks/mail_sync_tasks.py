# src/tasks/mail_sync_tasks.py
"""
Mail Sync Tasks für Celery - 1:1 Portierung aus Legacy 14_background_jobs.py

WICHTIG: Dieser Code ist eine exakte Kopie der Legacy-Logik!
Änderungen nur wenn ABSOLUT notwendig (z.B. self.update_state statt self._update_status).

Phase 2 Security: ServiceToken Pattern
- master_key wird NICHT mehr als Parameter übergeben (wäre Plaintext in Redis!)
- Stattdessen: service_token_id → Task lädt DEK aus DB
"""

import logging
import importlib
import json
import gc
from datetime import datetime, UTC
from typing import Dict, Any, Callable, Optional
from sqlalchemy import text as sa_text  # 🆕 Für raw SQL queries

from src.celery_app import celery_app
from src.helpers.database import get_session, get_user, get_mail_account

# Phase 17: Semantic Search
from src.semantic_search import generate_embedding_for_email

logger = logging.getLogger(__name__)

# Layer 4 Security: Resource Exhaustion Prevention
MAX_EMAILS_PER_REQUEST = 1000


def _get_dek_from_service_token(service_token_id: int, session) -> str:
    """
    Phase 2 Security: Lädt und verifiziert ServiceToken, gibt DEK zurück.
    
    1:1 KOPIE aus Legacy 14_background_jobs.py
    
    Sicherheit: 
    - Token wird auf Gültigkeit überprüft
    - last_verified_at wird aktualisiert (Audit-Trail)
    - DEK wird aus DB geladen, nicht aus Task-Parameter
    
    Args:
        service_token_id: ID des ServiceTokens
        session: DB-Session
        
    Returns:
        str: DEK (Base64-encoded)
        
    Raises:
        ValueError: Token nicht gefunden/abgelaufen
    """
    models = importlib.import_module(".02_models", "src")
    
    service_token = session.query(models.ServiceToken).filter_by(
        id=service_token_id
    ).first()
    
    if not service_token:
        raise ValueError(f"ServiceToken {service_token_id} nicht gefunden")
    
    if not service_token.is_valid():
        raise ValueError(f"ServiceToken {service_token_id} abgelaufen (expires: {service_token.expires_at})")
    
    dek = service_token.encrypted_dek
    service_token.mark_verified()
    session.commit()
    
    logger.info(f"✅ DEK aus ServiceToken {service_token_id} geladen")
    return dek


def _is_transient_error(exc: Exception) -> bool:
    """
    P2-002: Erkennt ob Fehler transient ist (retry lohnt sich)
    
    1:1 KOPIE aus Legacy 14_background_jobs.py
    
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


def _fetch_raw_emails(
    account, master_key: str, limit: int, session, 
    progress_callback: Optional[Callable] = None
) -> list[Dict[str, Any]]:
    """
    Fetcht Mails aus ALLEN Ordnern (Phase 13C: Multi-Folder FULL SYNC)
    
    1:1 KOPIE aus Legacy 14_background_jobs.py
    
    Phase 13C Part 3: KEIN UNSEEN-Filter mehr!
    Problem: UNSEEN-Filter führte zu unvollständigem Sync (nur 2/20 Mails)
    Lösung: Server = Single Source of Truth → ALLE Mails fetchen
    
    Phase 13C Part 4: Delta-Sync Option
    - Wenn user.fetch_use_delta_sync=True: Nur neue Mails seit letztem Sync
    - Sonst: FULL SYNC (alle Mails)
    """
    encryption = importlib.import_module(".08_encryption", "src")
    mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
    google_oauth = importlib.import_module(".10_google_oauth", "src")
    models = importlib.import_module(".02_models", "src")
    
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
        folders = []
        for flags, delimiter, folder_name in mailboxes:
            folders.append(folder_name)
        
        # Phase 13C Part 4: User Fetch-Einstellungen laden (global)
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
        # Make UI setting authoritative: if the user explicitly set a per-folder value (>0),
        # use that. Otherwise distribute the global `limit` across folders.
        # This avoids the previous "cannot increase above 100" trap and makes the UI
        # usable for raising the per-folder fetch amount.
        if user_mails_per_folder and int(user_mails_per_folder) > 0:
            mails_per_folder = int(user_mails_per_folder)
        else:
            if folders and limit:
                mails_per_folder = max(1, int(limit // len(folders)))
            else:
                # fallback to a sensible default (UI shows 100)
                mails_per_folder = int(user_mails_per_folder or 100)
        
        # Phase 13C Part 4: Delta-Sync: Hole highest UID per folder aus DB
        from sqlalchemy import func
        folder_max_uids = {}
        
        if user_use_delta and account.initial_sync_done:
            # Query: SELECT imap_folder, MAX(imap_uid) FROM raw_emails WHERE account_id=X GROUP BY imap_folder
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
            if include_folders and folder_name not in include_folders:
                logger.debug(f"  ⏭️  {folder_name}: Nicht in Include-Liste")
                continue
            
            if exclude_folders and folder_name in exclude_folders:
                logger.debug(f"  ⏭️  {folder_name}: In Exclude-Liste")
                continue
            
            filtered_folders.append(folder_name)
        
        logger.info(f"  📂 {len(filtered_folders)}/{len(folders)} Ordner nach Filter")
        
        # ════════════════════════════════════════════════════════════════
        # WICHTIG: Lade existierende message_ids auf ACCOUNT-Ebene!
        # ════════════════════════════════════════════════════════════════
        existing_msgids_result = (
            session.query(models.RawEmail.message_id)
            .filter(
                models.RawEmail.mail_account_id == account.id,
                models.RawEmail.deleted_at.is_(None),
                models.RawEmail.message_id.isnot(None)
            )
            .all()
        )
        existing_msgids = set(r[0] for r in existing_msgids_result if r[0])
        logger.debug(f"  📊 {len(existing_msgids)} message_ids bereits in DB (Account-Ebene)")
        
        for folder_idx, folder_name in enumerate(filtered_folders, 1):
            try:
                # Progress-Callback
                if progress_callback:
                    progress_callback(
                        phase='fetch_folder', 
                        message=f"Lade '{folder_name}'...", 
                        folder_idx=folder_idx, 
                        total_folders=len(filtered_folders)
                    )
                
                # Phase 13C Part 6: SINCE-Datum und UNSEEN-Filter vom Account
                fetch_since = None
                fetch_unseen = account_unseen_only
                
                if account_since_date:
                    fetch_since = datetime.combine(account_since_date, datetime.min.time())
                
                # ════════════════════════════════════════════════════════════════
                # KORREKTUR: Filter-basiertes Delta-Sync
                # ════════════════════════════════════════════════════════════════
                uid_range = None
                missing_uids = None
                
                if user_use_delta and account.initial_sync_done:
                    # Hole existierende UIDs aus DB für diesen Ordner
                    db_uids_result = (
                        session.query(models.RawEmail.imap_uid)
                        .filter(
                            models.RawEmail.mail_account_id == account.id,
                            models.RawEmail.imap_folder == folder_name,
                            models.RawEmail.deleted_at.is_(None)
                        )
                        .all()
                    )
                    db_uids = set(int(r[0]) for r in db_uids_result if r[0])
                    
                    if fetch_since or fetch_unseen:
                        # Filter-basiertes Delta: Hole UIDs vom Server die dem Filter entsprechen
                        try:
                            server_uids = fetcher.search_uids(
                                folder=folder_name,
                                since=fetch_since,
                                unseen_only=fetch_unseen
                            )
                            if server_uids:
                                missing_uids = [uid for uid in server_uids if uid not in db_uids]
                                logger.info(
                                    f"  🔄 {folder_name}: Filter-Delta {len(missing_uids)}/{len(server_uids)} "
                                    f"(Server: {len(server_uids)}, DB: {len(db_uids)})"
                                )
                                if not missing_uids:
                                    logger.info(f"  ✓ {folder_name}: Alle {len(server_uids)} Mails bereits in DB")
                                    continue
                        except Exception as search_err:
                            logger.warning(f"  ⚠️ UID-Search fehlgeschlagen für {folder_name}: {search_err}")
                            missing_uids = None
                    else:
                        # Kein SINCE/UNSEEN-Filter: Klassisches UID-basiertes Delta
                        if folder_name in folder_max_uids:
                            last_uid = folder_max_uids[folder_name]
                            uid_range = f"{last_uid + 1}:*"
                            logger.info(f"  🔄 {folder_name}: Delta ab UID {last_uid + 1}")
                
                # IMAPClient braucht einfach den folder_name!
                folder_emails = fetcher.fetch_new_emails(
                    folder=folder_name,
                    limit=mails_per_folder,
                    unseen_only=fetch_unseen if not missing_uids else False,
                    uid_range=uid_range,
                    since=fetch_since if not missing_uids else None,
                    account_id=account.id,
                    session=session,
                    specific_uids=missing_uids
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
    session, user, account, raw_emails: list[Dict[str, Any]], master_key: str,
    progress_callback: Optional[Callable] = None
) -> int:
    """
    Speichert RawEmails verschlüsselt in der Datenbank
    
    1:1 KOPIE aus Legacy 14_background_jobs.py

    Phase 14e: RFC-konform Unique Key (account, folder, uidvalidity, uid)
    Phase 17: Semantic Search - Embedding-Generierung
    """
    encryption = importlib.import_module(".08_encryption", "src")
    models = importlib.import_module(".02_models", "src")
    ai_client = importlib.import_module(".03_ai_client", "src")
    
    saved = 0
    skipped = 0
    updated = 0
    total = len(raw_emails)
    
    # Phase 17: AI-Client für Embeddings (User Settings EMBEDDING Model!)
    embedding_ai_client = None
    resolved_model = None
    try:
        # WICHTIG: Nutze EMBEDDING Settings (nicht BASE!)
        provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
        model_embedding = user.preferred_embedding_model or "all-minilm:22m"
        resolved_model = ai_client.resolve_model(provider_embedding, model_embedding)
        
        embedding_ai_client = ai_client.build_client(provider_embedding, model=resolved_model)
        logger.info(f"✅ Embedding AI-Client ({resolved_model}) initialisiert")
    except Exception as e:
        logger.warning(f"⚠️ Embedding AI-Client nicht verfügbar: {e}")
    
    for idx, raw_email_data in enumerate(raw_emails, 1):
        # Progress-Callback
        if progress_callback and idx % 10 == 0:
            progress_callback(
                phase='persist_emails', 
                message=f"Speichere {idx}/{total}...", 
                processed=idx, 
                total=total
            )
        
        # Phase 14e: RFC-konform Unique Key
        imap_folder = raw_email_data.get("imap_folder")
        imap_uid = raw_email_data.get("imap_uid")
        imap_uidvalidity = raw_email_data.get("imap_uidvalidity")
        message_id = raw_email_data.get("message_id")
        
        if not imap_folder or not imap_uid or not imap_uidvalidity:
            logger.warning(
                f"⚠️ Mail ohne folder/uid/uidvalidity: "
                f"{raw_email_data.get('subject', 'N/A')[:30]}"
            )
            continue
        
        # ════════════════════════════════════════════════════════════════
        # SCHRITT 2: NUR INSERT - KEINE MOVE-LOGIK HIER!
        # MOVE-Erkennung macht Schritt 3 (sync_raw_emails_with_state)
        # ════════════════════════════════════════════════════════════════
        
        # Check if exists by folder/uid/uidvalidity (RFC-konform)
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
            # UPDATE: Mail existiert bereits (gleicher folder/uid), nur Flags aktualisieren
            existing.imap_flags = raw_email_data.get("imap_flags")
            existing.imap_is_seen = raw_email_data.get("imap_is_seen", False)
            existing.imap_is_flagged = raw_email_data.get("imap_is_flagged", False)
            existing.imap_is_answered = raw_email_data.get("imap_is_answered", False)
            existing.imap_last_seen_at = datetime.now(UTC)
            updated += 1
            logger.debug(f"🔄 UPDATE: {imap_folder}/{imap_uid}")
            continue
        
        # ════════════════════════════════════════════════════════════════
        # WICHTIG: Prüfe ob message_id schon existiert (in IRGENDEINEM Ordner!)
        # ════════════════════════════════════════════════════════════════
        existing_by_msgid = None
        
        if message_id:
            existing_by_msgid = (
                session.query(models.RawEmail)
                .filter_by(
                    user_id=user.id,
                    mail_account_id=account.id,
                    message_id=message_id,
                )
                .first()
            )
            
            if existing_by_msgid:
                if existing_by_msgid.deleted_at:
                    # WIEDERHERSTELLEN: Mail war gelöscht, ist aber wieder auf Server!
                    existing_by_msgid.deleted_at = None
                    existing_by_msgid.imap_folder = imap_folder
                    existing_by_msgid.imap_uid = imap_uid
                    existing_by_msgid.imap_uidvalidity = imap_uidvalidity
                    existing_by_msgid.imap_flags = raw_email_data.get("imap_flags")
                    existing_by_msgid.imap_is_seen = raw_email_data.get("imap_is_seen", False)
                    existing_by_msgid.imap_is_flagged = raw_email_data.get("imap_is_flagged", False)
                    existing_by_msgid.imap_is_answered = raw_email_data.get("imap_is_answered", False)
                    existing_by_msgid.imap_last_seen_at = datetime.now(UTC)
                    updated += 1
                    logger.info(f"♻️ UNDELETE: {imap_folder}/{imap_uid} (id={existing_by_msgid.id})")
                    continue
                else:
                    # Mail aktiv, anderer Ordner → Schritt 3 macht MOVE
                    skipped += 1
                    logger.debug(
                        f"⏭️ Skip: message_id existiert bereits in {existing_by_msgid.imap_folder} "
                        f"(Schritt 3 macht MOVE nach {imap_folder})"
                    )
                    continue
        
        # Fallback: content_hash (für Mails ohne message_id)
        content_hash = raw_email_data.get("content_hash")
        if not existing_by_msgid and content_hash:
            existing_by_hash = (
                session.query(models.RawEmail)
                .filter_by(
                    user_id=user.id,
                    mail_account_id=account.id,
                    content_hash=content_hash,
                )
                .first()
            )
            
            if existing_by_hash:
                if existing_by_hash.deleted_at:
                    # WIEDERHERSTELLEN
                    existing_by_hash.deleted_at = None
                    existing_by_hash.imap_folder = imap_folder
                    existing_by_hash.imap_uid = imap_uid
                    existing_by_hash.imap_uidvalidity = imap_uidvalidity
                    existing_by_hash.imap_flags = raw_email_data.get("imap_flags")
                    existing_by_hash.imap_is_seen = raw_email_data.get("imap_is_seen", False)
                    existing_by_hash.imap_is_flagged = raw_email_data.get("imap_is_flagged", False)
                    existing_by_hash.imap_is_answered = raw_email_data.get("imap_is_answered", False)
                    existing_by_hash.imap_last_seen_at = datetime.now(UTC)
                    updated += 1
                    logger.info(f"♻️ UNDELETE: {imap_folder}/{imap_uid} (id={existing_by_hash.id})")
                    continue
                else:
                    skipped += 1
                    logger.debug(
                        f"⏭️ Skip: content_hash existiert bereits in {existing_by_hash.imap_folder} "
                        f"(Schritt 3 macht MOVE nach {imap_folder})"
                    )
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
                        model_name=resolved_model
                    )
                if embedding_bytes:
                    logger.debug(f"🔍 Embedding generiert für: {subject_plain[:50]}...")
            except Exception as e:
                logger.warning(f"⚠️ Embedding-Fehler: {e}")
        
        # ════════════════════════════════════════════════════════════════
        # PHASE 26: Auto-Translation (VOR Verschlüsselung!)
        # ════════════════════════════════════════════════════════════════
        detected_lang = None
        encrypted_translation_de = None
        translation_engine = None
        
        if subject_plain or body_plain:
            try:
                from src.services.translator_service import get_translator
                translator = get_translator()
                
                # 1. Sprache erkennen - HTML-Stripping für korrekte Detection!
                text_for_detection = f"{subject_plain}\n{body_plain[:1500]}"
                
                # HTML-Tags entfernen VOR Language Detection (verhindert "en" Bias)
                if '<' in text_for_detection[:500]:
                    try:
                        from inscriptis import get_text
                        from inscriptis.model.config import ParserConfig
                        text_for_detection = get_text(text_for_detection, ParserConfig(display_links=False))
                    except Exception:
                        # Fallback: einfaches Strip von Tags
                        import re
                        text_for_detection = re.sub(r'<[^>]+>', ' ', text_for_detection)
                
                detection = translator.detect_language(text_for_detection[:1000])
                detected_lang = detection.language
                
                logger.debug(f"🌍 Detected language: {detected_lang} ({detection.confidence:.2f})")
                
                # 2. Falls nicht Deutsch → übersetzen (Confidence > 70%)
                if detected_lang != 'de' and detection.confidence > 0.7:
                    try:
                        # Sync-Wrapper für Celery (asyncio.run intern)
                        # Max 1500 Zeichen (Chunking in translator_service.py)
                        text_to_translate = f"{subject_plain}\n\n{body_plain[:1500]}"
                        
                        result = translator.translate_sync(
                            text=text_to_translate,
                            target_lang='de',
                            source_lang=detected_lang,
                            engine='local'  # Opus-MT
                        )
                        
                        # Verschlüsseln der Übersetzung
                        encrypted_translation_de = encryption.EncryptionManager.encrypt_data(
                            result.translated_text, master_key
                        )
                        translation_engine = result.model_used
                        
                        logger.info(f"🌍 Translated {detected_lang}→de via {translation_engine}")
                        
                    except Exception as trans_err:
                        logger.warning(f"⚠️  Translation fehlgeschlagen: {trans_err}")
                        
            except Exception as lang_err:
                logger.warning(f"⚠️  Language detection fehlgeschlagen: {lang_err}")

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

        # Inline-Attachments (CID-Bilder) verschlüsseln
        encrypted_inline_attachments = None
        inline_attachments = raw_email_data.get("inline_attachments")
        if inline_attachments:
            import json
            encrypted_inline_attachments = encryption.EncryptionManager.encrypt_data(
                json.dumps(inline_attachments), master_key
            )

        # Phase 25: Kalenderdaten verschlüsseln
        encrypted_calendar_data = None
        calendar_data = raw_email_data.get("calendar_data")
        if calendar_data:
            import json
            encrypted_calendar_data = encryption.EncryptionManager.encrypt_data(
                json.dumps(calendar_data, ensure_ascii=False), master_key
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
            imap_uidvalidity=raw_email_data.get("imap_uidvalidity"),
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
            # Inline-Attachments (CID-Bilder) für korrektes HTML-Rendering
            encrypted_inline_attachments=encrypted_inline_attachments,
            # Phase 17: Semantic Search - Embeddings (NICHT verschlüsselt!)
            email_embedding=embedding_bytes,
            embedding_model=embedding_model,
            embedding_generated_at=embedding_generated_at,
            # Phase 26: Auto-Translation
            detected_language=detected_lang,
            encrypted_translation_de=encrypted_translation_de,
            translation_engine=translation_engine,
            # Phase 25: Kalendereinladungen
            is_calendar_invite=raw_email_data.get("is_calendar_invite", False),
            calendar_method=calendar_data.get("method") if calendar_data else None,
            encrypted_calendar_data=encrypted_calendar_data,
            # Phase 27: Processing Status - Initial
            processing_status=models.EmailProcessingStatus.NEW,  # Startet bei 0
            processing_retry_count=0,
            processing_last_attempt_at=datetime.now(UTC),
        )
        
        try:
            session.add(raw_email)
            session.flush()  # Flush um raw_email.id zu bekommen
            
            # Phase 27: Status-Update nach erfolgreichem DB-Insert
            # Embedding wurde bereits generiert → Status auf 10
            if embedding_bytes:
                raw_email.processing_status = models.EmailProcessingStatus.EMBEDDING_DONE
            
            # Translation wurde bereits gemacht → Status auf 20
            if encrypted_translation_de or detected_lang == 'de':
                raw_email.processing_status = models.EmailProcessingStatus.TRANSLATION_DONE
            
            session.flush()  # Status speichern
            
            # Klassische Anhänge speichern (verschlüsselt)
            classic_attachments = raw_email_data.get("attachments", [])
            if classic_attachments:
                for att_data in classic_attachments:
                    try:
                        # Verschlüssele Anhang-Daten (base64)
                        encrypted_att_data = encryption.EncryptionManager.encrypt_data(
                            att_data["data"], master_key
                        )
                        
                        attachment = models.EmailAttachment(
                            raw_email_id=raw_email.id,
                            filename=att_data["filename"],
                            mime_type=att_data["mime_type"],
                            size=att_data["size"],
                            content_id=att_data.get("content_id"),
                            encrypted_data=encrypted_att_data,
                        )
                        session.add(attachment)
                    except Exception as att_err:
                        logger.warning(f"⚠️ Anhang '{att_data.get('filename')}' nicht gespeichert: {att_err}")
                
                session.flush()
                logger.debug(f"📎 {len(classic_attachments)} Anhänge für Email {raw_email.id} gespeichert")
            
            saved += 1
        except Exception as e:
            session.rollback()
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


def resume_incomplete_processing(session, user, account, master_key, self_task):
    """
    Phase 27: Resume-Processor - Verarbeitet Mails mit processing_status < 100
    
    Wird VOR dem Fetch aufgerufen. Emails die bei früherem Crash/Timeout
    nicht fertig verarbeitet wurden, werden hier abgeschlossen.
    
    Returns: Anzahl abgeschlossener Emails
    """
    models = importlib.import_module(".02_models", "src")
    from datetime import datetime, UTC, timedelta
    
    # Query: Alle Emails mit status < 100 (nicht fertig)
    incomplete_emails = (
        session.query(models.RawEmail)
        .filter(
            models.RawEmail.user_id == user.id,
            models.RawEmail.mail_account_id == account.id,
            models.RawEmail.processing_status < models.EmailProcessingStatus.COMPLETE,
            models.RawEmail.deleted_at.is_(None)
        )
        .all()
    )
    
    if not incomplete_emails:
        return 0
    
    logger.info(f"🔄 Resume: {len(incomplete_emails)} unvollständige Emails gefunden")
    
    completed = 0
    
    for email in incomplete_emails:
        try:
            # Retry-Logik: Fehler-Status mit zu vielen Retries → Skip
            if models.EmailProcessingStatus.is_error(email.processing_status):
                if not models.EmailProcessingStatus.needs_retry(
                    email.processing_status, email.processing_retry_count
                ):
                    logger.warning(
                        f"⏭️ Skip Email {email.id}: Max Retries erreicht "
                        f"(status={email.processing_status}, retries={email.processing_retry_count})"
                    )
                    continue
                
                # Retry: Status zurücksetzen
                email.processing_status = models.EmailProcessingStatus.get_retry_status(
                    email.processing_status
                )
                email.processing_retry_count += 1
                email.processing_last_attempt_at = datetime.now(UTC)
                session.commit()
                logger.info(
                    f"🔁 Retry Email {email.id}: status={email.processing_status}, "
                    f"attempt={email.processing_retry_count}"
                )
            
            # Verarbeitung basierend auf aktuellem Status
            # NOTE: Business-Logik bleibt in den jeweiligen Funktionen!
            # Hier nur Status-Check + Weiterleitung
            
            if email.processing_status < models.EmailProcessingStatus.EMBEDDING_DONE:
                # Embedding fehlt → wird in process_pending_raw_emails gemacht
                pass
            
            if email.processing_status < models.EmailProcessingStatus.TRANSLATION_DONE:
                # Translation fehlt → wird in process_pending_raw_emails gemacht
                pass
            
            # ... weitere Stati analog
            
            # WICHTIG: Die eigentliche Verarbeitung macht process_pending_raw_emails()
            # Wir zählen hier nur, wie viele ready sind
            completed += 1
            
        except Exception as e:
            logger.error(f"❌ Resume Email {email.id} fehlgeschlagen: {e}")
            email.processing_error = str(e)
            email.processing_last_attempt_at = datetime.now(UTC)
            session.commit()
    
    logger.info(f"✅ Resume: {completed} Emails bereit für Verarbeitung")
    return completed


@celery_app.task(
    bind=True, 
    max_retries=3, 
    default_retry_delay=60, 
    name="tasks.sync_user_emails",
    # KEIN time_limit! Mail-Sync kann bei 1000+ Emails Stunden dauern
    # Mit Translation/Embedding: ~300ms pro Email = 5 Min für 1000 Emails
    time_limit=None,
    soft_time_limit=None
)
def sync_user_emails(self, user_id: int, account_id: int, service_token_id: int, max_emails: int | None = None):
    """
    Sync Emails - 6 Schritte wie Legacy 14_background_jobs.py
    
    1:1 KOPIE der _execute_fetch_job() Methode
    
    Phase 2 Security: ServiceToken Pattern
    - Kein master_key als Parameter (wäre Plaintext in Redis!)
    - service_token_id → DEK wird aus DB geladen
    
    CONCURRENCY PROTECTION:
    - Verhindert parallele Sync-Tasks für denselben Account via Redis-Lock
    - Timeout 3600s (1h) - wenn Task länger dauert, wird Lock automatisch freigegeben
    """
    from celery.exceptions import Reject
    
    # Redis-Lock: Verhindert parallele Syncs desselben Accounts
    lock_key = f"mail_sync_lock:user_{user_id}:account_{account_id}"
    lock_timeout = 600  # 10 Minuten max (auto-expire bei Worker-Crash)
    
    # Versuche Lock zu bekommen
    redis_client = celery_app.backend.client  # Redis connection von Celery
    lock_acquired = redis_client.set(lock_key, self.request.id, nx=True, ex=lock_timeout)
    
    if not lock_acquired:
        # Ein anderer Worker synchronisiert bereits - prüfe ob Task noch existiert
        existing_task_id = redis_client.get(lock_key)
        if existing_task_id:
            existing_task_id = existing_task_id.decode()
            # Prüfe ob Task-Result existiert (wenn nicht: stuck lock!)
            task_result_key = f"celery-task-meta-{existing_task_id}"
            task_exists = redis_client.exists(task_result_key)
            
            if not task_exists:
                # Lock ist stuck (Task existiert nicht mehr) → übernehmen!
                logger.warning(
                    f"🔧 Stuck lock erkannt für Account {account_id} (Task {existing_task_id} existiert nicht). "
                    f"Übernehme Lock..."
                )
                redis_client.set(lock_key, self.request.id, ex=lock_timeout)
                lock_acquired = True
            else:
                logger.warning(
                    f"⏳ Sync übersprungen: Account {account_id} wird bereits synchronisiert (Task {existing_task_id})"
                )
                raise Reject("Account sync already in progress", requeue=False)
        else:
            # Kein Lock vorhanden, aber SET nx=True failed? Retry
            lock_acquired = redis_client.set(lock_key, self.request.id, nx=True, ex=lock_timeout)
            if not lock_acquired:
                raise Reject("Account sync already in progress", requeue=False)
    
    try:
        _execute_sync_with_lock(self, user_id, account_id, service_token_id, max_emails)
    finally:
        # Lock freigeben (nur wenn wir ihn haben!)
        current_lock = redis_client.get(lock_key)
        if current_lock and current_lock.decode() == self.request.id:
            redis_client.delete(lock_key)
            logger.info(f"🔓 Lock freigegeben für Account {account_id}")


def _execute_sync_with_lock(self, user_id: int, account_id: int, service_token_id: int, max_emails: int | None = None):
    """Eigentliche Sync-Logik (nach Lock-Acquisition)"""
    session = get_session()
    saved = 0
    processed = 0
    sync_service = None
    stats1 = None
    master_key = None  # Wird aus ServiceToken geladen
    
    try:
        user = get_user(session, user_id)
        account = get_mail_account(session, account_id, user_id)
        if not user or not account:
            return {"status": "error", "message": "User oder Account nicht gefunden"}
        
        # Phase 2 Security: DEK aus ServiceToken laden
        master_key = _get_dek_from_service_token(service_token_id, session)
        if not master_key:
            return {"status": "error", "message": "DEK konnte nicht aus ServiceToken geladen werden"}
        
        logger.info(f"🚀 Sync für user {user_id}, account {account_id}")
        
        # Module laden
        encryption = importlib.import_module(".08_encryption", "src")
        mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
        mail_sync_v2 = importlib.import_module(".services.mail_sync_v2", "src")
        processing_mod = importlib.import_module(".12_processing", "src")
        ai_client_mod = importlib.import_module(".03_ai_client", "src")
        # HINWEIS: 04_sanitizer entfernt - Sanitization-Level wird jetzt inline berechnet
        # Die eigentliche Anonymisierung erfolgt in 12_processing.py mit content_sanitizer.py (spaCy NER)
        
        # ═══════════════════════════════════════════════════════════════
        # PHASE 27: Resume unvollständige Emails (VOR dem Fetch!)
        # ═══════════════════════════════════════════════════════════════
        
        self.update_state(
            state='PROGRESS',
            meta={
                "phase": "resume_incomplete",
                "message": "Prüfe unvollständige Emails...",
            }
        )
        
        try:
            resumed = resume_incomplete_processing(session, user, account, master_key, self)
            if resumed > 0:
                logger.info(f"✅ {resumed} unvollständige Emails für Verarbeitung vorbereitet")
        except Exception as e:
            logger.error(f"⚠️ Resume fehlgeschlagen (nicht kritisch): {e}")
        
        # ═══════════════════════════════════════════════════════════════
        # SCHRITT 1: State mit Server synchronisieren (DELETE + INSERT pro Ordner)
        # ═══════════════════════════════════════════════════════════════
        
        include_folders = None
        if account.fetch_include_folders:
            try:
                include_folders = json.loads(account.fetch_include_folders)
                logger.info(f"🔄 Schritt 1: State-Sync für Ordner: {include_folders}")
            except json.JSONDecodeError:
                logger.warning("Ungültiges JSON in fetch_include_folders, ignoriere Filter")
        
        # IMAP-Verbindung für State-Sync aufbauen
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
            port=account.imap_port or 993,
        )
        fetcher.connect()
        
        # Progress-Callback für State-Sync
        def state_sync_progress(phase, message, **kwargs):
            """Callback für kontinuierliche Progress-Updates während State-Sync."""
            logger.info(f"🔔 DEBUG: Callback aufgerufen! phase={phase}, message={message}")
            self.update_state(
                state='PROGRESS',
                meta={
                    "phase": phase,
                    "message": message,
                    **kwargs
                }
            )
            logger.info(f"✅ DEBUG: Status updated")
        
        logger.info(f"🎯 DEBUG: Callback-Funktion definiert, übergebe an sync_state_with_server")
        
        try:
            # Schritt 1: Nur State-Sync (kein Raw-Sync hier!)
            sync_service = mail_sync_v2.MailSyncServiceV2(
                imap_connection=fetcher.connection,
                db_session=session,
                user_id=user_id,
                account_id=account_id
            )
            stats1 = sync_service.sync_state_with_server(
                include_folders, 
                progress_callback=state_sync_progress
            )
            
            logger.info(
                f"✅ Schritt 1: {stats1.folders_scanned} Ordner, "
                f"{stats1.mails_on_server} Server-Mails, "
                f"+{stats1.state_inserted} -{stats1.state_deleted} State"
            )
            
            # Account Last Sync Timestamp aktualisieren
            account.last_server_sync_at = datetime.now(UTC)
            session.commit()
            
        finally:
            fetcher.disconnect()
        
        # ═══════════════════════════════════════════════════════════════
        # SCHRITT 2: Neue Mails fetchen (Delta-Fetch)
        # ═══════════════════════════════════════════════════════════════
        
        self.update_state(
            state='PROGRESS',
            meta={
                "phase": "fetch_mails",
                "message": "Lade neue Mails...",
            }
        )
        
        def fetch_progress(phase, message, **kwargs):
            self.update_state(state='PROGRESS', meta={'phase': phase, 'message': message, **kwargs})
        
        # Bestimme max_emails dynamisch, wenn kein expliziter Wert übergeben wurde
        if max_emails is None:
            # Priorität: user.fetch_max_total (0 = unbegrenzt) → else konfigurierbarer Default
            user_max_total = getattr(account.user, 'fetch_max_total', 0) or 0
            if user_max_total and int(user_max_total) > 0:
                max_emails = int(user_max_total)
            else:
                # Großzügigerer System-Default (statt harter 50)
                max_emails = 200

        raw_emails = _fetch_raw_emails(
            account, master_key, max_emails, session, fetch_progress
        )
        
        if raw_emails:
            logger.info(f"📧 {len(raw_emails)} Mails abgerufen, speichere in DB...")
            
            def persist_progress(phase, message, **kwargs):
                self.update_state(state='PROGRESS', meta={'phase': phase, 'message': message, **kwargs})
            
            saved = _persist_raw_emails(
                session, user, account, raw_emails, master_key, persist_progress
            )
        
        # ═══════════════════════════════════════════════════════════════
        # SCHRITT 3: raw_emails mit State synchronisieren (MOVE-Erkennung!)
        # ═══════════════════════════════════════════════════════════════
        
        self.update_state(
            state='PROGRESS',
            meta={
                "phase": "sync_raw",
                "message": "Synchronisiere Mails...",
            }
        )
        
        try:
            if sync_service:
                stats3 = sync_service.sync_raw_emails_with_state()
                logger.info(
                    f"✅ Schritt 3: {stats3.raw_updated} MOVE erkannt, "
                    f"{stats3.raw_deleted} gelöscht, {stats3.raw_linked} verlinkt"
                )
        except Exception as e:
            logger.error(f"❌ Schritt 3 fehlgeschlagen: {e}")

        # ═══════════════════════════════════════════════════════════════
        # SCHRITT 4: AI-Verarbeitung
        # ═══════════════════════════════════════════════════════════════
        
        provider = user.preferred_ai_provider or "ollama"
        model = ai_client_mod.resolve_model(provider, user.preferred_ai_model)
        # Level-Logik inline: Cloud-Provider brauchen volle Anonymisierung (Level 3), lokal Level 2
        is_cloud_provider = ai_client_mod.provider_requires_cloud(provider)
        sanitize_level = 3 if is_cloud_provider else 2
        ai_instance = ai_client_mod.build_client(provider, model=model)
        
        logger.info(f"🤖 AI-Verarbeitung mit {provider}/{model}")

        def progress_callback(idx: int, total: int, subject: str) -> None:
            self.update_state(
                state='PROGRESS',
                meta={
                    "phase": None,  # ⚠️ Phase clearen = Frontend zeigt Email-Counter
                    "message": None,
                    "current_email_index": idx,
                    "total_emails": total,
                    "current_subject": subject,
                },
            )

        processed = processing_mod.process_pending_raw_emails(
            session=session,
            user=user,
            master_key=master_key,
            mail_account=account,
            limit=max_emails,
            ai=ai_instance,
            sanitize_level=sanitize_level,
            progress_callback=progress_callback,
        )
        
        # ═══════════════════════════════════════════════════════════════
        # SCHRITT 5: Auto-Action Rules nach Email-Fetch anwenden
        # ═══════════════════════════════════════════════════════════════
        
        self.update_state(
            state='PROGRESS',
            meta={
                "phase": "auto_rules",
                "message": "Wende Auto-Rules an...",
            }
        )
        
        try:
            from src.auto_rules_engine import AutoRulesEngine
            
            rules_engine = AutoRulesEngine(user_id, master_key, session)
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
        # FINALISIERUNG
        # ═══════════════════════════════════════════════════════════════

        account.last_fetch_at = datetime.now(UTC)
        
        if not account.initial_sync_done:
            account.initial_sync_done = True
            logger.info(f"🎉 Initialer Sync für Account {account.id} abgeschlossen")
        
        session.commit()

        logger.info(
            f"✅ Job abgeschlossen (saved={saved}, processed={processed})"
        )
        
        return {
            "status": "success", 
            "saved": saved, 
            "processed": processed, 
            "folders_scanned": stats1.folders_scanned if stats1 else 0, 
            "mails_on_server": stats1.mails_on_server if stats1 else 0
        }
        
    except Exception as exc:
        session.rollback()
        logger.exception(f"❌ Sync failed: {exc}")
        
        # P2-002: Nur transiente Fehler retrien (wie im Legacy)
        if _is_transient_error(exc):
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        else:
            # Permanente Fehler (Auth, ValueError etc.) nicht retrien
            logger.error(f"❌ Permanenter Fehler - kein Retry: {type(exc).__name__}")
            raise
        
    finally:
        # 🔒 Security: Sichere Master-Key Bereinigung aus RAM
        if 'master_key' in locals() and master_key is not None:
            master_key = '\x00' * len(master_key)
            del master_key
            gc.collect()
        session.close()


@celery_app.task(
    bind=True, 
    max_retries=2, 
    default_retry_delay=60, 
    name="tasks.batch_reprocess_emails",
    # Batch-Reprocess kann auch lange dauern (1000 Emails × 100ms Embedding)
    time_limit=None,
    soft_time_limit=None
)
def batch_reprocess_emails(self, user_id: int, service_token_id: int, provider: str, model: str):
    """
    Batch-Reprocess Job (regenerate embeddings for all emails).
    
    1:1 KOPIE aus Legacy 14_background_jobs.py _execute_batch_reprocess_job()
    
    Phase 2 Security: ServiceToken Pattern
    - Kein master_key als Parameter (wäre Plaintext in Redis!)
    - service_token_id → DEK wird aus DB geladen
    """
    session = get_session()
    processed = 0
    failed = 0
    master_key = None  # Wird aus ServiceToken geladen
    
    try:
        user = get_user(session, user_id)
        if not user:
            return {"status": "error", "message": "User nicht gefunden"}
        
        # Phase 2 Security: DEK aus ServiceToken laden
        master_key = _get_dek_from_service_token(service_token_id, session)
        if not master_key:
            return {"status": "error", "message": "DEK konnte nicht aus ServiceToken geladen werden"}
        
        encryption = importlib.import_module(".08_encryption", "src")
        models = importlib.import_module(".02_models", "src")
        ai_client = importlib.import_module(".03_ai_client", "src")

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
            return {
                "status": "success",
                "processed": 0,
                "failed": 0,
                "total_emails": 0,
                "message": "Keine Emails vorhanden"
            }
        
        total = len(raw_emails)
        logger.info(f"🔄 Batch-Reprocess: {total} Emails mit {model}")
        
        # Build AI Client
        resolved_model = ai_client.resolve_model(provider, model)
        embedding_client = ai_client.build_client(provider, model=resolved_model)
        
        # Update initial status
        self.update_state(
            state='PROGRESS',
            meta={
                "total_emails": total,
                "current_email_index": 0,
            }
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
                self.update_state(
                    state='PROGRESS',
                    meta={
                        "current_email_index": idx,
                        "total_emails": total,
                        "current_subject": decrypted_subject[:50] if decrypted_subject else "Kein Betreff",
                    }
                )
                
                logger.info(f"🔄 [{idx}/{total}] Verarbeite: {decrypted_subject[:50] if decrypted_subject else 'Kein Betreff'}...")
                
                # Embedding generieren
                embedding_bytes, model_name, timestamp = generate_embedding_for_email(
                    subject=decrypted_subject,
                    body=decrypted_body,
                    ai_client=embedding_client,
                    model_name=resolved_model
                )
                
                if embedding_bytes:
                    raw_email.email_embedding = embedding_bytes
                    raw_email.embedding_model = model_name or resolved_model
                    raw_email.embedding_generated_at = timestamp
                    
                    session.flush()
                    
                    processed += 1
                    logger.info(f"✅ [{idx}/{total}] Email {raw_email.id} embedded ({len(embedding_bytes)} bytes)")
                else:
                    failed += 1
                    logger.warning(f"⚠️  [{idx}/{total}] Embedding failed for email {raw_email.id}")
                    
            except Exception as e:
                failed += 1
                logger.error(f"❌ [{idx}/{total}] Failed to reprocess email {raw_email.id}: {e}")
        
        session.commit()
        
        # Tag-Embedding-Cache UND DB-Embeddings zurücksetzen nach Batch-Reprocess!
        # KRITISCH: Verhindert Dimensions-Mismatch zwischen alten Tags (z.B. 1024 dim)
        # und neuen Emails (z.B. 384 dim nach Model-Wechsel)
        try:
            from src.services.tag_manager import TagEmbeddingCache
            
            # 1. Memory-Cache leeren
            TagEmbeddingCache._cache.clear()
            TagEmbeddingCache._ai_client_cache.clear()
            logger.info("🗑️  Tag-Embedding-Cache geleert")
            
            # 2. DB-Embeddings zurücksetzen (werden beim nächsten Tagging-Vorgang neu erstellt)
            tag_reset_result = session.execute(
                sa_text("""
                    UPDATE email_tags 
                    SET learned_embedding = NULL,
                        learned_embedding_model = NULL,
                        embedding_updated_at = NULL,
                        negative_embedding = NULL,
                        negative_embedding_model = NULL,
                        negative_updated_at = NULL
                    WHERE user_id = :user_id
                      AND (learned_embedding IS NOT NULL OR negative_embedding IS NOT NULL)
                """),
                {"user_id": user_id}
            )
            session.commit()
            
            tags_reset = tag_reset_result.rowcount
            if tags_reset > 0:
                logger.info(f"🗑️  {tags_reset} Tag-Embeddings in DB zurückgesetzt (Model-Wechsel → neu generieren mit {resolved_model})")
            else:
                logger.info("ℹ️  Keine Tag-Embeddings zum Zurücksetzen gefunden")
                
        except Exception as cache_err:
            logger.warning(f"⚠️  Konnte Tag-Cache/DB nicht leeren: {cache_err}")
        
        logger.info(f"✅ Batch-Reprocess abgeschlossen (processed={processed}, failed={failed})")
        
        return {
            "status": "success",
            "processed": processed,
            "failed": failed,
            "total_emails": total,
            "model": resolved_model,
        }
        
    except Exception as exc:
        session.rollback()
        logger.exception(f"❌ Batch-Reprocess failed: {exc}")
        
        # P2-002: Nur transiente Fehler retrien (wie im Legacy)
        if _is_transient_error(exc):
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        else:
            logger.error(f"❌ Permanenter Fehler - kein Retry: {type(exc).__name__}")
            raise
        
    finally:
        if 'master_key' in locals() and master_key is not None:
            master_key = '\x00' * len(master_key)
            del master_key
            gc.collect()
        session.close()


@celery_app.task(
    bind=True, 
    max_retries=1, 
    name="tasks.sync_all_accounts",
    # KEIN time_limit! Multi-Account-Sync kann Stunden dauern (ruft sync_user_emails für jeden Account)
    time_limit=None,
    soft_time_limit=None
)
def sync_all_accounts(self, user_id: int, service_token_id: int):
    """
    Sync alle Accounts eines Users
    
    Phase 2 Security: ServiceToken Pattern
    - service_token_id wird an Sub-Tasks weitergegeben
    """
    session = get_session()
    try:
        user = get_user(session, user_id)
        if not user:
            return {"status": "error", "message": "User nicht gefunden"}
        
        successful = 0
        failed = 0
        
        for acc in user.mail_accounts:
            try:
                logger.info(f"🔄 Sync Account {acc.id} ({acc.name})...")
                result = sync_user_emails.apply_async(
                    args=[user_id, acc.id, service_token_id]
                ).get(timeout=600)  # 10 Minuten Timeout pro Account
                
                if result.get('status') == 'success':
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"❌ Account {acc.id}: {e}")
                failed += 1
        
        return {
            "status": "success", 
            "accounts_synced": successful,
            "accounts_failed": failed
        }
        
    finally:
        session.close()
