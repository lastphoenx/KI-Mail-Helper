"""
Tag Manager Service - Email-Tags verwalten (Phase 10)

Funktionen:
- create_tag(): Neuen Tag erstellen
- get_user_tags(): Alle Tags eines Users
- assign_tag(): Tag zu Email zuweisen
- remove_tag(): Tag von Email entfernen
- get_email_tags(): Tags einer Email

Phase 11c: Tag-Embeddings für semantische Ähnlichkeit
- suggest_similar_tags(): Findet ähnliche Tags basierend auf Embeddings
- get_tag_suggestions(): Tag-Vorschläge für Email
"""

from datetime import datetime, UTC
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Import from sibling directory (src/)
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import models module (02_models.py)
from importlib import import_module
models = import_module("02_models")


class TagEmbeddingCache:
    """Phase 11c: Cache für Tag-Embeddings
    
    Speichert Embeddings aller User-Tags im Memory für schnelle Similarity-Suche.
    """
    
    _cache: dict = {}  # {user_id: {tag_name: embedding}}
    _ollama_client = None
    
    @classmethod
    def _get_ollama_client(cls):
        """Lazy-Init des Ollama Clients"""
        if cls._ollama_client is None:
            try:
                ai_client = import_module("03_ai_client")
                cls._ollama_client = ai_client.LocalOllamaClient(model="all-minilm:22m")
            except Exception as e:
                logger.warning(f"Ollama Client nicht verfügbar: {e}")
                return None
        return cls._ollama_client
    
    @classmethod
    def get_tag_embedding(cls, tag_name: str, user_id: int) -> Optional[np.ndarray]:
        """Holt oder generiert Embedding für einen Tag-Namen"""
        # Check Cache
        if user_id in cls._cache and tag_name in cls._cache[user_id]:
            return cls._cache[user_id][tag_name]
        
        # Generiere Embedding
        client = cls._get_ollama_client()
        if not client:
            return None
        
        embedding = client._get_embedding(tag_name)
        if embedding:
            embedding_array = np.array(embedding)
            
            # Cache speichern
            if user_id not in cls._cache:
                cls._cache[user_id] = {}
            cls._cache[user_id][tag_name] = embedding_array
            
            return embedding_array
        return None
    
    @classmethod
    def invalidate_user_cache(cls, user_id: int):
        """Invalidiert Cache für einen User (z.B. nach Tag-Rename)"""
        if user_id in cls._cache:
            del cls._cache[user_id]
    
    @classmethod
    def compute_similarity(cls, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Berechnet Cosine-Similarity zwischen zwei Embeddings"""
        if emb1 is None or emb2 is None:
            return 0.0
        
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(emb1, emb2) / (norm1 * norm2))


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
            
            # Cache invalidieren (Phase 11c) - neuer Tag verfügbar
            TagEmbeddingCache.invalidate_user_cache(user_id)
            
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
        
        # Cache invalidieren (Phase 11c)
        TagEmbeddingCache.invalidate_user_cache(user_id)
        
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
            
            # Cache invalidieren bei Namensänderung (Phase 11c)
            if name is not None:
                TagEmbeddingCache.invalidate_user_cache(user_id)
            
            return tag
        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Tag konnte nicht aktualisiert werden: {e}")
    
    # ============================================
    # Phase 11c: Tag-Suggestions basierend auf Embeddings
    # ============================================
    
    @staticmethod
    def suggest_similar_tags(
        db: Session,
        user_id: int,
        text: str,
        top_k: int = 5,
        min_similarity: float = 0.3
    ) -> List[Tuple[models.EmailTag, float]]:
        """
        Findet Tags die semantisch ähnlich zum gegebenen Text sind.
        
        Verwendet Ollama-Embeddings um die Ähnlichkeit zwischen dem
        Text (z.B. E-Mail-Betreff+Inhalt) und den Tag-Namen zu berechnen.
        
        Args:
            db: Database session
            user_id: User ID für Tag-Lookup
            text: Text zum Vergleichen (z.B. E-Mail subject + body)
            top_k: Maximale Anzahl Vorschläge
            min_similarity: Minimale Ähnlichkeit (0-1)
            
        Returns:
            Liste von (Tag, Ähnlichkeit) Tupeln, sortiert nach Ähnlichkeit
        """
        # Alle Tags des Users holen
        tags = db.query(models.EmailTag).filter(
            models.EmailTag.user_id == user_id
        ).all()
        
        if not tags:
            return []
        
        # Text-Embedding holen
        text_embedding = TagEmbeddingCache.get_tag_embedding(text[:512], user_id)
        if text_embedding is None:
            logger.warning("Konnte kein Embedding für Text generieren")
            return []
        
        # Ähnlichkeiten berechnen
        similarities: List[Tuple[models.EmailTag, float]] = []
        
        for tag in tags:
            tag_embedding = TagEmbeddingCache.get_tag_embedding(tag.name, user_id)
            if tag_embedding is None:
                continue
                
            similarity = TagEmbeddingCache.compute_similarity(text_embedding, tag_embedding)
            
            if similarity >= min_similarity:
                similarities.append((tag, similarity))
        
        # Nach Ähnlichkeit sortieren (höchste zuerst)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]
    
    @staticmethod
    def get_tag_suggestions_for_email(
        db: Session,
        email_id: int,
        user_id: int,
        top_k: int = 3
    ) -> List[Dict[str, any]]:
        """
        Holt Tag-Vorschläge für eine spezifische E-Mail.
        
        Args:
            db: Database session
            email_id: E-Mail ID
            user_id: User ID
            top_k: Maximale Anzahl Vorschläge
            
        Returns:
            Liste von Tag-Vorschlägen mit id, name, color, similarity
        """
        # E-Mail holen (ProcessedEmail für subject/body_preview)
        email = db.query(models.ProcessedEmail).filter(
            models.ProcessedEmail.id == email_id
        ).first()
        
        if not email:
            return []
        
        # Bereits zugewiesene Tags ausschließen
        assigned_tag_ids = {
            assignment.tag_id 
            for assignment in db.query(models.EmailTagAssignment).filter(
                models.EmailTagAssignment.email_id == email_id
            ).all()
        }
        
        # Text für Similarity - encrypted fields müssen entschlüsselt werden
        # Fallback auf leeren String wenn nicht verfügbar
        subject = getattr(email, 'decrypted_subject', '') or ''
        body = getattr(email, 'decrypted_body', '') or getattr(email, 'body_preview', '') or ''
        text = f"{subject} {body}"[:512]  # Limit für Embedding
        
        # Vorschläge holen
        suggestions = TagManager.suggest_similar_tags(db, user_id, text, top_k=top_k + len(assigned_tag_ids))
        
        # Filtern und formatieren
        result = []
        for tag, similarity in suggestions:
            if tag.id in assigned_tag_ids:
                continue
            if len(result) >= top_k:
                break
            result.append({
                "id": tag.id,
                "name": tag.name,
                "color": tag.color,
                "similarity": round(similarity, 3)
            })
        
        return result
