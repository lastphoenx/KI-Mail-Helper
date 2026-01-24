"""Shared processing helpers for turning RawEmail entries into ProcessedEmail rows."""

from __future__ import annotations

import logging
import importlib
from typing import Callable, Optional, List, Dict
from datetime import datetime, UTC

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

models = importlib.import_module(".02_models", "src")
sanitizer_mod = importlib.import_module(".04_sanitizer", "src")
ai_client_mod = importlib.import_module(".03_ai_client", "src")
scoring = importlib.import_module(".05_scoring", "src")
imap_flags_mod = importlib.import_module(".16_imap_flags", "src")

logger = logging.getLogger(__name__)


def build_thread_context(
    session,
    raw_email,
    master_key: str,
    max_context_emails: int = 5
) -> str:
    """Build conversation context from previous emails in the same thread.
    
    Phase E: Thread-Context Builder
    
    Collects previous emails in the same thread, decrypts them, and formats
    them into a context string for AI analysis. This helps the AI understand
    the conversation flow and improve classification accuracy.
    
    Args:
        session: SQLAlchemy session for DB queries
        raw_email: The current RawEmail being processed
        master_key: Master key for decryption (from Flask session)
        max_context_emails: Maximum number of previous emails to include (default: 5)
    
    Returns:
        Formatted context string with previous emails, or empty string if no context
    
    Example output:
        '''
        CONVERSATION CONTEXT (3 previous emails):
        
        [1] 2025-01-01 10:00 | From: alice@example.com
        Subject: Project Update
        Body: Initial project status update...
        
        [2] 2025-01-01 14:30 | From: bob@example.com  
        Subject: Re: Project Update
        Body: Thanks for the update. I have a question...
        
        [3] 2025-01-01 16:00 | From: alice@example.com
        Subject: Re: Project Update  
        Body: Sure, let me answer that...
        '''
    """
    if not raw_email.thread_id:
        logger.debug(f"RawEmail {raw_email.id} has no thread_id - no context available")
        return ""
    
    try:
        # Query previous emails in same thread (older than current email)
        # Use received_at for chronological ordering (IDs can be non-sequential)
        thread_emails = (
            session.query(models.RawEmail)
            .filter(
                models.RawEmail.thread_id == raw_email.thread_id,
                models.RawEmail.received_at < raw_email.received_at,  # Time-based filter!
                models.RawEmail.deleted_at.is_(None)  # P1-002: deleted_verm entfernt
            )
            .order_by(models.RawEmail.received_at.asc())
            .limit(max_context_emails)
            .all()
        )
        
        if not thread_emails:
            logger.debug(f"Thread {raw_email.thread_id} has no previous emails (first in thread)")
            return ""
        
        # Decrypt and format context
        encryption_mod = importlib.import_module(".08_encryption", "src")
        context_lines = [
            f"CONVERSATION CONTEXT ({len(thread_emails)} previous email{'s' if len(thread_emails) > 1 else ''}):",
            ""
        ]
        
        for idx, email in enumerate(thread_emails, 1):
            try:
                # Decrypt email data
                sender = encryption_mod.EmailDataManager.decrypt_email_sender(
                    email.encrypted_sender or "", master_key
                )
                subject = encryption_mod.EmailDataManager.decrypt_email_subject(
                    email.encrypted_subject or "", master_key
                )
                body = encryption_mod.EmailDataManager.decrypt_email_body(
                    email.encrypted_body or "", master_key
                )
                
                # Format timestamp
                timestamp = email.received_at.strftime("%Y-%m-%d %H:%M") if email.received_at else "unknown"
                
                # Truncate body for context (max 300 chars)
                body_preview = body[:300] + "..." if len(body) > 300 else body
                
                # Attachment awareness
                attachment_info = ""
                if email.has_attachments:
                    attachment_info = " 📎 (has attachments)"
                
                context_lines.extend([
                    f"[{idx}] {timestamp} | From: {sender}{attachment_info}",
                    f"Subject: {subject}",
                    f"Body: {body_preview}",
                    ""  # Empty line between emails
                ])
                
            except Exception as e:
                logger.warning(f"Failed to decrypt email {email.id} for context: {e}")
                context_lines.extend([
                    f"[{idx}] (Decryption failed for previous email)",
                    ""
                ])
        
        context_str = "\n".join(context_lines)
        
        # P2-001: Intelligentes Truncation - behalte neueste Emails
        # Konfigurierbar und behält wichtigste (neueste) Emails statt einfach abzuschneiden
        max_context_chars = 4500  # Konfigurierbar
        
        if len(context_str) > max_context_chars:
            # Strategie: Behalte die letzten N Emails, nicht erste N Chars
            # Das ist wichtiger für Thread-Kontext (neueste Nachrichten relevanter)
            lines = context_str.split('\n')
            
            # Finde Email-Blöcke (beginnen mit "[N]")
            email_blocks = []
            current_block = []
            for line in lines:
                if line.strip().startswith('[') and ']' in line:
                    if current_block:
                        email_blocks.append('\n'.join(current_block))
                    current_block = [line]
                else:
                    current_block.append(line)
            if current_block:
                email_blocks.append('\n'.join(current_block))
            
            # Behalte Emails vom Ende bis max_context_chars erreicht
            kept_blocks = []
            total_len = 0
            for block in reversed(email_blocks):
                block_len = len(block)
                if total_len + block_len > max_context_chars:
                    break
                kept_blocks.insert(0, block)
                total_len += block_len
            
            if kept_blocks:
                context_str = '\n'.join(kept_blocks)
                removed_count = len(email_blocks) - len(kept_blocks)
                if removed_count > 0:
                    context_str = f"[{removed_count} older emails omitted for brevity]\n\n" + context_str
            else:
                # Fallback: Wenn kein Block passt, nehme einfach erste Chars
                context_str = context_str[:max_context_chars] + "\n\n[Context truncated due to size]"
        
        logger.info(f"Built thread context for {raw_email.id}: {len(thread_emails)} emails, {len(context_str)} chars")
        return context_str
        
    except Exception as e:
        logger.error(f"Failed to build thread context for {raw_email.id}: {e}", exc_info=True)
        return ""


def get_sender_hint_from_patterns(
    session,
    raw_email,
    master_key: str
) -> str:
    """Analyze sender behavior patterns from thread history.
    
    Phase E: Sender-Intelligence
    
    Examines previous emails from the same sender in this thread to detect:
    - Newsletter/automated email patterns
    - Notification patterns (e.g., GitHub, Jira)
    - Conversational vs. transactional style
    - Response patterns
    
    Args:
        session: SQLAlchemy session for DB queries
        raw_email: The current RawEmail being analyzed
        master_key: Master key for decryption
    
    Returns:
        Hint string for AI classifier, or empty string if no patterns detected
    
    Example outputs:
        "SENDER PATTERN: This sender typically sends newsletters (3/3 previous emails)"
        "SENDER PATTERN: This sender is conversational - expects replies (2/3 emails have responses)"
        ""
    """
    if not raw_email.thread_id:
        return ""
    
    try:
        encryption_mod = importlib.import_module(".08_encryption", "src")
        
        # Decrypt current sender
        current_sender = encryption_mod.EmailDataManager.decrypt_email_sender(
            raw_email.encrypted_sender or "", master_key
        )
        
        if not current_sender:
            return ""
        
        # Query previous emails from same sender in this thread
        sender_emails = (
            session.query(models.RawEmail)
            .filter(
                models.RawEmail.thread_id == raw_email.thread_id,
                models.RawEmail.received_at < raw_email.received_at,  # Time-based!
                models.RawEmail.deleted_at.is_(None)  # P1-002: deleted_verm entfernt
            )
            .order_by(models.RawEmail.received_at.desc())
            .limit(5)
            .all()
        )
        
        if len(sender_emails) < 2:
            # Need at least 2 emails to detect patterns
            return ""
        
        # Count sender's emails vs. others (case-insensitive comparison)
        sender_count = 0
        decryptable_count = 0  # Track successfully decrypted emails
        has_responses = False
        current_sender_lower = current_sender.lower()
        
        for email in sender_emails:
            email_sender = encryption_mod.EmailDataManager.decrypt_email_sender(
                email.encrypted_sender or "", master_key
            )
            
            # Null-safety: skip if decryption failed
            if not email_sender:
                continue
            
            decryptable_count += 1  # Count successfully decrypted emails
            
            if email_sender.lower() == current_sender_lower:
                sender_count += 1
            else:
                has_responses = True
        
        # Pattern detection (use decryptable_count instead of len(sender_emails))
        if sender_count == decryptable_count and decryptable_count >= 3:
            # All emails from same sender → likely newsletter/automation
            return f"SENDER PATTERN: This sender typically sends automated emails (no conversation, {decryptable_count}/{decryptable_count} from same sender)"
        
        if has_responses and sender_count >= 2:
            # Mix of sender and responses → conversational
            return f"SENDER PATTERN: This sender is conversational - thread has {decryptable_count} emails with responses"
        
        return ""
        
    except Exception as e:
        logger.warning(f"Failed to analyze sender patterns for {raw_email.id}: {e}")
        return ""


def map_exception_to_status(exc: Exception, current_step: str) -> int:
    """Map Exception zu processing_status Error-Code basierend auf aktuellem Schritt."""
    if current_step == "embedding":
        return models.EmailProcessingStatus.EMBEDDING_FAILED
    elif current_step == "translation":
        return models.EmailProcessingStatus.TRANSLATION_FAILED
    elif current_step == "sanitization":
        return models.EmailProcessingStatus.SANITIZATION_FAILED
    elif current_step == "ai_classification":
        return models.EmailProcessingStatus.AI_CLASSIFICATION_FAILED
    elif current_step == "auto_rules":
        return models.EmailProcessingStatus.AUTO_RULES_FAILED
    else:
        return -99  # Unknown error


def add_processing_warning(
    raw_email,
    code: str,
    step: str,
    message: str,
    **extra_fields
) -> None:
    """
    Fügt eine nicht-fatale Warnung zu processing_warnings hinzu.
    
    Args:
        raw_email: RawEmail Instanz
        code: Warning-Code (z.B. "TRANSLATION_UNAVAILABLE")
        step: Processing-Step (z.B. "translation")
        message: Fehlermeldung
        **extra_fields: Zusätzliche Felder (z.B. language="hy", model="...")
    
    Example:
        add_processing_warning(
            raw_email,
            code="TRANSLATION_UNAVAILABLE",
            step="translation",
            message="Translation model not available",
            language="hy",
            model="Helsinki-NLP/opus-mt-hy-de"
        )
    """
    from datetime import datetime, UTC
    import json
    
    # Erstelle Warning-Objekt
    warning = {
        "code": code,
        "step": step,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
        **extra_fields  # language, model, etc.
    }
    
    # Initialisiere processing_warnings wenn noch nicht vorhanden
    if raw_email.processing_warnings is None:
        raw_email.processing_warnings = []
    
    # JSONB wird automatisch serialisiert von SQLAlchemy
    # Aber bei Updates müssen wir eine neue Liste erstellen (trigger update)
    current_warnings = list(raw_email.processing_warnings) if raw_email.processing_warnings else []
    current_warnings.append(warning)
    raw_email.processing_warnings = current_warnings


def process_pending_raw_emails(
    session,
    user,
    *,
    master_key: Optional[str] = None,
    mail_account: Optional[object] = None,
    limit: Optional[int] = None,
    ai=None,
    sanitize_level: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    """Process RawEmails without ProcessedEmail entries for the given user.

    Args:
        master_key: Master-Key for encryption/decryption. Required for processing emails.
        progress_callback: Optional callback(current_index: int, total: int, subject: str) for each email.
    """
    if not user:
        return 0

    if not master_key:
        logger.warning(
            "⚠️  Master-Key nicht verfügbar - kann E-Mails nicht verarbeiten"
        )
        return 0

    level = (
        sanitize_level
        if sanitize_level is not None
        else sanitizer_mod.get_sanitization_level(False)
    )

    # PHASE 27: Query für Resume-Pipeline
    # Hole ALLE Mails die:
    # - Noch nicht COMPLETE sind (status < 100) ODER Fehler hatten (status < 0)
    # - AUCH wenn ProcessedEmail existiert (z.B. bei Re-Processing wegen falscher Übersetzung)
    query = (
        session.query(models.RawEmail)
        .outerjoin(
            models.ProcessedEmail,
            models.RawEmail.id == models.ProcessedEmail.raw_email_id,
        )
        .filter(
            models.RawEmail.user_id == user.id,
            models.RawEmail.deleted_at.is_(None),
            or_(
                models.RawEmail.processing_status < models.EmailProcessingStatus.COMPLETE,
                models.RawEmail.processing_status < 0  # Fehler-Status
            )
        )
    )

    if mail_account:
        query = query.filter(models.RawEmail.mail_account_id == mail_account.id)

    query = query.order_by(models.RawEmail.received_at.asc(), models.RawEmail.id.asc())

    if limit and limit > 0:
        query = query.limit(limit)

    pending_emails = query.all()
    if not pending_emails:
        return 0

    active_ai = ai or ai_client_mod.LocalOllamaClient()

    # Provider und Modell für Tracking ermitteln
    ai_provider = "ollama"  # Default
    if hasattr(active_ai, "__class__"):
        class_name = active_ai.__class__.__name__
        if "OpenAI" in class_name:
            ai_provider = "openai"
        elif "Anthropic" in class_name:
            ai_provider = "anthropic"
        elif "Ollama" in class_name:
            ai_provider = "ollama"

    ai_model = getattr(active_ai, "model", None) or "unknown"

    logger.info(
        "🧾 Verarbeite %d gespeicherte Mails für %s",
        len(pending_emails),
        getattr(mail_account, "name", user.username),
    )
    
    # 🚀 PERFORMANCE: Pre-Load alle Tag-Embeddings für User
    # Verhindert 11-13× Ollama-Calls pro Email (6min+ → 10s)
    try:
        tag_manager_mod = importlib.import_module(".services.tag_manager", "src")
        preloaded = tag_manager_mod.TagEmbeddingCache.preload_user_tags(user.id, session)
        logger.info(f"⚡ {preloaded} Tag-Embeddings vorgeladen")
    except Exception as e:
        logger.warning(f"⚠️  Tag-Preload fehlgeschlagen: {e}")

    processed_count = 0
    total_emails = len(pending_emails)

    # Zero-Knowledge: Hole Master-Key für Entschlüsselung
    # Wichtig: Dieser Key muss vom Caller übergeben werden (z.B. aus Flask Session)
    # oder aus user.encrypted_master_key_for_cron entschlüsselt werden
    # Für manuelle Verarbeitung (Web-Request) sollte master_key aus Session kommen

    for idx, raw_email in enumerate(pending_emails, 1):
        current_step = None  # Für Error-Mapping
        
        try:
            # ═══════════════════════════════════════════════════════════════════════
            # PHASE 27: PIPELINE-STRUKTUR MIT STATUS-CHECKS
            # ═══════════════════════════════════════════════════════════════════════
            
            # Quick check: Wenn ProcessedEmail existiert UND status=100 → Skip
            already_processed = (
                session.query(models.ProcessedEmail)
                .filter_by(raw_email_id=raw_email.id)
                .first()
            )
            if already_processed and raw_email.processing_status == models.EmailProcessingStatus.COMPLETE:
                logger.info(
                    "⏭️  RawEmail %s bereits vollständig verarbeitet – überspringe", raw_email.id
                )
                continue
            
            # Re-Processing: Lösche existierendes ProcessedEmail bei Neuverarbeitung
            if already_processed and raw_email.processing_status < models.EmailProcessingStatus.COMPLETE:
                logger.info(
                    f"🔄 RawEmail {raw_email.id} wird neu verarbeitet (Status {raw_email.processing_status}) "
                    f"- lösche altes ProcessedEmail {already_processed.id}"
                )
                session.delete(already_processed)
                session.flush()  # Sofort löschen, damit kein UniqueConstraint-Konflikt

            # Zero-Knowledge: Entschlüssele E-Mail-Inhalte mit master_key (wird für alle Schritte benötigt)
            try:
                encryption_mod = importlib.import_module(".08_encryption", "src")
                decrypted_subject = (
                    encryption_mod.EmailDataManager.decrypt_email_subject(
                        raw_email.encrypted_subject or "", master_key
                    )
                )
                decrypted_body = encryption_mod.EmailDataManager.decrypt_email_body(
                    raw_email.encrypted_body or "", master_key
                )
                decrypted_sender = encryption_mod.EmailDataManager.decrypt_email_sender(
                    raw_email.encrypted_sender or "", master_key
                )
            except Exception as e:
                logger.error(
                    f"❌ Entschlüsselung fehlgeschlagen für RawEmail {raw_email.id}: {e}"
                )
                continue

            subject_preview = (decrypted_subject or "(ohne Betreff)")[:50]
            
            # ═══════════════════════════════════════════════════════════════════════
            # SCHRITT 0: HTML→PLAIN-TEXT KONVERTIERUNG (vor allem anderen!)
            # ═══════════════════════════════════════════════════════════════════════
            # WICHTIG: Muss VOR Language Detection laufen, sonst HTML-Schrott!
            plain_body = decrypted_body
            if decrypted_body and ('<html' in decrypted_body.lower() or '<body' in decrypted_body.lower()):
                try:
                    logger.info("🔍 HTML im Body erkannt, starte Konvertierung...")
                    logger.info(f"📄 decrypted_body (raw, first 500 chars):\n{repr(decrypted_body[:500])}\n")
                    import inscriptis
                    from inscriptis.model.config import ParserConfig
                    plain_body = inscriptis.get_text(decrypted_body, ParserConfig(display_links=False))
                    logger.info(
                        f"✅ HTML→Plain Text (inscriptis): {len(decrypted_body)} chars → {len(plain_body)} chars"
                    )
                    logger.info(f"📄 plain_body (after inscriptis, first 500 chars):\n{repr(plain_body[:500])}\n")
                except Exception as html_err:
                    logger.warning(f"⚠️  HTML-Konvertierung fehlgeschlagen: {html_err}, nutze Original")
                    plain_body = decrypted_body
            
            # Phase 27: analysis_body als Alias für Plain Text (wird für alle folgenden Schritte genutzt)
            analysis_body = plain_body
            
            # ═══════════════════════════════════════════════════════════════════════
            # SCHRITT 1: EMBEDDING (falls noch nicht vorhanden)
            # ═══════════════════════════════════════════════════════════════════════
            if not models.EmailProcessingStatus.should_skip_step(
                raw_email.processing_status, 
                models.EmailProcessingStatus.EMBEDDING_DONE
            ):
                current_step = "embedding"
                logger.info(f"🔄 [{idx}/{total_emails}] Schritt 1/4: Embedding für '{subject_preview}'")
                
                # Embedding generieren
                try:
                    semantic_search_mod = importlib.import_module(".semantic_search", "src")
                    embedding_bytes, embedding_model_used, embedding_timestamp = \
                        semantic_search_mod.generate_embedding_for_email(
                            subject=decrypted_subject or "",
                            body=plain_body or "",  # ← PLAIN TEXT statt HTML!
                            ai_client=active_ai,
                            model_name=ai_model
                        )
                    
                    if embedding_bytes:
                        raw_email.email_embedding = embedding_bytes
                        raw_email.embedding_model = embedding_model_used or ai_model
                        raw_email.embedding_generated_at = embedding_timestamp or datetime.now(UTC)
                        raw_email.processing_status = models.EmailProcessingStatus.EMBEDDING_DONE
                        session.flush()  # 🔥 KRITISCH: Zwischenspeichern!
                        logger.info(f"✅ Embedding generiert ({len(embedding_bytes)} bytes)")
                    else:
                        logger.warning(f"⚠️  Kein Embedding generiert, fahre fort ohne Embedding")
                        add_processing_warning(
                            raw_email,
                            code=models.ProcessingWarningCode.EMBEDDING_GENERATION_FAILED.value,
                            step="embedding",
                            message="No embedding bytes returned"
                        )
                        raw_email.processing_status = models.EmailProcessingStatus.EMBEDDING_DONE
                        session.flush()
                        
                except Exception as emb_err:
                    # Embedding-Fehler sind nicht mehr fatal - fahre ohne Embedding fort
                    logger.warning(f"⚠️ Embedding-Fehler für Email {raw_email.id}: {emb_err}")
                    add_processing_warning(
                        raw_email,
                        code=models.ProcessingWarningCode.EMBEDDING_MODEL_UNAVAILABLE.value,
                        step="embedding",
                        message=str(emb_err)
                    )
                    raw_email.processing_status = models.EmailProcessingStatus.EMBEDDING_DONE
                    session.flush()
                    # ⚡ Verarbeitung läuft weiter - Semantic Search funktioniert nur nicht
            
            # ═══════════════════════════════════════════════════════════════════════
            # SCHRITT 2: TRANSLATION (falls Sprache != de und noch nicht übersetzt)
            # ═══════════════════════════════════════════════════════════════════════
            # WICHTIG: Translation muss auch nachgeholt werden wenn Status > 20 aber Translation fehlt!
            
            # Sprache erkennen falls noch nicht gesetzt (z.B. nach Reset oder alten Mails)
            if not raw_email.detected_language:
                try:
                    translator_mod = importlib.import_module(".services.translator_service", "src")
                    translator = translator_mod.get_translator()
                    
                    # PLAIN TEXT für bessere Detection (HTML würde Confidence zerstören!)
                    detection = translator.detect_language(f"{decrypted_subject or ''}\n{plain_body[:1500]}")
                    raw_email.detected_language = detection.language
                    logger.info(f"🌍 Language detected: {detection.language} ({detection.confidence:.2f})")
                    
                    # Warning bei niedriger Confidence (< 0.80 = unsicher)
                    if detection.confidence < 0.80:
                        add_processing_warning(
                            raw_email,
                            code=models.ProcessingWarningCode.LANGUAGE_DETECTION_LOW_CONFIDENCE.value,
                            step="language_detection",
                            message=f"Low confidence: {detection.confidence:.2f}",
                            language=detection.language,
                            confidence=detection.confidence
                        )
                        logger.warning(
                            f"⚠️ Language detection low confidence: {detection.language} ({detection.confidence:.2f})"
                        )
                        
                except Exception as e:
                    logger.warning(f"Language detection failed: {e}, assume 'de'")
                    raw_email.detected_language = 'de'
                    add_processing_warning(
                        raw_email,
                        code=models.ProcessingWarningCode.LANGUAGE_DETECTION_FAILED.value,
                        step="language_detection",
                        message=str(e)
                    )
            
            needs_translation = (
                raw_email.detected_language and 
                raw_email.detected_language != 'de' and 
                not raw_email.encrypted_translation_de
            )
            
            if needs_translation or not models.EmailProcessingStatus.should_skip_step(
                raw_email.processing_status,
                models.EmailProcessingStatus.TRANSLATION_DONE
            ):
                current_step = "translation"
                logger.info(f"🔄 [{idx}/{total_emails}] Schritt 2/4: Translation Check")
                
                try:
                    # Translation nur wenn detected_language != 'de' UND noch nicht vorhanden
                    if needs_translation:
                        translator_mod = importlib.import_module(".services.translator_service", "src")
                        translator = translator_mod.get_translator()
                        
                        # Performance-Limit für sehr lange Emails (z.B. Newsletter)
                        # Erhöht auf 5000 wegen trailing spaces in inscriptis output
                        MAX_TRANSLATION_CHARS = 5000
                        full_text = f"{decrypted_subject or ''}\n\n{plain_body}"
                        
                        if len(full_text) <= MAX_TRANSLATION_CHARS:
                            text_to_translate = full_text
                            logger.info(f"🔤 Translation Input (komplett): {len(text_to_translate)} Zeichen")
                        else:
                            text_to_translate = full_text[:MAX_TRANSLATION_CHARS]
                            logger.info(f"🔤 Translation Input (begrenzt): {len(text_to_translate)}/{len(full_text)} Zeichen")
                        
                        result = translator.translate_sync(
                            text=text_to_translate,
                            target_lang='de',
                            source_lang=raw_email.detected_language,
                            engine='local'  # Opus-MT
                        )
                        logger.info(f"✅ Translation Output: {len(result.translated_text)} Zeichen")
                        
                        # Verschlüsseln der Übersetzung
                        raw_email.encrypted_translation_de = encryption_mod.EncryptionManager.encrypt_data(
                            result.translated_text, master_key
                        )
                        raw_email.translation_engine = result.model_used
                        logger.info(f"✅ Translation {raw_email.detected_language}→de ({result.model_used})")
                    else:
                        logger.debug(f"⏭️  Keine Translation nötig (Sprache: {raw_email.detected_language or 'de'})")
                    
                    # Status nur setzen wenn nicht schon höher
                    if raw_email.processing_status < models.EmailProcessingStatus.TRANSLATION_DONE:
                        raw_email.processing_status = models.EmailProcessingStatus.TRANSLATION_DONE
                    session.flush()
                    
                except Exception as trans_err:
                    # ⚠️ WICHTIG: Translation-Fehler nicht mehr fatal!
                    # Verarbeitung wird fortgesetzt, Fehler wird nur geloggt
                    logger.warning(
                        f"⚠️ Translation fehlgeschlagen für Email {raw_email.id} "
                        f"(Sprache: {raw_email.detected_language}): {trans_err}"
                    )
                    
                    # Warnung in processing_warnings speichern (nicht processing_error!)
                    add_processing_warning(
                        raw_email,
                        code=models.ProcessingWarningCode.TRANSLATION_MODEL_UNAVAILABLE.value,
                        step="translation",
                        message=str(trans_err),
                        language=raw_email.detected_language,
                        target_language="de"
                    )
                    
                    # Status trotzdem auf TRANSLATION_DONE setzen (übersprungen)
                    if raw_email.processing_status < models.EmailProcessingStatus.TRANSLATION_DONE:
                        raw_email.processing_status = models.EmailProcessingStatus.TRANSLATION_DONE
                    session.flush()
                    # ⚡ Verarbeitung wird NICHT abgebrochen - AI-Klassifizierung folgt!
            
            # ═══════════════════════════════════════════════════════════════════════
            # SCHRITT 3: AI-KLASSIFIZIERUNG (nur wenn noch kein ProcessedEmail)
            # ═══════════════════════════════════════════════════════════════════════
            if not models.EmailProcessingStatus.should_skip_step(
                raw_email.processing_status,
                models.EmailProcessingStatus.AI_CLASSIFIED
            ):
                current_step = "ai_classification"
                logger.info(f"🔄 [{idx}/{total_emails}] Schritt 3/4: AI-Klassifizierung")
                
                # Ab hier beginnt die original AI-Klassifizierungs-Logik
                clean_body = sanitizer_mod.sanitize_email(decrypted_body, level=level)

                if progress_callback:
                    progress_callback(idx, total_emails, subject_preview)

                # Phase E: Build thread context for AI
                thread_context = build_thread_context(session, raw_email, master_key)
                sender_hint = get_sender_hint_from_patterns(session, raw_email, master_key)
            
                # Combine context and hint
                context_str = ""
                if thread_context:
                    context_str += thread_context + "\n\n"
                if sender_hint:
                    context_str += sender_hint + "\n\n"
            
                # Add current email attachment info
                if raw_email.has_attachments:
                    context_str += "📎 CURRENT EMAIL: This email has attachments.\n\n"
            
                # Bug #4: Improved logging with char counts
                if context_str:
                    logger.info(
                        f"📧 Thread-Context: {len(thread_context) if thread_context else 0} chars, "
                        f"Sender-Hint: {len(sender_hint) if sender_hint else 0} chars"
                    )

                # ===== ANALYSE-MODUS ERKENNUNG =====
                # Account-Settings laden
                enable_ai_analysis = True  # default (legacy)
                account_booster_enabled = True  # default (legacy)
                effective_mode = "llm_original"  # default
                should_anonymize = False  # Anonymisierung ist unabhängig vom Analyse-Modus
            
                # 🛡️ KRITISCH: Cloud-Provider MÜSSEN immer anonymisierte Daten erhalten!
                # Unabhängig von Account-Einstellungen (GDPR/Datenschutz)
                is_cloud_provider = ai_provider in ["openai", "anthropic", "google"]
                if is_cloud_provider:
                    should_anonymize = True
                    logger.info(f"🛡️ Cloud-Provider '{ai_provider}' erkannt → Anonymisierung erzwungen")
            
                try:
                    models_mod = importlib.import_module(".02_models", "src")
                    account = session.query(models_mod.MailAccount).filter_by(id=raw_email.mail_account_id).first()
                    if account:
                        # Legacy-Support
                        enable_ai_analysis = account.enable_ai_analysis_on_fetch
                        account_booster_enabled = account.urgency_booster_enabled
                    
                        # Effektiven Modus berechnen
                        effective_mode = account.effective_ai_mode
                    
                        # Account-Setting kann Anonymisierung zusätzlich aktivieren (z.B. für lokale AI)
                        # ABER: Cloud-Provider überschreibt IMMER (bereits oben gesetzt)
                        if not is_cloud_provider:
                            should_anonymize = account.anonymize_with_spacy
                    
                        logger.info(f"📧 Account '{account.name}': mode={effective_mode}, anonymize={should_anonymize}, cloud={is_cloud_provider}")
                except Exception as e:
                    logger.debug(f"Failed to fetch account settings: {e}")
            
                # ===== HTML→PLAIN TEXT BEREITS IN SCHRITT 0 ERLEDIGT! =====
                # plain_body ist bereits konvertiert, keine doppelte Arbeit mehr!
                
                # ===== ANONYMISIERUNG (UNABHÄNGIG) =====
                # Anonymisierung läuft parallel zur Analyse (erzeugt Tab-Content)
                sanitized_subject = None
                sanitized_body = None
            
                if should_anonymize:
                    try:
                        from src.services.content_sanitizer import get_sanitizer
                        sanitizer = get_sanitizer()
                    
                        logger.info("🛡️ Anonymisiere Inhalte (unabhängig vom Analyse-Modus)...")
                        sanitization_result = sanitizer.sanitize(
                            subject=decrypted_subject or "",
                            body=plain_body,  # ✅ Nutze CACHED plain_body!
                            level=3  # Full spaCy (PER + ORG + GPE + LOC)
                        )
                    
                        # Speichere anonymisierte Version (für Tab + AI-Anon)
                        sanitized_subject = sanitization_result.subject
                        sanitized_body = sanitization_result.body
                    
                        try:
                            encryption_mod = importlib.import_module(".08_encryption", "src")
                            raw_email.encrypted_subject_sanitized = \
                                encryption_mod.EmailDataManager.encrypt_email_subject(
                                    sanitized_subject, master_key
                                )
                            raw_email.encrypted_body_sanitized = \
                                encryption_mod.EmailDataManager.encrypt_email_body(
                                    sanitized_body, master_key
                                )
                            raw_email.sanitization_level = sanitization_result.level
                            raw_email.sanitization_time_ms = sanitization_result.processing_time_ms
                            raw_email.sanitization_entities_count = sanitization_result.entities_found
                        
                            # 🆕 EntityMap für De-Anonymisierung speichern
                            import json
                            entity_map_dict = sanitization_result.entity_map.to_dict()
                            raw_email.encrypted_entity_map = \
                                encryption_mod.EncryptionManager.encrypt_data(
                                    json.dumps(entity_map_dict), master_key
                                )
                        
                            logger.info(
                                f"✅ Anonymisierung: {sanitization_result.entities_found} entities "
                                f"in {sanitization_result.processing_time_ms:.1f}ms"
                            )
                            
                            # Warning wenn Text zu lang war und truncated wurde
                            MAX_SPACY_CHARS = 50000
                            if len(analysis_body) > MAX_SPACY_CHARS:
                                add_processing_warning(
                                    raw_email,
                                    code=models.ProcessingWarningCode.ANONYMIZATION_TEXT_TRUNCATED.value,
                                    step="anonymization",
                                    message=f"Text truncated from {len(analysis_body)} to {MAX_SPACY_CHARS} chars",
                                    original_length=len(analysis_body),
                                    truncated_length=MAX_SPACY_CHARS
                                )
                                
                        except Exception as e:
                            logger.error(f"❌ Fehler beim Speichern der Anonymisierung: {e}")
                            sanitized_subject = None
                            sanitized_body = None
                        
                    except ImportError as e:
                        logger.error(f"❌ ContentSanitizer nicht verfügbar: {e}")
                        add_processing_warning(
                            raw_email,
                            code=models.ProcessingWarningCode.ANONYMIZATION_PARTIAL_FAILURE.value,
                            step="anonymization",
                            message=f"ContentSanitizer not available: {str(e)}"
                        )
                        sanitized_subject = None
                        sanitized_body = None
                    except Exception as e:
                        logger.error(f"❌ Anonymisierung fehlgeschlagen: {e}")
                        add_processing_warning(
                            raw_email,
                            code=models.ProcessingWarningCode.ANONYMIZATION_PARTIAL_FAILURE.value,
                            step="anonymization",
                            message=str(e)
                        )
                        sanitized_subject = None
                        sanitized_body = None
            
                # ===== ANALYSE-MODUS AUSFÜHREN =====
                # Nutze cached plain_body (bereits oben konvertiert!)
            
                try:
                    if effective_mode == "none":
                        logger.info("⏭️  Keine Analyse (alle Toggles aus)")
                        ai_result = None
                    
                    elif effective_mode == "spacy_booster":
                        # Booster nutzt IMMER Original-Daten (lokal = sicher, beste Ergebnisse)
                        # HINWEIS: Booster ist konzeptionell NUR für lokale spaCy gedacht, nicht Cloud
                        if is_cloud_provider:
                            logger.warning("⚠️ spacy_booster mit Cloud-Provider - ungewöhnliche Konfiguration, nutze lokale Booster-Logik")
                        logger.info("⚡ Urgency Booster auf Original-Daten")
                        ai_result = active_ai.analyze_email(
                            subject=decrypted_subject or "",
                            body=analysis_body,  # ← Jetzt Plain Text statt HTML!
                            sender=decrypted_sender or "",
                            language="de",
                            context=context_str if context_str else None,
                            user_id=raw_email.user_id,
                            account_id=raw_email.mail_account_id,
                            db=session,
                            user_enabled_booster=True
                        )
                    
                    elif effective_mode == "llm_original":
                        # AI nutzt Original-Daten (keine Anonymisierung) - NUR für lokale AI!
                        # 🛡️ KRITISCH: Cloud-Provider MÜSSEN anonymisierte Daten nutzen!
                        if is_cloud_provider and sanitized_subject and sanitized_body:
                            logger.info("🛡️ LLM auf anonymisierte Daten (Cloud-Provider erzwingt Anonymisierung)")
                            ai_result = active_ai.analyze_email(
                                subject=sanitized_subject,
                                body=sanitized_body,
                                sender="[SENDER]",  # Auch Sender pseudonymisieren
                                language="de",
                                context=context_str if context_str else None,
                                user_id=raw_email.user_id,
                                account_id=raw_email.mail_account_id,
                                db=session,
                                user_enabled_booster=False
                            )
                            if ai_result:
                                ai_result["_used_anonymized"] = True
                        elif is_cloud_provider:
                            # Cloud-Provider aber keine Anonymisierung verfügbar → FEHLER, nicht senden!
                            logger.error("❌ Cloud-Provider ohne anonymisierte Daten - Analyse übersprungen (Datenschutz)")
                            ai_result = None
                        else:
                            # Lokale AI: Original-Daten sind sicher
                            logger.info("🤖 LLM auf Original-Daten (lokale AI)")
                            ai_result = active_ai.analyze_email(
                                subject=decrypted_subject or "",
                                body=analysis_body,  # ← Jetzt Plain Text statt HTML!
                                sender=decrypted_sender or "",
                                language="de",
                                context=context_str if context_str else None,
                                user_id=raw_email.user_id,
                                account_id=raw_email.mail_account_id,
                                db=session,
                                user_enabled_booster=False
                            )
                    
                    elif effective_mode == "llm_anon":
                        # AI nutzt anonymisierte Daten (Datenschutz für Cloud-LLMs)
                        if sanitized_subject and sanitized_body:
                            logger.info("🛡️ LLM auf anonymisierte Daten")
                            ai_result = active_ai.analyze_email(
                                subject=sanitized_subject,
                                body=sanitized_body,
                                sender="[SENDER]",  # Auch Sender pseudonymisieren
                                language="de",
                                context=context_str if context_str else None,
                                user_id=raw_email.user_id,
                                account_id=raw_email.mail_account_id,
                                db=session,
                                user_enabled_booster=False
                            )
                        
                            if ai_result:
                                ai_result["_used_anonymized"] = True
                        else:
                            # 🛡️ KRITISCH: Cloud-Provider ohne Anonymisierung → NICHT auf Original fallen!
                            if is_cloud_provider:
                                logger.error("❌ AI-Anon gewählt + Cloud-Provider, aber keine anonymisierten Daten → Analyse übersprungen (Datenschutz)")
                                ai_result = None
                            else:
                                # Lokale AI: Fallback auf Original ist sicher
                                logger.warning("⚠️ AI-Anon gewählt, aber keine anonymisierten Daten → Fallback auf Original (lokale AI)")
                                ai_result = active_ai.analyze_email(
                                    subject=decrypted_subject or "",
                                    body=analysis_body,  # ← Konsistent: Plain Text statt HTML
                                    sender=decrypted_sender or "",
                                    language="de",
                                    context=context_str if context_str else None,
                                    user_id=raw_email.user_id,
                                    account_id=raw_email.mail_account_id,
                                    db=session,
                                    user_enabled_booster=False
                                )
                
                    else:
                        logger.warning(f"⚠️ Unbekannter effective_mode: {effective_mode}, Fallback auf keine Analyse")
                        ai_result = None
                        
                except Exception as ai_err:
                    logger.error(f"❌ AI-Analyse fehlgeschlagen: {ai_err}")
                    add_processing_warning(
                        raw_email,
                        code=models.ProcessingWarningCode.AI_CLASSIFICATION_MODEL_UNAVAILABLE.value,
                        step="ai_classification",
                        message=str(ai_err),
                        provider=ai_provider,
                        model=ai_model
                    )
                    ai_result = None
            
                # Phase 11d: Sender-Pattern-Hinweis anwenden (wenn vorhanden) - nur wenn AI-Analyse durchgeführt wurde
                if ai_result:
                    try:
                        sender_patterns_mod = importlib.import_module(".services.sender_patterns", "src")
                        classification_hint = sender_patterns_mod.SenderPatternManager.get_classification_hint(
                            db=session,
                            user_id=raw_email.user_id,
                            sender=decrypted_sender or "",
                            min_confidence=70,  # Nur bei hoher Konfidenz überschreiben
                            min_emails=3
                        )
                        if classification_hint:
                            # Bei hoher Konfidenz: Sender-Pattern überschreibt AI
                            if classification_hint.get("category"):
                                ai_result["kategorie_aktion"] = classification_hint["category"]
                            if classification_hint.get("priority"):
                                ai_result["dringlichkeit"] = classification_hint["priority"]
                            if classification_hint.get("is_newsletter") is not None:
                                ai_result["spam_flag"] = classification_hint["is_newsletter"]
                            logger.debug(f"📊 Sender-Pattern angewandt (confidence={classification_hint['confidence']})")
                    except Exception as e:
                        # Sender-Patterns sind optional
                        logger.debug(f"Sender-Pattern Lookup übersprungen: {e}")
            
                # ===== PHASE 22: OPTIONAL SANITIZATION (unabhängig von AI-Modus) =====
                # Wenn anonymize_with_spacy aktiv ist, speichere IMMER auch sanitized version
                # (auch wenn AI auf Original läuft - für späteren Export/Archiv)
                if account and account.anonymize_with_spacy and effective_mode != "llm_anon":
                    try:
                        from src.services.content_sanitizer import get_sanitizer
                        sanitizer = get_sanitizer()
                    
                        sanitization_result = sanitizer.sanitize(
                            subject=decrypted_subject or "",
                            body=decrypted_body,  # ✅ Original HTML - wie im "Gerendert" Tab!
                            level=3
                        )
                    
                        encryption_mod = importlib.import_module(".08_encryption", "src")
                        raw_email.encrypted_subject_sanitized = \
                            encryption_mod.EmailDataManager.encrypt_email_subject(
                                sanitization_result.subject, master_key
                            )
                        raw_email.encrypted_body_sanitized = \
                            encryption_mod.EmailDataManager.encrypt_email_body(
                                sanitization_result.body, master_key
                            )
                        raw_email.sanitization_level = sanitization_result.level
                        raw_email.sanitization_time_ms = sanitization_result.processing_time_ms
                        raw_email.sanitization_entities_count = sanitization_result.entities_found
                    
                        # 🆕 EntityMap für De-Anonymisierung speichern
                        import json
                        entity_map_dict = sanitization_result.entity_map.to_dict()
                        raw_email.encrypted_entity_map = \
                            encryption_mod.EncryptionManager.encrypt_data(
                                json.dumps(entity_map_dict), master_key
                            )
                    
                        logger.debug(
                            f"🔐 Background-Sanitization: {sanitization_result.entities_found} entities"
                        )
                    except Exception as e:
                        logger.debug(f"Background-Sanitization übersprungen: {e}")
            
                # Provider/Model Tracking: Prüfe ob UrgencyBooster oder LLM verwendet wurde
                actual_provider = None
                actual_model = None
                analysis_method = None
            
                if ai_result:
                    if ai_result.get("_used_booster"):
                        # UrgencyBooster (spaCy) hat die Email verarbeitet
                        actual_provider = "urgency_booster"
                        actual_model = "spacy:de_core_news_sm"
                    
                        # Unterscheide zwischen Hybrid und Legacy Booster
                        if ai_result.get("_used_hybrid_booster"):
                            analysis_method = "hybrid_booster"
                        else:
                            analysis_method = "spacy_booster"
                
                    elif ai_result.get("_used_anonymized"):
                        actual_provider = ai_provider
                        actual_model = ai_model
                        analysis_method = f"llm_anon:{ai_provider}"
                
                    else:
                        # Normales LLM hat die Email verarbeitet
                        actual_provider = ai_provider
                        actual_model = ai_model
                        analysis_method = f"llm:{ai_provider}"
                else:
                    analysis_method = "none"
            
                # Sender-Pattern auch für AI-Klassifizierung aktualisieren (niedriges Gewicht) - nur wenn AI-Analyse durchgeführt wurde
                if ai_result:
                    try:
                        sender_patterns_mod = importlib.import_module(".services.sender_patterns", "src")
                        sender_patterns_mod.SenderPatternManager.update_from_classification(
                            db=session,
                            user_id=raw_email.user_id,
                            sender=decrypted_sender or "",
                            category=ai_result.get("kategorie_aktion"),
                            priority=ai_result.get("dringlichkeit"),
                            is_newsletter=ai_result.get("spam_flag"),
                            is_correction=False  # AI-Klassifizierung hat geringeres Gewicht
                        )
                    except Exception as e:
                        logger.debug(f"Sender-Pattern Update übersprungen: {e}")

                # If AI analysis was skipped, use default values
                if ai_result is None:
                    ai_result = {
                        "dringlichkeit": 1,  # Default: Niedrig
                        "wichtigkeit": 1,    # Default: Niedrig
                        "kategorie_aktion": "Sonstiges",
                        "spam_flag": False,
                        "summary_de": "",
                        "text_de": "",
                        "tags": [],
                        "suggested_tags": []
                    }

                priority = scoring.analyze_priority(
                    dringlichkeit=ai_result["dringlichkeit"],
                    wichtigkeit=ai_result["wichtigkeit"],
                )

                imap_flags_parser = imap_flags_mod.IMAPFlagParser()

                # Zero-Knowledge: Verschlüssele KI-generierte Inhalte
                try:
                    encryption_mod = importlib.import_module(".08_encryption", "src")
                    encrypted_summary = encryption_mod.EmailDataManager.encrypt_summary(
                        ai_result["summary_de"], master_key
                    )
                    encrypted_text = encryption_mod.EmailDataManager.encrypt_summary(
                        ai_result["text_de"], master_key
                    )
                    encrypted_tags = encryption_mod.EmailDataManager.encrypt_summary(
                        ",".join(ai_result.get("tags", [])), master_key
                    )
                except Exception as e:
                    logger.error(
                        f"❌ Verschlüsselung fehlgeschlagen für ProcessedEmail: {e}"
                    )
                    continue

                # WARN-002-FIX: Nutze neue Boolean-Flags direkt (200-300% schneller)
                # Falls Boolean-Flags fehlen (Altdaten), Fallback zu String-Parsing
                was_seen = raw_email.imap_is_seen if raw_email.imap_is_seen is not None else (
                    imap_flags_parser.is_seen(raw_email.imap_flags or "")
                )
                was_answered = raw_email.imap_is_answered if raw_email.imap_is_answered is not None else (
                    imap_flags_parser.is_answered(raw_email.imap_flags or "")
                )
            
                # Extract confidence from AI result if available
                ai_confidence = ai_result.get("_phase_y_confidence") if ai_result else None

                processed_email = models.ProcessedEmail(
                    raw_email_id=raw_email.id,
                    dringlichkeit=ai_result["dringlichkeit"],
                    wichtigkeit=ai_result["wichtigkeit"],
                    kategorie_aktion=ai_result["kategorie_aktion"],
                    encrypted_tags=encrypted_tags,
                    spam_flag=ai_result["spam_flag"],
                    encrypted_summary_de=encrypted_summary,
                    encrypted_text_de=encrypted_text,
                    score=priority["score"],
                    matrix_x=priority["matrix_x"],
                    matrix_y=priority["matrix_y"],
                    farbe=priority["farbe"],
                    done=False,
                    base_provider=actual_provider,
                    base_model=actual_model,
                    analysis_method=analysis_method,
                    ai_confidence=ai_confidence,
                    imap_flags_at_processing=raw_email.imap_flags,  # Audit-Trail
                    was_seen_at_processing=was_seen,  # Optimiert!
                    was_answered_at_processing=was_answered,  # Optimiert!
                )

                # 🐛 BUG-002 FIX: Transaction-Management mit try-except-rollback
                # Per-Email Commit Pattern: Jede Email wird sofort committed (bessere Concurrency)
                try:
                    session.add(processed_email)
                
                    # 🐛 Race-Condition Fix: Flush sofort um UniqueViolation früh zu erkennen
                    try:
                        session.flush()
                    except Exception as flush_err:
                        err_str = str(flush_err).lower()
                        err_type = str(type(flush_err).__name__)
                        # Erkenne alle Varianten von Duplicate-Key-Errors
                        if ("uniqueviolation" in err_type.lower() or 
                            "integrityerror" in err_type.lower() or
                            "duplicate key" in err_str or 
                            "unique constraint" in err_str or
                            "already exists" in err_str):
                            logger.info(f"⏭️  RawEmail {raw_email.id} wurde parallel verarbeitet – markiere als erledigt")
                            # Rollback vorheriger Transaktion und setze RawEmail-Status auf AI_CLASSIFIED
                            session.rollback()
                            try:
                                raw_email.processing_status = models.EmailProcessingStatus.AI_CLASSIFIED
                                raw_email.processing_last_attempt_at = datetime.now(UTC)
                                if hasattr(raw_email, 'processing_retry_count'):
                                    raw_email.processing_retry_count = 0
                                if hasattr(raw_email, 'retry_count'):
                                    raw_email.retry_count = 0
                                session.commit()
                            except Exception as status_err:
                                # Wenn sogar das Setzen des Status fehlschlägt, loggen und safe-abbrechen
                                session.rollback()
                                logger.error(
                                    f"❌ Konnte RawEmail {raw_email.id} nicht auf AI_CLASSIFIED setzen: {status_err}"
                                )
                            continue
                        # Unbekannter Fehler - rollback und re-raise
                        session.rollback()
                        raise
                
                    # Phase 10: Auto-assign suggested_tags from AI
                    # GEÄNDERT 2026-01-05: Nur existierende Tags zuweisen, keine Auto-Creation
                    # GEÄNDERT 2026-01-05: AI-Vorschläge gehen optional in Queue statt zu werden ignoriert
                    # Siehe: doc/offen/PATCH_DISABLE_TAG_AUTO_CREATION.md
                    suggested_tags = ai_result.get("suggested_tags", [])
                    if suggested_tags and isinstance(suggested_tags, list):
                        try:
                            tag_manager_mod = importlib.import_module(".services.tag_manager", "src")
                            suggestion_mod = importlib.import_module(".services.tag_suggestion_service", "src")
                        
                            # processed_email.id ist jetzt verfügbar (nach flush oben)
                        
                            for tag_name in suggested_tags[:5]:  # Max 5 Tags
                                if not tag_name or not isinstance(tag_name, str):
                                    continue
                            
                                tag_name = tag_name.strip()[:50]  # Max 50 chars
                                if not tag_name:
                                    continue
                            
                                try:
                                    # NEU: Nur existierende Tags verwenden, NICHT erstellen
                                    tag = tag_manager_mod.TagManager.get_tag_by_name(
                                        db=session,
                                        user_id=user.id,
                                        name=tag_name
                                    )
                                
                                    if tag:
                                        # Tag existiert → zuweisen
                                        tag_manager_mod.TagManager.assign_tag(
                                            db=session,
                                            email_id=processed_email.id,
                                            tag_id=tag.id,
                                            user_id=user.id
                                        )
                                        logger.debug(f"📌 Tag '{tag_name}' assigned to email {processed_email.id}")
                                    else:
                                        # Tag existiert nicht → zur Queue hinzufügen (falls aktiviert)
                                        if user.enable_tag_suggestion_queue:
                                            suggestion_mod.TagSuggestionService.add_to_queue(
                                                db=session,
                                                user_id=user.id,
                                                suggested_name=tag_name,
                                                source_email_id=processed_email.id
                                            )
                                            logger.info(f"📥 AI suggested tag '{tag_name}' added to queue (email {processed_email.id})")
                                        else:
                                            # Queue deaktiviert → nur loggen
                                            logger.info(f"💡 AI suggested tag '{tag_name}' - nicht vorhanden, übersprungen (email {processed_email.id})")
                                    
                                except Exception as tag_err:
                                    logger.warning(f"⚠️  Tag-Assignment/Queue fehlgeschlagen für '{tag_name}': {tag_err}")
                                
                        except Exception as e:
                            logger.warning(f"⚠️  Tag-Manager/Suggestion nicht verfügbar oder Fehler: {e}")
                
                    # Phase F.2: Smart Tag Auto-Suggestions basierend auf Email-Embeddings
                    if raw_email.email_embedding:
                        try:
                            tag_manager_mod = importlib.import_module(".services.tag_manager", "src")
                        
                            # Bereits zugewiesene Tags holen (um Duplikate zu vermeiden)
                            session.flush()  # Ensure processed_email.id is available
                            already_assigned_tag_ids = [
                                assignment.tag_id 
                                for assignment in session.query(models.EmailTagAssignment)
                                .filter_by(email_id=processed_email.id).all()
                            ]
                        
                            # Phase F.2 Enhanced: Tag-Suggestions mit dynamischen Thresholds
                            # min_similarity=None → Nutzt dynamischen Threshold basierend auf Tag-Anzahl (70-80%)
                            tag_suggestions = tag_manager_mod.TagManager.suggest_tags_by_email_embedding(
                                db=session,
                                user_id=user.id,
                                email_embedding_bytes=raw_email.email_embedding,
                                top_k=5,
                                min_similarity=None,  # Dynamisch: 70% bei <= 5 Tags, 75% bei 6-15, 80% bei >= 16
                                exclude_tag_ids=already_assigned_tag_ids
                            )
                        
                            # Auto-Assignment vs. Manuelle Vorschläge:
                            # >= 80% (AUTO_ASSIGN_SIMILARITY_THRESHOLD) → Auto-assign
                            # 70-79% (get_suggestion_threshold) → Nur Vorschlag für UI
                            auto_assigned_count = 0
                            manual_suggestions = []
                        
                            # Import der Threshold-Konstante
                            AUTO_ASSIGN_THRESHOLD = tag_manager_mod.AUTO_ASSIGN_SIMILARITY_THRESHOLD
                        
                            for tag, similarity in tag_suggestions:
                                if similarity >= AUTO_ASSIGN_THRESHOLD:
                                    # Phase F.3: Separate enable_auto_assignment Flag
                                    # Siehe: doc/offen/REFACTOR_SPLIT_AUTO_ASSIGNMENT_FLAG.md
                                    if user.enable_auto_assignment:
                                        # Auto-Assign für sehr sichere Matches (>= 80%)
                                        try:
                                            tag_manager_mod.TagManager.assign_tag(
                                                db=session,
                                                email_id=processed_email.id,
                                                tag_id=tag.id,
                                                user_id=user.id,
                                                auto_assigned=True  # NEW: Mark as auto-assigned
                                            )
                                            auto_assigned_count += 1
                                            logger.info(
                                                f"⚡ AUTO-ASSIGNED Tag '{tag.name}' ({similarity:.0%} similarity) "
                                                f"to email {processed_email.id}"
                                            )
                                        except Exception as assign_err:
                                            logger.warning(f"⚠️  Auto-assignment fehlgeschlagen für '{tag.name}': {assign_err}")
                                    else:
                                        # User hat Auto-Assignment deaktiviert → Nur als Suggestion zurückgeben
                                        logger.info(
                                            f"💡 SUGGEST: Tag '{tag.name}' ({similarity:.0%}) - "
                                            f"Auto-Assignment disabled (enable_auto_assignment=False)"
                                        )
                                        manual_suggestions.append({
                                            "name": tag.name,
                                            "id": tag.id,
                                            "similarity": round(similarity, 3)
                                        })
                                else:
                                    # Für UI-Suggestions speichern (similarity >= threshold aber < 80%)
                                    manual_suggestions.append({
                                        "name": tag.name,
                                        "id": tag.id,
                                        "similarity": round(similarity, 3)
                                    })
                                    logger.debug(f"💡 Suggested Tag '{tag.name}' ({similarity:.0%}) for manual review")
                        
                            if auto_assigned_count > 0:
                                logger.info(f"✅ Phase F.2: {auto_assigned_count} Tags auto-assigned")
                        
                            if manual_suggestions:
                                # TODO: Suggested_tags könnten in ProcessedEmail.metadata gespeichert werden
                                logger.debug(f"💡 Phase F.2: {len(manual_suggestions)} manual tag suggestions available")
                        
                        except Exception as e:
                            logger.warning(f"⚠️  Phase F.2 Tag-Suggestions fehlgeschlagen: {e}")
                
                    # Per-Email Commit für bessere Concurrency (WAL-Mode erlaubt parallele Reads)
                    session.commit()
                    
                    # Phase 27: Status-Update nach erfolgreichem Schritt 3
                    raw_email.processing_status = models.EmailProcessingStatus.AI_CLASSIFIED
                    raw_email.processing_last_attempt_at = datetime.now(UTC)
                    # Reset retry counter bei Erfolg
                    raw_email.processing_retry_count = 0
                    session.commit()
                    
                    logger.info(
                        "✅ Mail klassifiziert: Score=%s, Farbe=%s",
                        priority["score"],
                        priority["farbe"],
                    )
                
                except Exception as process_err:
                    # 🐛 BUG-002 FIX: Rollback bei Fehler während ProcessedEmail-Erstellung
                    session.rollback()
                    logger.error(f"❌ Fehler bei ProcessedEmail-Erstellung (ID {raw_email.id}): {process_err}")
                    raise  # Re-raise für äußeren Exception-Handler
            
            # HINWEIS: Schritt 4 (AUTO_RULES_APPLIED, Status 50) wird von auto_rules_engine.py gemacht
            # HINWEIS: Finalisierung (COMPLETE, Status 100) wird ebenfalls von auto_rules_engine.py gemacht
            # Diese Pipeline endet bei AI_CLASSIFIED (Status 40)
            
            processed_count += 1
            
        except IntegrityError as integrity_err:
            session.rollback()
            logger.warning(f"⚠️  Mail {raw_email.id} bereits verarbeitet (IntegrityError)")
            
        except Exception as e:
            # PHASE 27: Pipeline Exception Handling mit Error-Mapping
            session.rollback()
            logger.error(f"❌ Fehler bei Email {raw_email.id} (Schritt: {current_step}): {e}")
            
            try:
                # Map Exception zu Status-Code basierend auf Schritt
                error_status = map_exception_to_status(e, current_step)
                raw_email.processing_status = error_status
                raw_email.processing_error = str(e)[:1000]  # Max 1000 chars
                raw_email.processing_last_attempt_at = datetime.now(UTC)
                # Increment retry counter
                raw_email.processing_retry_count = (raw_email.processing_retry_count or 0) + 1
                
                session.commit()
                
                logger.warning(
                    f"⚠️  Status gesetzt auf {error_status} (Retry {raw_email.processing_retry_count}/3)"
                )
                
            except Exception as status_err:
                # Falls auch Status-Update fehlschlägt
                session.rollback()
                logger.error(f"❌ Konnte Status nicht setzen: {status_err}")
            
            # Continue mit nächster Email statt abzubrechen
            continue

    # Alle Emails wurden einzeln committed (Per-Email Commit Pattern)
    logger.info(f"✅ Verarbeitung abgeschlossen: {processed_count} Mails erfolgreich verarbeitet")

    return processed_count


def purge_marked_emails(session, days_to_retain: int = 90) -> dict[str, int]:
    """
    Hard-delete emails marked for deletion after retention period.

    Löscht RawEmails und zugehörige ProcessedEmails, die vor mehr als
    `days_to_retain` Tagen mit deleted_at markiert wurden.
    
    P1-002: Nutzt nur deleted_at (deleted_verm entfernt)

    Args:
        session: SQLAlchemy Session
        days_to_retain: Tage bis zum Hard-Delete (default: 90)

    Returns:
        Dictionary mit Counts: {raw_deleted: int, processed_deleted: int}
    """
    from datetime import datetime, timedelta, UTC

    cutoff_date = datetime.now(UTC) - timedelta(days=days_to_retain)

    try:
        raw_emails_to_delete = (
            session.query(models.RawEmail)
            .filter(
                models.RawEmail.deleted_at.isnot(None),  # P1-002: deleted_verm entfernt
                models.RawEmail.deleted_at < cutoff_date,
            )
            .all()
        )

        if not raw_emails_to_delete:
            logger.info(
                "✅ Keine Emails zum Purge nach %d Tagen vorhanden", days_to_retain
            )
            return {"raw_deleted": 0, "processed_deleted": 0}

        raw_ids = [email.id for email in raw_emails_to_delete]

        processed_count = (
            session.query(models.ProcessedEmail)
            .filter(models.ProcessedEmail.raw_email_id.in_(raw_ids))
            .delete(synchronize_session=False)
        )

        raw_count = (
            session.query(models.RawEmail)
            .filter(models.RawEmail.id.in_(raw_ids))
            .delete(synchronize_session=False)
        )

        session.commit()

        logger.info(
            "🧹 Purge abgeschlossen: %d RawEmails, %d ProcessedEmails gelöscht",
            raw_count,
            processed_count,
        )

        return {"raw_deleted": raw_count, "processed_deleted": processed_count}

    except Exception as exc:
        session.rollback()
        logger.error("❌ Fehler beim Purge: %s", exc, exc_info=True)
        return {"raw_deleted": 0, "processed_deleted": 0}
