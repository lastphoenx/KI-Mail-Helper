"""
PATCH: 02_models.py - Semantic Search Felder
============================================

Füge diese Felder zur RawEmail Klasse hinzu.
"""

# =============================================================================
# IN class RawEmail(Base):
# =============================================================================

# Suche nach dem Kommentar "# ===== PHASE 12: NICE-TO-HAVE" oder ähnlich
# und füge DANACH hinzu:

    # ===== PHASE 15: SEMANTIC SEARCH =====
    # Embedding für semantische Suche
    # NICHT verschlüsselt! Embeddings sind nicht zu Klartext reversibel.
    # 384 floats × 4 bytes = 1536 bytes pro Email
    email_embedding = Column(LargeBinary, nullable=True)
    
    # Embedding-Metadaten
    embedding_model = Column(String(50), nullable=True)  # "all-minilm:22m"
    embedding_generated_at = Column(DateTime, nullable=True)


# =============================================================================
# VOLLSTÄNDIGES BEISPIEL (RawEmail Klasse mit Phase 15)
# =============================================================================

"""
class RawEmail(Base):
    '''Raw Email Data mit Zero-Knowledge Encryption'''
    
    __tablename__ = "raw_emails"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mail_account_id = Column(
        Integer, ForeignKey("mail_accounts.id"), nullable=False, index=True
    )

    # Zero-Knowledge: Verschlüsselte persönliche Daten
    encrypted_sender = Column(Text, nullable=False)
    encrypted_subject = Column(Text)
    encrypted_body = Column(Text)

    received_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    deleted_at = Column(DateTime, nullable=True)
    deleted_verm = Column(Boolean, default=False)

    # ===== PHASE 14A: RFC-KONFORMER KEY =====
    imap_uid = Column(Integer, nullable=True, index=True)
    imap_folder = Column(String(200), nullable=False, default='INBOX')
    imap_uidvalidity = Column(Integer, nullable=True, index=True)
    imap_flags = Column(String(500), nullable=True)
    imap_last_seen_at = Column(DateTime, nullable=True)

    # ===== PHASE 12: MUST-HAVE (Threading) =====
    message_id = Column(String(255), nullable=True, index=True)
    encrypted_in_reply_to = Column(Text, nullable=True)
    parent_uid = Column(String(255), nullable=True, index=True)
    thread_id = Column(String(36), nullable=True, index=True)

    # Boolean Flags (200-300% faster queries)
    imap_is_seen = Column(Boolean, default=False, nullable=True, index=True)
    imap_is_answered = Column(Boolean, default=False, nullable=True, index=True)
    imap_is_flagged = Column(Boolean, default=False, nullable=True, index=True)
    imap_is_deleted = Column(Boolean, default=False, nullable=True)
    imap_is_draft = Column(Boolean, default=False, nullable=True)

    # ===== PHASE 12: SHOULD-HAVE (Extended Envelope) =====
    encrypted_to = Column(Text, nullable=True)
    encrypted_cc = Column(Text, nullable=True)
    encrypted_bcc = Column(Text, nullable=True)
    encrypted_reply_to = Column(Text, nullable=True)

    # Message Metadata
    message_size = Column(Integer, nullable=True)
    encrypted_references = Column(Text, nullable=True)

    # ===== PHASE 12: NICE-TO-HAVE (Content Info) =====
    content_type = Column(String(100), nullable=True)
    charset = Column(String(50), nullable=True)
    has_attachments = Column(Boolean, default=False, nullable=True)
    last_flag_sync_at = Column(DateTime, nullable=True)

    # ===== PHASE 15: SEMANTIC SEARCH =====
    # Embedding für semantische Suche
    # NICHT verschlüsselt! Embeddings sind nicht zu Klartext reversibel.
    email_embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String(50), nullable=True)  # "all-minilm:22m"
    embedding_generated_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="raw_emails")
    mail_account = relationship("MailAccount", back_populates="raw_emails")
    processed_email = relationship(
        "ProcessedEmail", back_populates="raw_email", uselist=False
    )
    todos = relationship("TodoItem", back_populates="email")  # Phase 15 (optional)
'''
"""
