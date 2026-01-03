"""
PATCH: 14_background_jobs.py - Semantic Search Integration
===========================================================

Diese Datei zeigt die Änderungen für src/14_background_jobs.py

WICHTIG: Embedding wird generiert BEVOR die Email verschlüsselt wird,
da wir den Klartext brauchen!
"""

# =============================================================================
# IMPORT HINZUFÜGEN (am Anfang der Datei)
# =============================================================================

# Füge hinzu nach den anderen imports:
from src.semantic_search import generate_embedding_for_email


# =============================================================================
# IN _persist_raw_emails() METHODE
# =============================================================================

# VORHER (bestehender Code, ca. Zeile 280-350):
"""
def _persist_raw_emails(
    self, session, user, account, raw_emails: list[Dict], master_key: str
):
    for raw_email_data in raw_emails:
        # ... Verschlüsselung ...
        
        raw_email = models.RawEmail(
            user_id=user.id,
            mail_account_id=account.id,
            encrypted_sender=encrypted_sender,
            encrypted_subject=encrypted_subject,
            encrypted_body=encrypted_body,
            # ... andere Felder ...
        )
        session.add(raw_email)
"""

# NACHHER (mit Embedding-Generierung):

def _persist_raw_emails(
    self, session, user, account, raw_emails: list, master_key: str
):
    """Persist RawEmails mit Embedding-Generierung (Phase 15)"""
    
    # AI-Client für Embeddings (einmal pro Batch)
    embedding_ai_client = None
    try:
        embedding_ai_client = ai_client_mod.LocalOllamaClient(model="all-minilm:22m")
    except Exception as e:
        logger.warning(f"Embedding AI-Client nicht verfügbar: {e}")
    
    for raw_email_data in raw_emails:
        # ════════════════════════════════════════════════════════════════
        # KLARTEXT ist hier noch verfügbar!
        # ════════════════════════════════════════════════════════════════
        subject_plain = raw_email_data.get("subject", "")
        body_plain = raw_email_data.get("body", "")
        sender_plain = raw_email_data.get("sender", "")
        
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
                        ai_client=embedding_ai_client
                    )
                if embedding_bytes:
                    logger.debug(f"Embedding generiert für: {subject_plain[:50]}...")
            except Exception as e:
                logger.warning(f"Embedding-Fehler: {e}")
        
        # ════════════════════════════════════════════════════════════════
        # Verschlüsselung (wie bisher)
        # ════════════════════════════════════════════════════════════════
        encrypted_sender = encryption.EncryptionManager.encrypt_data(
            sender_plain, master_key
        )
        encrypted_subject = encryption.EncryptionManager.encrypt_data(
            subject_plain, master_key
        )
        encrypted_body = encryption.EncryptionManager.encrypt_data(
            body_plain, master_key
        )
        
        # ... weitere Verschlüsselungen (in_reply_to, to, cc, etc.) ...
        
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
        
        # ════════════════════════════════════════════════════════════════
        # RawEmail erstellen (mit Embedding!)
        # ════════════════════════════════════════════════════════════════
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
            
            # Threading (Phase 12)
            message_id=raw_email_data.get("message_id"),
            encrypted_in_reply_to=encrypted_in_reply_to,
            parent_uid=raw_email_data.get("parent_uid"),
            thread_id=raw_email_data.get("thread_id"),
            
            # Boolean Flags (Phase 12)
            imap_is_seen=raw_email_data.get("imap_is_seen"),
            imap_is_answered=raw_email_data.get("imap_is_answered"),
            imap_is_flagged=raw_email_data.get("imap_is_flagged"),
            imap_is_deleted=raw_email_data.get("imap_is_deleted"),
            imap_is_draft=raw_email_data.get("imap_is_draft"),
            
            # Extended Envelope (Phase 12)
            encrypted_to=encrypted_to,
            encrypted_cc=encrypted_cc,
            encrypted_bcc=encrypted_bcc,
            encrypted_reply_to=encrypted_reply_to,
            encrypted_references=encrypted_references,
            
            # Content Metadata (Phase 12)
            message_size=raw_email_data.get("message_size"),
            content_type=raw_email_data.get("content_type"),
            charset=raw_email_data.get("charset"),
            has_attachments=raw_email_data.get("has_attachments", False),
            
            # ════════════════════════════════════════════════════════════
            # NEU: Semantic Search Embedding (Phase 15)
            # ════════════════════════════════════════════════════════════
            email_embedding=embedding_bytes,
            embedding_model=embedding_model,
            embedding_generated_at=embedding_generated_at,
        )
        session.add(raw_email)


# =============================================================================
# AUCH IN 01_web_app.py (manueller Fetch)
# =============================================================================

# Falls ihr auch in 01_web_app.py Emails speichert (z.B. manueller Fetch),
# muss dort dieselbe Logik eingefügt werden.
# 
# Suche nach: raw_email = models.RawEmail(
# Und füge embedding_bytes Generierung VOR der Verschlüsselung hinzu.
