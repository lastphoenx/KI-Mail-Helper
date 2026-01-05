"""Shared processing helpers for turning RawEmail entries into ProcessedEmail rows."""

from __future__ import annotations

import logging
import importlib
from typing import Callable, Optional, List, Dict
from datetime import datetime

from sqlalchemy.exc import IntegrityError

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
                models.RawEmail.deleted_at.is_(None),
                models.RawEmail.deleted_verm.is_(False)
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
        
        # Limit context size early (before AI sanitization)
        max_context_chars = 4500  # Leave room for current email info
        if len(context_str) > max_context_chars:
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
                models.RawEmail.deleted_at.is_(None),
                models.RawEmail.deleted_verm.is_(False)
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

    query = (
        session.query(models.RawEmail)
        .outerjoin(
            models.ProcessedEmail,
            models.RawEmail.id == models.ProcessedEmail.raw_email_id,
        )
        .filter(
            models.RawEmail.user_id == user.id,
            models.ProcessedEmail.id.is_(None),
            models.RawEmail.deleted_at.is_(None),
            models.RawEmail.deleted_verm.is_(False),
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
        preloaded = tag_manager_mod.TagEmbeddingCache.preload_user_tags(user.id, db)
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
        try:
            already_processed = (
                session.query(models.ProcessedEmail)
                .filter_by(raw_email_id=raw_email.id)
                .first()
            )
            if already_processed:
                logger.info(
                    "⏭️  RawEmail %s bereits verarbeitet – überspringe", raw_email.id
                )
                continue

            # Zero-Knowledge: Entschlüssele E-Mail-Inhalte mit master_key
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

            logger.info("🤖 Analysiere gespeicherte Mail: %s...", subject_preview)
            ai_result = active_ai.analyze_email(
                subject=decrypted_subject or "",
                body=clean_body,
                context=context_str if context_str else None  # Phase E: Pass context to AI
            )
            
            # Phase 11d: Sender-Pattern-Hinweis anwenden (wenn vorhanden)
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
            
            # Sender-Pattern auch für AI-Klassifizierung aktualisieren (niedriges Gewicht)
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
                base_provider=ai_provider,
                base_model=ai_model,
                imap_flags_at_processing=raw_email.imap_flags,  # Audit-Trail
                was_seen_at_processing=was_seen,  # Optimiert!
                was_answered_at_processing=was_answered,  # Optimiert!
            )

            # 🐛 BUG-002 FIX: Transaction-Management mit try-except-rollback
            try:
                session.add(processed_email)
                # Transaction Fix: Don't commit inside loop - batch commit at end
                
                # Phase 10: Auto-assign suggested_tags from AI
                suggested_tags = ai_result.get("suggested_tags", [])
                if suggested_tags and isinstance(suggested_tags, list):
                    try:
                        tag_manager_mod = importlib.import_module(".services.tag_manager", "src")
                        
                        # Muss flushen damit processed_email.id verfügbar ist
                        session.flush()
                        
                        for tag_name in suggested_tags[:5]:  # Max 5 Tags
                            if not tag_name or not isinstance(tag_name, str):
                                continue
                            
                            tag_name = tag_name.strip()[:50]  # Max 50 chars
                            if not tag_name:
                                continue
                            
                            try:
                                # Get or create tag für diesen User
                                tag = tag_manager_mod.TagManager.get_or_create_tag(
                                    db=session,
                                    user_id=user.id,
                                    name=tag_name,
                                    color="#3B82F6"  # Default blue
                                )
                                
                                # Assign tag zu email
                                tag_manager_mod.TagManager.assign_tag(
                                    db=session,
                                    email_id=processed_email.id,
                                    tag_id=tag.id,
                                    user_id=user.id
                                )
                                logger.debug(f"📌 Tag '{tag_name}' assigned to email {processed_email.id}")
                            except Exception as tag_err:
                                logger.warning(f"⚠️  Tag-Assignment fehlgeschlagen für '{tag_name}': {tag_err}")
                                
                    except Exception as e:
                        logger.warning(f"⚠️  Tag-Manager nicht verfügbar oder Fehler: {e}")
                
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
                                # Auto-Assign für sehr sichere Matches (>= 80%)
                                try:
                                    tag_manager_mod.TagManager.assign_tag(
                                        db=session,
                                        email_id=processed_email.id,
                                        tag_id=tag.id,
                                        user_id=user.id
                                    )
                                    auto_assigned_count += 1
                                    logger.info(
                                        f"🏷️  ✅ AUTO-ASSIGNED Tag '{tag.name}' ({similarity:.0%} similarity) "
                                        f"to email {processed_email.id}"
                                    )
                                except Exception as assign_err:
                                    logger.warning(f"⚠️  Auto-assignment fehlgeschlagen für '{tag.name}': {assign_err}")
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
                
                processed_count += 1

                logger.info(
                    "✅ Mail verarbeitet: Score=%s, Farbe=%s",
                    priority["score"],
                    priority["farbe"],
                )
            
            except Exception as process_err:
                # 🐛 BUG-002 FIX: Rollback bei Fehler während session.add()
                session.rollback()
                logger.error(f"❌ Fehler bei Email-Verarbeitung (ID {raw_email.id}): {process_err}")
                # Continue mit nächster Email statt abzubrechen
                continue

        except IntegrityError:
            session.rollback()
            logger.warning("⚠️  Mail bereits verarbeitet (IntegrityError)")
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Fehler bei Verarbeitung: {e}")

    # Commit all processed emails at once (atomic transaction)
    try:
        session.commit()
        logger.info(f"✅ Batch-Commit: {processed_count} Mails erfolgreich verarbeitet")
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Batch-Commit fehlgeschlagen: {e}")
        raise

    return processed_count


def purge_marked_emails(session, days_to_retain: int = 90) -> dict[str, int]:
    """
    Hard-delete emails marked for deletion after retention period.

    Löscht RawEmails und zugehörige ProcessedEmails, die vor mehr als
    `days_to_retain` Tagen mit deleted_verm=True markiert wurden.

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
                models.RawEmail.deleted_verm == True,
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
