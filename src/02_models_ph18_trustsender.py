class TrustedSender(Base):
    """
    User-definierte vertrauenswürdige Absender (Phase X).
    
    Nur für Emails von diesen Sendern wird UrgencyBooster (spaCy) verwendet.
    Pattern wird normalisiert (lowercase) beim Speichern.
    
    Pattern-Typen:
    - exact: Exakte Email-Adresse (chef@firma.de)
    - email_domain: Alle von Email-Domain (@firma.de)
    - domain: Alle von Domain (firma.de)
    """
    __tablename__ = "trusted_senders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    sender_pattern = Column(String(255), nullable=False)
    """Pattern: "chef@firma.de", "@firma.de", oder "firma.de" - normalisiert zu lowercase"""
    
    pattern_type = Column(String(20), nullable=False)
    """Pattern-Typ: 'exact', 'email_domain', oder 'domain'"""
    
    label = Column(String(100), nullable=True)
    """Optionales Label für UI: "Chef", "Kollegen", "Buchhaltung" """
    
    use_urgency_booster = Column(Boolean, default=True, nullable=False)
    """User kann spaCy pro Sender aktivieren/deaktivieren"""
    
    added_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    email_count = Column(Integer, default=0, nullable=False)
    """Wie viele Emails von diesem Sender wurden gesehen?"""
    
    # Relationship
    user = relationship("User", back_populates="trusted_senders")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'sender_pattern', name='uq_user_sender'),
    )
    
    def __init__(self, **kwargs):
        # Normalisiere Pattern beim Erstellen
        if 'sender_pattern' in kwargs:
            kwargs['sender_pattern'] = kwargs['sender_pattern'].lower().strip()
        super().__init__(**kwargs)
    
    def __repr__(self):
        return f"<TrustedSender(id={self.id}, pattern={self.sender_pattern}, type={self.pattern_type})>"
