"""
Tag Manager Service - Email-Tags verwalten (Phase 10)

Funktionen:
- create_tag(): Neuen Tag erstellen
- get_user_tags(): Alle Tags eines Users
- assign_tag(): Tag zu Email zuweisen
- remove_tag(): Tag von Email entfernen
- get_email_tags(): Tags einer Email
"""

from datetime import datetime, UTC
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Import from sibling directory (src/)
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import models module (02_models.py)
from importlib import import_module
models = import_module("02_models")


class TagManager:
    """Service für Tag-Management"""

    @staticmethod
    def create_tag(
        db: Session, user_id: int, name: str, color: str = "#3B82F6"
    ) -> models.EmailTag:
        """Erstellt neuen Tag für User
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            name: Tag-Name (max 50 Zeichen)
            color: Hex-Color (default: Tailwind blue-500)
            
        Returns:
            EmailTag object
            
        Raises:
            ValueError: Wenn Tag-Name bereits existiert oder invalid
        """
        # Validierung
        if not name or len(name) > 50:
            raise ValueError("Tag-Name muss 1-50 Zeichen sein")
        
        if not color.startswith("#") or len(color) != 7:
            raise ValueError("Color muss Hex-Format sein (#RRGGBB)")
        
        # Prüfe ob Tag bereits existiert
        existing = (
            db.query(models.EmailTag)
            .filter(models.EmailTag.user_id == user_id, models.EmailTag.name == name)
            .first()
        )
        if existing:
            raise ValueError(f"Tag '{name}' existiert bereits")
        
        # Erstelle Tag
        tag = models.EmailTag(user_id=user_id, name=name, color=color)
        db.add(tag)
        
        try:
            db.commit()
            db.refresh(tag)
            return tag
        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Tag konnte nicht erstellt werden: {e}")

    @staticmethod
    def get_user_tags(db: Session, user_id: int) -> List[models.EmailTag]:
        """Gibt alle Tags eines Users zurück
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            
        Returns:
            Liste von EmailTag objects (sortiert nach Name)
        """
        return (
            db.query(models.EmailTag)
            .filter(models.EmailTag.user_id == user_id)
            .order_by(models.EmailTag.name)
            .all()
        )

    @staticmethod
    def get_or_create_tag(
        db: Session, user_id: int, name: str, color: str = "#3B82F6"
    ) -> models.EmailTag:
        """Gibt existierenden Tag zurück oder erstellt neuen
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            name: Tag-Name
            color: Hex-Color (nur bei Erstellung)
            
        Returns:
            EmailTag object
        """
        tag = (
            db.query(models.EmailTag)
            .filter(models.EmailTag.user_id == user_id, models.EmailTag.name == name)
            .first()
        )
        
        if not tag:
            tag = models.EmailTag(user_id=user_id, name=name, color=color)
            db.add(tag)
            db.commit()
            db.refresh(tag)
        
        return tag

    @staticmethod
    def assign_tag(db: Session, email_id: int, tag_id: int, user_id: int) -> bool:
        """Weist Tag zu Email zu
        
        Args:
            db: SQLAlchemy Session
            email_id: ProcessedEmail ID
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich, False wenn bereits zugewiesen
            
        Raises:
            ValueError: Wenn Email oder Tag nicht existiert oder nicht zu User gehört
        """
        # Validiere Email
        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
                models.RawEmail.user_id == user_id,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )
        if not email:
            raise ValueError("Email nicht gefunden")
        
        # Validiere Tag
        tag = (
            db.query(models.EmailTag)
            .filter(models.EmailTag.id == tag_id, models.EmailTag.user_id == user_id)
            .first()
        )
        if not tag:
            raise ValueError("Tag nicht gefunden")
        
        # Prüfe ob bereits zugewiesen
        existing = (
            db.query(models.EmailTagAssignment)
            .filter(
                models.EmailTagAssignment.email_id == email_id,
                models.EmailTagAssignment.tag_id == tag_id,
            )
            .first()
        )
        if existing:
            return False  # Bereits zugewiesen
        
        # Erstelle Assignment
        assignment = models.EmailTagAssignment(email_id=email_id, tag_id=tag_id)
        db.add(assignment)
        
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def remove_tag(db: Session, email_id: int, tag_id: int, user_id: int) -> bool:
        """Entfernt Tag von Email
        
        Args:
            db: SQLAlchemy Session
            email_id: ProcessedEmail ID
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich, False wenn nicht zugewiesen
        """
        # Validiere dass Email und Tag zu User gehören
        assignment = (
            db.query(models.EmailTagAssignment)
            .join(models.ProcessedEmail)
            .join(models.RawEmail)
            .join(models.EmailTag)
            .filter(
                models.EmailTagAssignment.email_id == email_id,
                models.EmailTagAssignment.tag_id == tag_id,
                models.RawEmail.user_id == user_id,
                models.EmailTag.user_id == user_id,
            )
            .first()
        )
        
        if not assignment:
            return False
        
        db.delete(assignment)
        db.commit()
        return True

    @staticmethod
    def get_email_tags(db: Session, email_id: int, user_id: int) -> List[models.EmailTag]:
        """Gibt alle Tags einer Email zurück
        
        Args:
            db: SQLAlchemy Session
            email_id: ProcessedEmail ID
            user_id: User ID (zur Validierung)
            
        Returns:
            Liste von EmailTag objects
        """
        return (
            db.query(models.EmailTag)
            .join(models.EmailTagAssignment)
            .join(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.EmailTagAssignment.email_id == email_id,
                models.RawEmail.user_id == user_id,
                models.ProcessedEmail.deleted_at == None,
            )
            .order_by(models.EmailTag.name)
            .all()
        )

    @staticmethod
    def delete_tag(db: Session, tag_id: int, user_id: int) -> bool:
        """Löscht Tag (CASCADE löscht auch alle Assignments)
        
        Args:
            db: SQLAlchemy Session
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich, False wenn Tag nicht existiert
        """
        tag = (
            db.query(models.EmailTag)
            .filter(models.EmailTag.id == tag_id, models.EmailTag.user_id == user_id)
            .first()
        )
        
        if not tag:
            return False
        
        db.delete(tag)
        db.commit()
        return True

    @staticmethod
    def update_tag(
        db: Session, tag_id: int, user_id: int, name: Optional[str] = None, color: Optional[str] = None
    ) -> Optional[models.EmailTag]:
        """Aktualisiert Tag-Name oder -Farbe
        
        Args:
            db: SQLAlchemy Session
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            name: Neuer Name (optional)
            color: Neue Farbe (optional)
            
        Returns:
            Aktualisierter EmailTag oder None wenn nicht gefunden
            
        Raises:
            ValueError: Bei Validierungsfehlern
        """
        tag = (
            db.query(models.EmailTag)
            .filter(models.EmailTag.id == tag_id, models.EmailTag.user_id == user_id)
            .first()
        )
        
        if not tag:
            return None
        
        if name is not None:
            if not name or len(name) > 50:
                raise ValueError("Tag-Name muss 1-50 Zeichen sein")
            
            # Prüfe ob neuer Name bereits existiert
            existing = (
                db.query(models.EmailTag)
                .filter(
                    models.EmailTag.user_id == user_id,
                    models.EmailTag.name == name,
                    models.EmailTag.id != tag_id,
                )
                .first()
            )
            if existing:
                raise ValueError(f"Tag '{name}' existiert bereits")
            
            tag.name = name
        
        if color is not None:
            if not color.startswith("#") or len(color) != 7:
                raise ValueError("Color muss Hex-Format sein (#RRGGBB)")
            tag.color = color
        
        try:
            db.commit()
            db.refresh(tag)
            return tag
        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Tag konnte nicht aktualisiert werden: {e}")
