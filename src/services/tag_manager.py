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
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import numpy as np
import logging
import importlib

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


# ============================================================================
# Phase F.2 Enhanced: Learning Configuration
# ============================================================================

# Minimum Anzahl Emails für stabiles Learning
MIN_EMAILS_FOR_LEARNING = 3

# Auto-Assignment: Nur sehr sichere Matches (80%)
AUTO_ASSIGN_SIMILARITY_THRESHOLD = 0.80

def get_suggestion_threshold(total_tags: int) -> float:
    """Dynamischer Threshold basierend auf Tag-Anzahl
    
    Logik: Bei wenigen Tags lockerer, bei vielen Tags strenger
    - <= 5 Tags: 70% (User hat wenige Tags, mehr Vorschläge helfen)
    - 6-15 Tags: 75% (Mittelfeld)
    - >= 16 Tags: 80% (Viele Tags, nur beste Matches)
    
    HINWEIS: Seit Bugfix (OllamaEmbeddingClient statt LocalOllamaClient)
    funktionieren diese Thresholds für ALLE Embedding-Quellen (learned/description/name).
    Die alten source-spezifischen Thresholds (15-25% für description) werden
    nicht mehr benötigt, da nun korrekte Embeddings generiert werden.
    """
    if total_tags <= 5:
        return 0.70
    elif total_tags <= 15:
        return 0.75
    else:
        return 0.80


class TagEmbeddingCache:
    """Phase F.2: Cache für Tag-Embeddings mit Learning
    
    Speichert Embeddings aller User-Tags im Memory für schnelle Similarity-Suche.
    
    Learning-Hierarchie (Fallback-Kette):
    1. learned_embedding (aggregiert aus assigned emails) - BESTE Qualität!
    2. description Embedding (semantische Beschreibung)
    3. name Embedding (nur Tag-Name, schwächste Option)
    """
    
    _cache: dict = {}  # {user_id: {tag_id: embedding}}
    _ai_client_cache: dict = {}  # {user_id: ai_client}
    _current_model: dict = {}  # {user_id: "model-name"} - für Auto-Invalidierung bei Model-Wechsel
    
    @classmethod
    def _get_ai_client_for_user(cls, user_id: int, db: Session = None):
        """Holt dedizierten Embedding-Client für Tag-Embeddings
        
        WICHTIG: Nutzt OllamaEmbeddingClient (05_embedding_api.py), 
        nicht LocalOllamaClient (Chat-Model)!
        
        STRATEGIE: Verwendet das GLEICHE Embedding-Model wie die Emails!
        - Liest embedding_model aus vorhandenen Emails des Users
        - Garantiert Dimensions-Kompatibilität (384, 768, 1536, etc.)
        - Model-Wechsel: Settings ändern + Emails neu verarbeiten
        
        Returns:
            OllamaEmbeddingClient oder None
        """
        try:
            # Import des RICHTIGEN Embedding-Clients (nicht Chat-Client!)
            embedding_api = import_module(".05_embedding_api", "src")
            
            # 1. Ermittle Embedding-Model aus vorhandenen Emails
            embedding_model = "all-minilm:22m"  # Default-Fallback
            
            if db:
                # Sample: Erste Email mit Embedding holen
                sample_email = db.query(models.RawEmail).filter(
                    models.RawEmail.user_id == user_id,
                    models.RawEmail.email_embedding.isnot(None),
                    models.RawEmail.embedding_model.isnot(None)
                ).first()
                
                if sample_email:
                    embedding_model = sample_email.embedding_model
                    logger.info(f"🔍 Tag-Embeddings: Using model from emails: {embedding_model}")
                else:
                    logger.warning(f"⚠️  No emails with embeddings found for user {user_id}, using default: {embedding_model}")
            
            # 🆕 AUTO-INVALIDIERUNG: Prüfe ob Model geändert wurde
            if user_id in cls._current_model:
                old_model = cls._current_model[user_id]
                if old_model != embedding_model:
                    logger.info(f"🔄 Model-Wechsel erkannt: {old_model} → {embedding_model}")
                    # Cache komplett leeren bei Model-Wechsel!
                    if user_id in cls._cache:
                        cls._cache[user_id].clear()
                    if user_id in cls._ai_client_cache:
                        del cls._ai_client_cache[user_id]
                    logger.info(f"🗑️  Tag-Cache für User {user_id} geleert (Model-Wechsel)")
            
            # Speichere aktuelles Model
            cls._current_model[user_id] = embedding_model
            
            # Cache Check NACH Model-Validierung
            if user_id in cls._ai_client_cache:
                return cls._ai_client_cache[user_id]
            
            # 2. Embedding-Client mit dem ermittelten Model erstellen
            # WICHTIG: LocalOllamaClient für Chunking-Support nutzen!
            ai_client_module = importlib.import_module("src.03_ai_client")
            client = ai_client_module.LocalOllamaClient(
                model=embedding_model,
                base_url="http://127.0.0.1:11434"
            )
            
            cls._ai_client_cache[user_id] = client
            logger.info(f"✅ Tag-Embeddings: Created LocalOllamaClient with {embedding_model}")
            return client
            
        except Exception as e:
            logger.error(f"Embedding-Client konnte nicht erstellt werden: {e}")
            return None
    
    @classmethod
    def get_tag_embedding(cls, tag: models.EmailTag, db: Session) -> Optional[np.ndarray]:
        """Holt Embedding für Tag (Learning-Hierarchie!)
        
        Fallback-Kette:
        1. learned_embedding (aus assigned emails) - BESTE Qualität!
        2. description Embedding (semantische Beschreibung)
        3. name Embedding (nur Tag-Name)
        
        Args:
            tag: EmailTag object
            db: Database session (für User-Settings)
        """
        # 🆕 WICHTIG: Zuerst Client holen (prüft Model-Wechsel + invalidiert Cache!)
        client = cls._get_ai_client_for_user(tag.user_id, db)
        if not client:
            logger.error(f"❌ Kein AI-Client für User {tag.user_id}")
            return None
        
        # Check Cache NACH Model-Validierung
        if tag.user_id in cls._cache and tag.id in cls._cache[tag.user_id]:
            return cls._cache[tag.user_id][tag.id]
        
        # 1. PRIORITÄT: Learned Embedding (aggregiert aus assigned emails)
        if tag.learned_embedding:
            try:
                embedding_array = np.frombuffer(tag.learned_embedding, dtype=np.float32)
                logger.debug(f"🎓 Tag '{tag.name}': Using learned embedding ({len(embedding_array)} dims)")
                
                # Cache speichern
                if tag.user_id not in cls._cache:
                    cls._cache[tag.user_id] = {}
                cls._cache[tag.user_id][tag.id] = embedding_array
                return embedding_array
            except Exception as e:
                logger.warning(f"Learned embedding konvertierung fehlgeschlagen: {e}")
        
        # 2. FALLBACK: Description Embedding (semantische Beschreibung)
        text_for_embedding = tag.description if tag.description else tag.name
        
        # Client wurde bereits oben geholt (mit Model-Validierung!)
        # LocalOllamaClient nutzt _get_embedding() (mit Chunking!)
        logger.info(f"🔍 DEBUG: Generiere Embedding für Tag '{tag.name}' mit Text: '{text_for_embedding[:100]}...'")
        embedding = client._get_embedding(text_for_embedding)
        
        if embedding:
            logger.info(f"🔍 DEBUG: Embedding erhalten - Type: {type(embedding)}, Länge: {len(embedding) if embedding else 'None'}")
            embedding_array = np.array(embedding, dtype=np.float32)
            logger.info(f"🔍 DEBUG: Embedding-Array - Shape: {embedding_array.shape}, Dtype: {embedding_array.dtype}")
            
            # 🆕 WICHTIG: Normalisieren für konsistente Similarity!
            # Ollama gibt normalisierte Embeddings (Norm = 1.0) zurück,
            # aber nach Chunking + Mean-Pooling ist Norm < 1.0
            norm = np.linalg.norm(embedding_array)
            if norm > 0:
                embedding_array = embedding_array / norm
                logger.debug(f"📊 Tag-Embedding normalisiert: {norm:.4f} → 1.0")
            
            source = "description" if tag.description else "name"
            logger.info(f"📝 Tag '{tag.name}': Generated embedding from {source} ('{text_for_embedding[:50]}...')")
            
            # Cache speichern
            if tag.user_id not in cls._cache:
                cls._cache[tag.user_id] = {}
            cls._cache[tag.user_id][tag.id] = embedding_array
            
            return embedding_array
        else:
            logger.error(f"❌ DEBUG: get_embedding() gab None/Empty zurück für Tag '{tag.name}'!")
        return None
    
    @classmethod
    def invalidate_tag_cache(cls, tag_id: int, user_id: int):
        """Invalidiert Cache für einen spezifischen Tag"""
        if user_id in cls._cache and tag_id in cls._cache[user_id]:
            del cls._cache[user_id][tag_id]
    
    @classmethod
    def invalidate_user_cache(cls, user_id: int):
        """Invalidiert Cache für einen User (z.B. nach Settings-Änderung)"""
        if user_id in cls._cache:
            del cls._cache[user_id]
        if user_id in cls._ai_client_cache:
            del cls._ai_client_cache[user_id]
    
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
    
    @staticmethod
    def _get_thresholds_for_tag(tag: models.EmailTag) -> tuple:
        """
        Bestimme Suggest- und Auto-Assign-Thresholds basierend auf der Embedding-Quelle.
        
        Source-spezifische Thresholds:
        - Learned Embeddings: 75% suggest, 80% auto-assign (höchste Qualität)
        - Description-basierte: 50% suggest, 60% auto-assign (mittlere Qualität)
        - Name-basierte: 35% suggest, 45% auto-assign (niedrigste Qualität)
        
        Args:
            tag: EmailTag object mit learned_embedding, description, name
            
        Returns:
            tuple: (suggest_threshold, auto_assign_threshold)
        """
        if tag.learned_embedding:
            # Learned Embeddings sind sehr präzise (aus echten Emails gelernt)
            # → Hohe Thresholds (75%/80%)
            return 0.75, 0.80
        elif tag.description:
            # Description-basierte Embeddings haben mittlere Qualität
            # → Mittlere Thresholds (50%/60%)
            return 0.50, 0.60
        else:
            # Name-basierte Embeddings sind am generischsten
            # → Niedrigere Thresholds (35%/45%)
            return 0.35, 0.45


class TagManager:
    """Service für Tag-Management"""

    @staticmethod
    def create_tag(
        db: Session, user_id: int, name: str, color: str = "#3B82F6", description: Optional[str] = None
    ) -> models.EmailTag:
        """Erstellt neuen Tag für User (Phase F.2: mit description)
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID
            name: Tag-Name (max 50 Zeichen)
            color: Hex-Color (default: Tailwind blue-500)
            description: Semantische Beschreibung (optional, für bessere Embeddings)
            
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
        tag = models.EmailTag(user_id=user_id, name=name, color=color, description=description)
        db.add(tag)
        
        try:
            db.commit()
            db.refresh(tag)
            
            # Cache invalidieren (Phase F.2) - neuer Tag verfügbar
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
            
            # Phase F.2 Learning: Update learned_embedding nach jeder Zuweisung!
            TagManager.update_learned_embedding(db, tag_id, user_id)
            
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
        
        # Phase F.2 Learning: Update learned_embedding nach Tag-Entfernung
        # WICHTIG: Embedding muss neu berechnet werden, da sich die assigned emails geändert haben
        TagManager.update_learned_embedding(db, tag_id, user_id)
        logger.info(f"🎓 Tag-Learning aktualisiert nach Entfernung von Email {email_id} (Tag ID: {tag_id})")
        
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
        db: Session, tag_id: int, user_id: int, name: Optional[str] = None, 
        color: Optional[str] = None, description: Optional[str] = None
    ) -> Optional[models.EmailTag]:
        """Aktualisiert Tag-Name, -Farbe oder -Beschreibung (Phase F.2)
        
        Args:
            db: SQLAlchemy Session
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            name: Neuer Name (optional)
            color: Neue Farbe (optional)
            description: Neue Beschreibung (optional, None = unverändert, "" = löschen)
            
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
        
        if description is not None:
            # Leerer String = description löschen
            tag.description = description if description.strip() else None
        
        try:
            db.commit()
            db.refresh(tag)
            
            # Cache invalidieren bei Name/Description-Änderung (Phase F.2)
            if name is not None or description is not None:
                TagEmbeddingCache.invalidate_tag_cache(tag_id, user_id)
            
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
    def suggest_tags_by_email_embedding(
        db: Session,
        user_id: int,
        email_embedding_bytes: bytes,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
        exclude_tag_ids: Optional[List[int]] = None
    ) -> List[Tuple[models.EmailTag, float]]:
        """
        Phase F.2 Enhanced: Findet Tags die semantisch ähnlich zum Email-Embedding sind.
        
        OPTIMIERT: Nutzt vorhandene Email-Embeddings direkt (bereits beim Fetch generiert),
        kein Re-Embedding nötig! Mit dynamischen Thresholds basierend auf Tag-Anzahl.
        
        Args:
            db: Database session
            user_id: User ID für Tag-Lookup
            email_embedding_bytes: Email-Embedding (bytes aus RawEmail.email_embedding)
            top_k: Maximale Anzahl Vorschläge
            min_similarity: Minimale Ähnlichkeit (0-1). Wenn None, wird dynamischer Threshold verwendet
            exclude_tag_ids: Optional - Tag-IDs die ignoriert werden sollen (z.B. bereits assigned)
            
        Returns:
            Liste von (Tag, Ähnlichkeit) Tupeln, sortiert nach Ähnlichkeit
        """
        # Alle Tags des Users holen
        tags = db.query(models.EmailTag).filter(
            models.EmailTag.user_id == user_id
        ).all()
        
        if not tags:
            logger.info(f"⚠️  Phase F.2: User {user_id} has no tags")
            return []
        
        total_tags = len(tags)
        
        # Dynamischer Threshold basierend auf Tag-Anzahl (wenn nicht explizit gesetzt)
        if min_similarity is None:
            min_similarity = get_suggestion_threshold(total_tags)
        
        logger.info(
            f"🔍 Phase F.2: Checking {total_tags} tags for user {user_id} "
            f"(threshold={min_similarity:.0%}, auto-assign={AUTO_ASSIGN_SIMILARITY_THRESHOLD:.0%})"
        )
        
        # Email-Embedding konvertieren
        try:
            email_embedding = np.frombuffer(email_embedding_bytes, dtype=np.float32)
            logger.info(f"🔍 DEBUG: Email-Embedding - Shape: {email_embedding.shape}, Dtype: {email_embedding.dtype}")
        except Exception as e:
            logger.warning(f"Konnte Email-Embedding nicht konvertieren: {e}")
            return []
        
        # Ähnlichkeiten berechnen
        similarities: List[Tuple[models.EmailTag, float, str]] = []  # (tag, similarity, source)
        exclude_set = set(exclude_tag_ids or [])
        
        if exclude_set:
            logger.info(f"⏭️  Phase F.2: Excluding {len(exclude_set)} already assigned tags")
        
        for tag in tags:
            # Skip bereits zugewiesene Tags
            if tag.id in exclude_set:
                logger.debug(f"⏭️  Phase F.2: Skipping already assigned tag '{tag.name}'")
                continue
            
            # Tag-Embedding holen (nutzt jetzt OllamaEmbeddingClient!)
            tag_embedding = TagEmbeddingCache.get_tag_embedding(tag, db)
            if tag_embedding is None:
                logger.warning(f"⚠️  Phase F.2: Could not get embedding for tag '{tag.name}'")
                continue
            
            logger.info(f"🔍 DEBUG: Tag '{tag.name}' Embedding - Shape: {tag_embedding.shape}, Dtype: {tag_embedding.dtype}")
            
            # Cosine Similarity berechnen
            similarity = TagEmbeddingCache.compute_similarity(email_embedding, tag_embedding)
            
            logger.info(
                f"🔍 DEBUG: Similarity Berechnung - "
                f"Email norm: {np.linalg.norm(email_embedding):.4f}, "
                f"Tag norm: {np.linalg.norm(tag_embedding):.4f}, "
                f"Dot product: {np.dot(email_embedding, tag_embedding):.4f}"
            )
            
            # 🆕 Source-spezifische Thresholds holen
            suggest_threshold, auto_assign_threshold = TagEmbeddingCache._get_thresholds_for_tag(tag)
            
            # Embedding-Quelle bestimmen (für Logging)
            if tag.learned_embedding:
                source = "learned"
            elif tag.description:
                source = "description"
            else:
                source = "name"
            
            # Konfidenz-Level mit source-spezifischen Thresholds bestimmen
            will_auto_assign = similarity >= auto_assign_threshold
            will_suggest = similarity >= suggest_threshold
            
            # LOG mit allen Details
            logger.info(
                f"📊 Tag '{tag.name}' ({source}): similarity={similarity:.4f} "
                f"thresh=[suggest={suggest_threshold:.0%}, auto={auto_assign_threshold:.0%}] "
                f"→ (auto={will_auto_assign}, suggest={will_suggest})"
            )
            
            if will_suggest:
                similarities.append((tag, similarity, source))
                if will_auto_assign:
                    logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity:.0%})")
                else:
                    logger.info(f"💡 SUGGEST: Tag '{tag.name}' ({similarity:.0%})")
        
        # Nach Ähnlichkeit sortieren (höchste zuerst)
        similarities_sorted = sorted(similarities, key=lambda x: x[1], reverse=True)
        
        # Top-K auswählen
        result = [(tag, sim) for tag, sim, _ in similarities_sorted[:top_k]]
        
        logger.info(
            f"✅ Phase F.2: Returning {len(result)} tag suggestions "
            f"(dynamic thresholds: learned=75%, description=50%, name=35%)"
        )
        
        return result
    
    @staticmethod
    def get_tag_suggestions_for_email(
        db: Session,
        email_id: int,
        user_id: int,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
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
    
    @staticmethod
    def update_learned_embedding(db: Session, tag_id: int, user_id: int) -> bool:
        """Phase F.2 Learning: Update Tag-Embedding aus assigned emails
        
        Berechnet Mittelwert aller email_embeddings von Emails mit diesem Tag.
        Wird nach jeder Tag-Zuweisung/Entfernung aufgerufen.
        
        Args:
            db: Database session
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich, False wenn nicht genug Daten
        """
        try:
            # Tag validieren
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user_id).first()
            if not tag:
                logger.warning(f"Tag {tag_id} nicht gefunden")
                return False
            
            # Alle assigned emails mit Embeddings holen
            assigned_emails = (
                db.query(models.RawEmail)
                .join(models.ProcessedEmail, models.RawEmail.id == models.ProcessedEmail.raw_email_id)
                .join(models.EmailTagAssignment, models.ProcessedEmail.id == models.EmailTagAssignment.email_id)
                .filter(
                    models.EmailTagAssignment.tag_id == tag_id,
                    models.RawEmail.email_embedding.isnot(None),
                    models.RawEmail.user_id == user_id
                )
                .all()
            )
            
            email_count = len(assigned_emails)
            
            if email_count == 0:
                logger.debug(f"🎓 Tag '{tag.name}': Keine Emails mit Embeddings für Learning")
                # Learned embedding löschen falls vorhanden
                if tag.learned_embedding:
                    tag.learned_embedding = None
                    tag.embedding_updated_at = None
                    db.commit()
                    TagEmbeddingCache.invalidate_tag_cache(tag_id, user_id)
                return False
            
            # NEU: Minimum Emails Check für stabiles Learning
            if email_count < MIN_EMAILS_FOR_LEARNING:
                logger.debug(
                    f"🎓 Tag '{tag.name}': Nur {email_count} Email(s), "
                    f"warte auf min. {MIN_EMAILS_FOR_LEARNING} für stabiles Learning"
                )
                return False
            
            # Embeddings sammeln und mitteln
            embeddings = []
            for email in assigned_emails:
                try:
                    emb = np.frombuffer(email.email_embedding, dtype=np.float32)
                    embeddings.append(emb)
                except Exception as e:
                    logger.warning(f"Embedding konvertierung fehlgeschlagen: {e}")
                    continue
            
            if not embeddings:
                return False
            
            # Mittelwert berechnen
            learned_embedding = np.mean(embeddings, axis=0)
            
            # In DB speichern
            tag.learned_embedding = learned_embedding.tobytes()
            tag.embedding_updated_at = datetime.now(UTC)
            db.commit()
            
            # Cache invalidieren
            TagEmbeddingCache.invalidate_tag_cache(tag_id, user_id)
            
            logger.info(
                f"🎓 Tag '{tag.name}': Learned embedding updated from "
                f"{len(embeddings)} emails (min={MIN_EMAILS_FOR_LEARNING})"
            )
            return True
            
        except Exception as e:
            logger.error(f"update_learned_embedding fehlgeschlagen: {e}")
            db.rollback()
            return False


