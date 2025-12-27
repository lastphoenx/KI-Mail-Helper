"""Shared processing helpers for turning RawEmail entries into ProcessedEmail rows."""

from __future__ import annotations

import logging
import importlib
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError

models = importlib.import_module('.02_models', 'src')
sanitizer_mod = importlib.import_module('.04_sanitizer', 'src')
ai_client_mod = importlib.import_module('.03_ai_client', 'src')
scoring = importlib.import_module('.05_scoring', 'src')
imap_flags_mod = importlib.import_module('.16_imap_flags', 'src')

logger = logging.getLogger(__name__)


def process_pending_raw_emails(
    session,
    user,
    *,
    master_key: Optional[str] = None,
    mail_account: Optional[object] = None,
    limit: Optional[int] = None,
    ai=None,
    sanitize_level: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> int:
    """Process RawEmails without ProcessedEmail entries for the given user.
    
    Args:
        master_key: Master-Key for encryption/decryption. Required for processing emails.
        progress_callback: Optional callback(current_index: int, total: int, subject: str) for each email.
    """
    if not user:
        return 0
    
    if not master_key:
        logger.warning("⚠️  Master-Key nicht verfügbar - kann E-Mails nicht verarbeiten")
        return 0

    level = sanitize_level if sanitize_level is not None else sanitizer_mod.get_sanitization_level(False)

    query = session.query(models.RawEmail).outerjoin(
        models.ProcessedEmail,
        models.RawEmail.id == models.ProcessedEmail.raw_email_id
    ).filter(
        models.RawEmail.user_id == user.id,
        models.ProcessedEmail.id.is_(None),
        models.RawEmail.deleted_at.is_(None),
        models.RawEmail.deleted_verm.is_(False)
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
    if hasattr(active_ai, '__class__'):
        class_name = active_ai.__class__.__name__
        if "OpenAI" in class_name:
            ai_provider = "openai"
        elif "Anthropic" in class_name:
            ai_provider = "anthropic"
        elif "Ollama" in class_name:
            ai_provider = "ollama"
    
    ai_model = getattr(active_ai, 'model', None) or "unknown"

    logger.info(
        "🧾 Verarbeite %d gespeicherte Mails für %s",
        len(pending_emails),
        getattr(mail_account, 'name', user.username)
    )

    processed_count = 0
    total_emails = len(pending_emails)
    
    # Zero-Knowledge: Hole Master-Key für Entschlüsselung
    # Wichtig: Dieser Key muss vom Caller übergeben werden (z.B. aus Flask Session)
    # oder aus user.encrypted_master_key_for_cron entschlüsselt werden
    # Für manuelle Verarbeitung (Web-Request) sollte master_key aus Session kommen

    for idx, raw_email in enumerate(pending_emails, 1):
        try:
            already_processed = session.query(models.ProcessedEmail).filter_by(
                raw_email_id=raw_email.id
            ).first()
            if already_processed:
                logger.info("⏭️  RawEmail %s bereits verarbeitet – überspringe", raw_email.id)
                continue

            # Zero-Knowledge: Entschlüssele E-Mail-Inhalte mit master_key
            try:
                encryption_mod = importlib.import_module('.08_encryption', 'src')
                decrypted_subject = encryption_mod.EmailDataManager.decrypt_email_subject(
                    raw_email.encrypted_subject or "", master_key
                )
                decrypted_body = encryption_mod.EmailDataManager.decrypt_email_body(
                    raw_email.encrypted_body or "", master_key
                )
                decrypted_sender = encryption_mod.EmailDataManager.decrypt_email_sender(
                    raw_email.encrypted_sender or "", master_key
                )
            except Exception as e:
                logger.error(f"❌ Entschlüsselung fehlgeschlagen für RawEmail {raw_email.id}: {e}")
                continue

            subject_preview = (decrypted_subject or "(ohne Betreff)")[:50]
            clean_body = sanitizer_mod.sanitize_email(decrypted_body, level=level)

            if progress_callback:
                progress_callback(idx, total_emails, subject_preview)

            logger.info("🤖 Analysiere gespeicherte Mail: %s...", subject_preview)
            ai_result = active_ai.analyze_email(
                subject=decrypted_subject or "",
                body=clean_body,
                sender=decrypted_sender or ""
            )

            priority = scoring.analyze_priority(
                dringlichkeit=ai_result["dringlichkeit"],
                wichtigkeit=ai_result["wichtigkeit"]
            )

            imap_flags_parser = imap_flags_mod.IMAPFlagParser()
            
            # Zero-Knowledge: Verschlüssele KI-generierte Inhalte
            try:
                encryption_mod = importlib.import_module('.08_encryption', 'src')
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
                logger.error(f"❌ Verschlüsselung fehlgeschlagen für ProcessedEmail: {e}")
                continue
            
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
                imap_flags_at_processing=raw_email.imap_flags,
                was_seen_at_processing=imap_flags_parser.is_seen(raw_email.imap_flags or ''),
                was_answered_at_processing=imap_flags_parser.is_answered(raw_email.imap_flags or '')
            )

            session.add(processed_email)
            # Transaction Fix: Don't commit inside loop - batch commit at end
            processed_count += 1

            logger.info(
                "✅ Mail verarbeitet: Score=%s, Farbe=%s",
                priority["score"],
                priority["farbe"]
            )

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
        raw_emails_to_delete = session.query(models.RawEmail).filter(
            models.RawEmail.deleted_verm == True,
            models.RawEmail.deleted_at < cutoff_date
        ).all()
        
        if not raw_emails_to_delete:
            logger.info("✅ Keine Emails zum Purge nach %d Tagen vorhanden", days_to_retain)
            return {"raw_deleted": 0, "processed_deleted": 0}
        
        raw_ids = [email.id for email in raw_emails_to_delete]
        
        processed_count = session.query(models.ProcessedEmail).filter(
            models.ProcessedEmail.raw_email_id.in_(raw_ids)
        ).delete(synchronize_session=False)
        
        raw_count = session.query(models.RawEmail).filter(
            models.RawEmail.id.in_(raw_ids)
        ).delete(synchronize_session=False)
        
        session.commit()
        
        logger.info(
            "🧹 Purge abgeschlossen: %d RawEmails, %d ProcessedEmails gelöscht",
            raw_count,
            processed_count
        )
        
        return {
            "raw_deleted": raw_count,
            "processed_deleted": processed_count
        }
        
    except Exception as exc:
        session.rollback()
        logger.error("❌ Fehler beim Purge: %s", exc, exc_info=True)
        return {"raw_deleted": 0, "processed_deleted": 0}
