"""
Tag Suggestion Service - KI-Tag-Vorschläge in Warteschlange (Phase TAG-QUEUE)

Verwaltet die Warteschlange für AI-vorgeschlagene Tags:
- add_to_queue(): Fügt Vorschlag zur Queue hinzu
- get_pending_suggestions(): Holt pending Vorschläge
- approve_suggestion(): Genehmigt → erstellt Tag
- reject_suggestion(): Lehnt ab
- merge_suggestion(): Merged zu existierendem Tag
"""

from datetime import datetime, UTC
from typing import List, Optional
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

# Import models module
from importlib import import_module
models = import_module("src.02_models")


class TagSuggestionService:
    """Service für Tag Suggestion Queue Management"""

    @staticmethod
    def add_to_queue(
        db: Session,
        user_id: int,
        suggested_name: str,
        source_email_id: Optional[int] = None,
    ) -> models.TagSuggestionQueue:
        """Fügt Vorschlag zur Queue hinzu oder erhöht Counter
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            suggested_name: Tag-Name (max 50 chars)
            source_email_id: ProcessedEmail ID (optional)
            
        Returns:
            TagSuggestionQueue object
        """
        # Normalisiere Namen
        suggested_name = suggested_name.strip()[:50]
        if not suggested_name:
            return None

        # Prüfe ob bereits pending (same name, same user)
        existing = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.suggested_name == suggested_name,
                models.TagSuggestionQueue.status == "pending",
            )
            .first()
        )

        if existing:
            # Nur Counter erhöhen + source_email aktualisieren falls vorhanden
            existing.suggestion_count += 1
            if source_email_id:
                existing.source_email_id = source_email_id
            db.commit()
            logger.debug(
                f"💡 Tag suggestion '{suggested_name}' count increased to {existing.suggestion_count}"
            )
            return existing

        # Neuen Vorschlag erstellen
        suggestion = models.TagSuggestionQueue(
            user_id=user_id,
            suggested_name=suggested_name,
            source_email_id=source_email_id,
            status="pending",
            suggestion_count=1,
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)
        logger.info(f"✅ Tag suggestion added: '{suggested_name}' (email {source_email_id})")
        return suggestion

    @staticmethod
    def get_pending_suggestions(db: Session, user_id: int) -> List[models.TagSuggestionQueue]:
        """Holt alle pending Vorschläge, sortiert nach Häufigkeit
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            
        Returns:
            Liste von TagSuggestionQueue objects
        """
        return (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.status == "pending",
            )
            .order_by(models.TagSuggestionQueue.suggestion_count.desc())
            .all()
        )

    @staticmethod
    def approve_suggestion(
        db: Session,
        suggestion_id: int,
        user_id: int,
        color: str = "#3B82F6",
    ) -> Optional[models.EmailTag]:
        """Genehmigt Vorschlag → Erstellt neuen Tag
        
        Args:
            db: SQLAlchemy Session
            suggestion_id: TagSuggestionQueue ID
            user_id: User ID (zur Validierung)
            color: Hex-Farbe für neuen Tag
            
        Returns:
            EmailTag object oder None wenn fehlgeschlagen
        """
        suggestion = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.id == suggestion_id,
                models.TagSuggestionQueue.user_id == user_id,
            )
            .first()
        )

        if not suggestion:
            logger.warning(f"Suggestion {suggestion_id} not found for user {user_id}")
            return None

        try:
            # Tag erstellen
            from . import tag_manager

            tag = tag_manager.TagManager.create_tag(
                db=db,
                user_id=user_id,
                name=suggestion.suggested_name,
                color=color,
            )

            # Status aktualisieren
            suggestion.status = "approved"
            suggestion.merged_into_tag_id = tag.id
            db.commit()

            logger.info(f"✅ Suggestion approved: '{suggestion.suggested_name}' → Tag {tag.id}")
            return tag

        except Exception as e:
            logger.error(f"❌ Error approving suggestion: {e}")
            db.rollback()
            return None

    @staticmethod
    def reject_suggestion(
        db: Session, suggestion_id: int, user_id: int
    ) -> bool:
        """Lehnt Vorschlag ab
        
        Args:
            db: SQLAlchemy Session
            suggestion_id: TagSuggestionQueue ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich
        """
        suggestion = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.id == suggestion_id,
                models.TagSuggestionQueue.user_id == user_id,
            )
            .first()
        )

        if not suggestion:
            return False

        suggestion.status = "rejected"
        db.commit()
        logger.info(f"❌ Suggestion rejected: '{suggestion.suggested_name}'")
        return True

    @staticmethod
    def merge_suggestion(
        db: Session,
        suggestion_id: int,
        target_tag_id: int,
        user_id: int,
    ) -> bool:
        """Merged Vorschlag zu existierendem Tag
        
        Args:
            db: SQLAlchemy Session
            suggestion_id: TagSuggestionQueue ID
            target_tag_id: EmailTag ID (Ziel)
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich
        """
        suggestion = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.id == suggestion_id,
                models.TagSuggestionQueue.user_id == user_id,
            )
            .first()
        )

        if not suggestion:
            logger.warning(f"Suggestion {suggestion_id} not found")
            return False

        # Validiere dass target_tag zum User gehört
        target_tag = (
            db.query(models.EmailTag)
            .filter(
                models.EmailTag.id == target_tag_id,
                models.EmailTag.user_id == user_id,
            )
            .first()
        )

        if not target_tag:
            logger.warning(f"Target tag {target_tag_id} not found for user {user_id}")
            return False

        suggestion.status = "merged"
        suggestion.merged_into_tag_id = target_tag_id
        db.commit()

        logger.info(
            f"🔀 Suggestion merged: '{suggestion.suggested_name}' → '{target_tag.name}'"
        )
        return True

    @staticmethod
    def batch_reject_by_user(db: Session, user_id: int) -> int:
        """Lehnt ALLE pending Vorschläge eines Users ab
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            
        Returns:
            Anzahl abgelehnte Vorschläge
        """
        count = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.status == "pending",
            )
            .update({"status": "rejected"})
        )
        db.commit()
        logger.info(f"❌ Batch rejected {count} suggestions for user {user_id}")
        return count

    @staticmethod
    def batch_approve_by_user(db: Session, user_id: int, color: str = "#3B82F6") -> int:
        """Genehmigt ALLE pending Vorschläge eines Users
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            color: Hex-Farbe für neue Tags
            
        Returns:
            Anzahl genehmigte Vorschläge
        """
        from . import tag_manager

        suggestions = TagSuggestionService.get_pending_suggestions(db, user_id)
        count = 0

        for suggestion in suggestions:
            try:
                tag = tag_manager.TagManager.create_tag(
                    db=db,
                    user_id=user_id,
                    name=suggestion.suggested_name,
                    color=color,
                )
                suggestion.status = "approved"
                suggestion.merged_into_tag_id = tag.id
                count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to approve suggestion '{suggestion.suggested_name}': {e}"
                )

        db.commit()
        logger.info(f"✅ Batch approved {count} suggestions for user {user_id}")
        return count

    @staticmethod
    def get_suggestion_stats(db: Session, user_id: int) -> dict:
        """Gibt Statistiken über Vorschläge
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            
        Returns:
            Dict mit pending/approved/rejected/merged counts
        """
        pending = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.status == "pending",
            )
            .count()
        )
        approved = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.status == "approved",
            )
            .count()
        )
        rejected = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.status == "rejected",
            )
            .count()
        )
        merged = (
            db.query(models.TagSuggestionQueue)
            .filter(
                models.TagSuggestionQueue.user_id == user_id,
                models.TagSuggestionQueue.status == "merged",
            )
            .count()
        )

        return {
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "merged": merged,
            "total": pending + approved + rejected + merged,
        }
