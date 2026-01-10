"""
Semantic Search Service (Phase 15)
==================================

Vektorbasierte Email-Suche mit Embeddings.

Features:
- Embedding-Generierung beim Email-Fetch (Klartext verfügbar!)
- Cosine Similarity für semantische Ähnlichkeit
- "Budget" findet auch "Kostenplanung", "Finanzübersicht"
- Zero-Knowledge kompatibel (Embeddings nicht reversibel)

Usage:
    from src.semantic_search import SemanticSearchService
    
    service = SemanticSearchService(db_session, ai_client)
    
    # Embedding generieren (beim Fetch)
    embedding = service.generate_embedding("Betreff", "Body-Text")
    
    # Suchen
    results = service.search("Projektbudget", user_id=1, limit=20)
"""

import logging
import numpy as np
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Embedding-Dimension für all-minilm:22m
EMBEDDING_DIM = 384
EMBEDDING_MODEL = "all-minilm:22m"

# Similarity-Schwellenwert (0.0 - 1.0)
DEFAULT_SIMILARITY_THRESHOLD = 0.25
HIGH_SIMILARITY_THRESHOLD = 0.5


class SemanticSearchService:
    """Service für semantische Email-Suche"""
    
    def __init__(self, db_session: Session = None, ai_client = None):
        """
        Args:
            db_session: SQLAlchemy Session für DB-Queries
            ai_client: AI Client mit _get_embedding() Methode (z.B. LocalOllamaClient)
        """
        self.db = db_session
        self.ai_client = ai_client
    
    # =========================================================================
    # EMBEDDING GENERATION (beim Fetch, Klartext verfügbar!)
    # =========================================================================
    
    def generate_embedding(
        self, 
        subject: str, 
        body: str,
        max_body_length: int = 500
    ) -> Optional[bytes]:
        """
        Generiert Embedding aus Subject + Body.
        
        WICHTIG: Aufrufen BEVOR verschlüsselt wird (Klartext nötig)!
        
        Args:
            subject: Email-Betreff (Klartext)
            body: Email-Body (Klartext)
            max_body_length: Maximale Body-Länge für Embedding
            
        Returns:
            Embedding als bytes (384 floats × 4 bytes = 1536 bytes)
            oder None bei Fehler
        """
        if not self.ai_client:
            logger.warning("Kein AI-Client für Embedding-Generierung")
            return None
        
        try:
            # Text für Embedding kombinieren
            # Subject ist wichtiger, daher zuerst
            text = f"{subject or ''}\n{(body or '')[:max_body_length]}"
            text = text.strip()
            
            if not text:
                logger.debug("Leerer Text, kein Embedding generiert")
                return None
            
            # Embedding von AI-Client holen
            embedding_list = self.ai_client._get_embedding(text)
            
            if not embedding_list:
                logger.warning("AI-Client lieferte kein Embedding")
                return None
            
            # Zu numpy array konvertieren und als bytes speichern
            embedding_array = np.array(embedding_list, dtype=np.float32)
            
            # Validierung
            if embedding_array.shape[0] != EMBEDDING_DIM:
                logger.warning(
                    f"Unerwartete Embedding-Dimension: {embedding_array.shape[0]} "
                    f"(erwartet: {EMBEDDING_DIM})"
                )
                # Trotzdem speichern, könnte anderes Modell sein
            
            return embedding_array.tobytes()
            
        except Exception as e:
            logger.error(f"Embedding-Generierung fehlgeschlagen: {e}")
            return None
    
    def embedding_to_vector(self, embedding_bytes: bytes) -> Optional[np.ndarray]:
        """Konvertiert gespeicherte bytes zurück zu numpy array"""
        if not embedding_bytes:
            return None
        try:
            return np.frombuffer(embedding_bytes, dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding-Konvertierung fehlgeschlagen: {e}")
            return None
    
    # =========================================================================
    # SEARCH
    # =========================================================================
    
    def search(
        self,
        query: str,
        user_id: int,
        limit: int = 20,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        folder: Optional[str] = None,
        account_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantische Suche über alle Emails eines Users.
        
        Args:
            query: Suchbegriff(e)
            user_id: User ID
            limit: Maximale Anzahl Ergebnisse
            threshold: Minimale Similarity (0.0 - 1.0)
            folder: Optional - nur in bestimmtem Ordner suchen
            account_id: Optional - nur in bestimmtem Account suchen
            
        Returns:
            Liste von Dicts mit:
            - email_id: RawEmail ID
            - similarity: Ähnlichkeitswert (0.0 - 1.0)
            - received_at: Empfangsdatum
            
            Sortiert nach Similarity (höchste zuerst)
        """
        import importlib
        models = importlib.import_module(".02_models", "src")
        
        if not self.ai_client:
            logger.error("Kein AI-Client für Suche")
            return []
        
        # 1. Query-Embedding generieren
        query_embedding = self.ai_client._get_embedding(query)
        if not query_embedding:
            logger.warning(f"Konnte kein Embedding für Query '{query}' generieren")
            return []
        
        query_vec = np.array(query_embedding, dtype=np.float32)
        
        # 2. Emails mit Embeddings laden
        email_query = self.db.query(models.RawEmail).filter(
            models.RawEmail.user_id == user_id,
            models.RawEmail.email_embedding.isnot(None),
            models.RawEmail.deleted_at.is_(None),
            models.RawEmail.deleted_verm.is_(False)
        )
        
        # Optionale Filter
        if folder:
            email_query = email_query.filter(models.RawEmail.imap_folder == folder)
        if account_id:
            email_query = email_query.filter(models.RawEmail.mail_account_id == account_id)
        
        emails = email_query.all()
        
        if not emails:
            logger.info(f"Keine Emails mit Embeddings für User {user_id}")
            return []
        
        # 3. Similarity berechnen
        results = []
        for email in emails:
            email_vec = self.embedding_to_vector(email.email_embedding)
            if email_vec is None:
                continue
            
            similarity = self._cosine_similarity(query_vec, email_vec)
            
            if similarity >= threshold:
                results.append({
                    'email_id': email.id,
                    'similarity': float(similarity),
                    'received_at': email.received_at.isoformat() if email.received_at else None,
                    'imap_folder': email.imap_folder,
                    'mail_account_id': email.mail_account_id,
                    'thread_id': email.thread_id
                })
        
        # 4. Nach Similarity sortieren (höchste zuerst)
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        # 5. Limit anwenden
        results = results[:limit]
        
        logger.info(
            f"Semantic Search '{query}': {len(results)} Ergebnisse "
            f"(von {len(emails)} Emails mit Embeddings)"
        )
        
        return results
    
    def search_similar_to_email(
        self,
        email_id: int,
        user_id: int,
        limit: int = 10,
        threshold: float = HIGH_SIMILARITY_THRESHOLD
    ) -> List[Dict[str, Any]]:
        """
        Findet ähnliche Emails zu einer gegebenen Email.
        
        Args:
            email_id: ID der Referenz-Email
            user_id: User ID (Sicherheitscheck)
            limit: Maximale Anzahl Ergebnisse
            threshold: Minimale Similarity (höher für "ähnliche Emails")
            
        Returns:
            Liste ähnlicher Emails (ohne die Referenz-Email selbst)
        """
        import importlib
        models = importlib.import_module(".02_models", "src")
        
        # Referenz-Email laden
        ref_email = self.db.query(models.RawEmail).filter_by(
            id=email_id,
            user_id=user_id
        ).first()
        
        if not ref_email or not ref_email.email_embedding:
            logger.warning(f"Email {email_id} nicht gefunden oder ohne Embedding")
            return []
        
        ref_vec = self.embedding_to_vector(ref_email.email_embedding)
        if ref_vec is None:
            return []
        
        # Alle anderen Emails mit Embeddings laden
        emails = self.db.query(models.RawEmail).filter(
            models.RawEmail.user_id == user_id,
            models.RawEmail.id != email_id,  # Nicht sich selbst
            models.RawEmail.email_embedding.isnot(None),
            models.RawEmail.deleted_at.is_(None)
        ).all()
        
        # Similarity berechnen
        results = []
        for email in emails:
            email_vec = self.embedding_to_vector(email.email_embedding)
            if email_vec is None:
                continue
            
            similarity = self._cosine_similarity(ref_vec, email_vec)
            
            if similarity >= threshold:
                results.append({
                    'email_id': email.id,
                    'similarity': float(similarity),
                    'received_at': email.received_at.isoformat() if email.received_at else None,
                    'thread_id': email.thread_id
                })
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]
    
    # =========================================================================
    # HELPER
    # =========================================================================
    
    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """
        Berechnet Cosine Similarity zwischen zwei Vektoren.
        
        Returns:
            Wert zwischen -1.0 und 1.0 (für normalisierte Embeddings meist 0.0 - 1.0)
        """
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_embedding_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Statistiken über Embedding-Coverage für einen User.
        
        Returns:
            {
                'total_emails': 150,
                'with_embedding': 120,
                'without_embedding': 30,
                'coverage_percent': 80.0,
                'embedding_model': 'all-minilm:22m'
            }
        """
        import importlib
        models = importlib.import_module(".02_models", "src")
        
        total = self.db.query(models.RawEmail).filter(
            models.RawEmail.user_id == user_id,
            models.RawEmail.deleted_at.is_(None)
        ).count()
        
        with_embedding = self.db.query(models.RawEmail).filter(
            models.RawEmail.user_id == user_id,
            models.RawEmail.email_embedding.isnot(None),
            models.RawEmail.deleted_at.is_(None)
        ).count()
        
        return {
            'total_emails': total,
            'with_embedding': with_embedding,
            'without_embedding': total - with_embedding,
            'coverage_percent': round((with_embedding / total * 100) if total > 0 else 0, 1),
            'embedding_model': EMBEDDING_MODEL
        }


# =============================================================================
# HELPER FUNCTION für Background Jobs
# =============================================================================

def generate_embedding_for_email(
    subject: str,
    body: str,
    ai_client = None
) -> Tuple[Optional[bytes], Optional[str], Optional[datetime]]:
    """
    Standalone-Funktion für Embedding-Generierung (für Background Jobs).
    
    Args:
        subject: Email-Betreff (Klartext!)
        body: Email-Body (Klartext!)
        ai_client: Optional AI Client, wird erstellt falls None
        
    Returns:
        Tuple von (embedding_bytes, model_name, generated_at)
        oder (None, None, None) bei Fehler
    """
    if ai_client is None:
        try:
            import importlib
            ai_module = importlib.import_module(".03_ai_client", "src")
            ai_client = ai_module.LocalOllamaClient(model=EMBEDDING_MODEL)
        except Exception as e:
            logger.warning(f"Konnte AI-Client nicht erstellen: {e}")
            return None, None, None
    
    service = SemanticSearchService(ai_client=ai_client)
    embedding_bytes = service.generate_embedding(subject, body)
    
    if embedding_bytes:
        return embedding_bytes, EMBEDDING_MODEL, datetime.now(UTC)
    
    return None, None, None
