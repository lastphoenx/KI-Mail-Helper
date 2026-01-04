"""
Sender-Pattern Service (Phase 11d)

Verwaltet gelernte Muster für Absender-basierte Klassifizierung.
Ermöglicht konsistente Klassifizierung für wiederkehrende Absender.

Privacy: Absenderadressen werden gehasht gespeichert (SHA-256),
sodass keine Klartextadressen in der Datenbank landen.
"""

import hashlib
import logging
from datetime import datetime, UTC
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

try:
    import importlib
    models = importlib.import_module("src.02_models")
except ModuleNotFoundError:
    models = importlib.import_module("02_models")


logger = logging.getLogger(__name__)


class SenderPatternManager:
    """
    Manager für Sender-Patterns.
    
    Lernt aus User-Korrekturen und AI-Klassifizierungen,
    wie E-Mails von bestimmten Absendern typischerweise
    behandelt werden sollen.
    """
    
    @staticmethod
    def _hash_sender(sender: str) -> str:
        """
        Erzeugt einen privacy-preserving Hash des Absenders.
        
        Args:
            sender: E-Mail-Adresse des Absenders
            
        Returns:
            SHA-256 Hash (64 Zeichen hex)
        """
        # Normalisieren: lowercase, whitespace entfernen
        normalized = sender.lower().strip()
        
        # Nur die E-Mail-Adresse extrahieren falls Format "Name <email>"
        if "<" in normalized and ">" in normalized:
            start = normalized.index("<") + 1
            end = normalized.index(">")
            normalized = normalized[start:end].strip()
        
        # SHA-256 Hash
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    @staticmethod
    def get_pattern(
        db: Session,
        user_id: int,
        sender: str
    ) -> Optional[models.SenderPattern]:
        """
        Holt das Pattern für einen Absender (falls vorhanden).
        
        Args:
            db: Database session
            user_id: User ID
            sender: E-Mail-Adresse des Absenders
            
        Returns:
            SenderPattern oder None
        """
        sender_hash = SenderPatternManager._hash_sender(sender)
        
        return db.query(models.SenderPattern).filter(
            models.SenderPattern.user_id == user_id,
            models.SenderPattern.sender_hash == sender_hash
        ).first()
    
    @staticmethod
    def get_classification_hint(
        db: Session,
        user_id: int,
        sender: str,
        min_confidence: int = 60,
        min_emails: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Holt einen Klassifizierungs-Hinweis basierend auf gelernten Patterns.
        
        Nur zurückgeben wenn Konfidenz hoch genug und genug E-Mails gesehen.
        
        Args:
            db: Database session
            user_id: User ID
            sender: E-Mail-Adresse des Absenders
            min_confidence: Minimale Konfidenz (0-100)
            min_emails: Minimale Anzahl E-Mails vom Sender
            
        Returns:
            Dict mit category, priority, is_newsletter, confidence oder None
        """
        pattern = SenderPatternManager.get_pattern(db, user_id, sender)
        
        if not pattern:
            return None
        
        # Prüfe ob genug Daten vorhanden
        if pattern.email_count < min_emails:
            return None
        
        if pattern.confidence < min_confidence:
            return None
        
        return {
            "category": pattern.category,
            "priority": pattern.priority,
            "is_newsletter": pattern.is_newsletter,
            "confidence": pattern.confidence,
            "email_count": pattern.email_count,
            "correction_count": pattern.correction_count
        }
    
    @staticmethod
    def update_from_classification(
        db: Session,
        user_id: int,
        sender: str,
        category: Optional[str] = None,
        priority: Optional[int] = None,
        is_newsletter: Optional[bool] = None,
        is_correction: bool = False
    ) -> models.SenderPattern:
        """
        Aktualisiert oder erstellt ein Sender-Pattern basierend auf
        einer Klassifizierung (AI oder User-Korrektur).
        
        Args:
            db: Database session
            user_id: User ID
            sender: E-Mail-Adresse des Absenders
            category: Kategorie der Klassifizierung
            priority: Priorität (1-10)
            is_newsletter: Newsletter-Flag
            is_correction: True wenn User-Korrektur (erhöht Gewicht)
            
        Returns:
            Aktualisiertes/erstelltes SenderPattern
        """
        sender_hash = SenderPatternManager._hash_sender(sender)
        
        pattern = db.query(models.SenderPattern).filter(
            models.SenderPattern.user_id == user_id,
            models.SenderPattern.sender_hash == sender_hash
        ).first()
        
        if not pattern:
            # Neues Pattern erstellen
            pattern = models.SenderPattern(
                user_id=user_id,
                sender_hash=sender_hash,
                category=category,
                priority=priority,
                is_newsletter=is_newsletter,
                email_count=1,
                correction_count=1 if is_correction else 0,
                confidence=70 if is_correction else 40  # Korrekturen haben mehr Gewicht
            )
            db.add(pattern)
            logger.info(f"Neues Sender-Pattern erstellt: hash={sender_hash[:8]}...")
        else:
            # Bestehendes Pattern aktualisieren
            pattern.email_count += 1
            
            if is_correction:
                pattern.correction_count += 1
                # Korrekturen überschreiben AI-Klassifizierungen
                if category is not None:
                    pattern.category = category
                if priority is not None:
                    pattern.priority = priority
                if is_newsletter is not None:
                    pattern.is_newsletter = is_newsletter
                # Konfidenz erhöhen (max 95)
                pattern.confidence = min(95, pattern.confidence + 10)
            else:
                # AI-Klassifizierung: nur bei niedriger Konfidenz übernehmen
                if pattern.confidence < 50:
                    if category is not None and pattern.category is None:
                        pattern.category = category
                    if priority is not None and pattern.priority is None:
                        pattern.priority = priority
                    if is_newsletter is not None and pattern.is_newsletter is None:
                        pattern.is_newsletter = is_newsletter
                
                # Konfidenz leicht erhöhen bei konsistenter Klassifizierung
                if category == pattern.category:
                    pattern.confidence = min(80, pattern.confidence + 2)
            
            pattern.updated_at = datetime.now(UTC)
            logger.debug(f"Sender-Pattern aktualisiert: hash={sender_hash[:8]}..., count={pattern.email_count}")
        
        db.commit()
        db.refresh(pattern)
        return pattern
    
    @staticmethod
    def get_user_statistics(
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Holt Statistiken über die Sender-Patterns eines Users.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Dict mit total_patterns, high_confidence_count, etc.
        """
        patterns = db.query(models.SenderPattern).filter(
            models.SenderPattern.user_id == user_id
        ).all()
        
        if not patterns:
            return {
                "total_patterns": 0,
                "high_confidence_count": 0,
                "total_emails_tracked": 0,
                "total_corrections": 0,
                "avg_confidence": 0
            }
        
        high_conf = sum(1 for p in patterns if p.confidence >= 70)
        total_emails = sum(p.email_count for p in patterns)
        total_corrections = sum(p.correction_count for p in patterns)
        avg_conf = sum(p.confidence for p in patterns) / len(patterns)
        
        return {
            "total_patterns": len(patterns),
            "high_confidence_count": high_conf,
            "total_emails_tracked": total_emails,
            "total_corrections": total_corrections,
            "avg_confidence": round(avg_conf, 1)
        }
    
    @staticmethod
    def cleanup_old_patterns(
        db: Session,
        user_id: int,
        min_emails: int = 1,
        max_age_days: int = 180
    ) -> int:
        """
        Entfernt alte/ungenutzte Patterns.
        
        Args:
            db: Database session
            user_id: User ID
            min_emails: Minimum E-Mails um Pattern zu behalten
            max_age_days: Maximales Alter in Tagen
            
        Returns:
            Anzahl gelöschter Patterns
        """
        from datetime import timedelta
        
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        
        deleted = db.query(models.SenderPattern).filter(
            models.SenderPattern.user_id == user_id,
            models.SenderPattern.email_count <= min_emails,
            models.SenderPattern.updated_at < cutoff
        ).delete(synchronize_session=False)
        
        db.commit()
        
        if deleted > 0:
            logger.info(f"Cleanup: {deleted} alte Sender-Patterns gelöscht für User {user_id}")
        
        return deleted
