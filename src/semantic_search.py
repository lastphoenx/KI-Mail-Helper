"""
Semantic Search Service (Phase 17)
==================================

Vektorbasierte Email-Suche mit Embeddings.

Features:
- Embedding-Generierung beim Email-Fetch (Klartext verfügbar!)
- Cosine Similarity für semantische Ähnlichkeit
- "Budget" findet auch "Kostenplanung", "Finanzübersicht"
- Zero-Knowledge kompatibel (Embeddings nicht reversibel)

Usage:
    from src.semantic_search import SemanticSearchService, generate_embedding_for_email
    
    # Embedding generieren (beim Fetch)
    embedding_bytes, model, timestamp = generate_embedding_for_email(
        subject="Betreff",
        body="Body-Text",
        ai_client=ollama_client
    )
    
    # Suchen
    service = SemanticSearchService(db_session, ai_client)
    results = service.search("Projektbudget", user_id=1, limit=20)
"""

import logging
import numpy as np
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
import importlib

models = importlib.import_module(".02_models", "src")

logger = logging.getLogger(__name__)

# Default Embedding-Dimension für all-minilm:22m
# WICHTIG: Alle Emails müssen vom gleichen Model embedded sein!
DEFAULT_EMBEDDING_DIM = 384
EMBEDDING_MODEL = "all-minilm:22m"

# Similarity-Schwellenwert (0.0 - 1.0)
DEFAULT_SIMILARITY_THRESHOLD = 0.25
HIGH_SIMILARITY_THRESHOLD = 0.5


def get_embedding_dim_from_bytes(embedding_bytes: bytes) -> int:
    """Berechnet Dimension aus Bytes (float32 = 4 bytes)"""
    if not embedding_bytes:
        return 0
    return len(embedding_bytes) // 4


def generate_embedding_for_email(
    subject: str,
    body: str,
    ai_client,
    max_body_length: int = 1000,  # Erhöht von 500 → 1000 für besseren Context
    model_name: Optional[str] = None
) -> Tuple[Optional[bytes], Optional[str], Optional[datetime]]:
    """
    Generiert Embedding aus Subject + Body.
    
    WICHTIG: Aufrufen BEVOR verschlüsselt wird (Klartext nötig)!
    
    Args:
        subject: Email-Betreff (Klartext)
        body: Email-Body (Klartext)
        ai_client: AI Client mit _get_embedding() Methode
        max_body_length: Maximale Body-Länge für Embedding
        model_name: Optional - Name des verwendeten Models (z.B. "text-embedding-3-large")
        
    Returns:
        Tuple (embedding_bytes, model_name, timestamp)
        - embedding_bytes: bytes oder None
        - model_name: str oder None
        - timestamp: datetime oder None
    """
    if not ai_client:
        logger.debug("Kein AI-Client für Embedding-Generierung")
        return None, None, None
    
    try:
        # Text für Embedding kombinieren
        # Subject ist wichtiger, daher zuerst
        text = f"{subject or ''}\n{(body or '')[:max_body_length]}"
        text = text.strip()
        
        if not text:
            logger.debug("Leerer Text, kein Embedding generiert")
            return None, None, None
        
        logger.info(f"📝 Generiere Embedding für Text ({len(text)} Zeichen)...")
        
        # Embedding von AI-Client holen
        embedding_list = ai_client._get_embedding(text)
        
        if not embedding_list:
            logger.warning("❌ AI-Client lieferte kein Embedding")
            return None, None, None
        
        # Zu numpy array konvertieren und als bytes speichern
        embedding_array = np.array(embedding_list, dtype=np.float32)
        
        # Validierung: Check gegen erste Email im System (wenn vorhanden)
        dimension = embedding_array.shape[0]
        
        # Log Dimension für Debugging
        logger.info(f"✅ Embedding generiert: {dimension} Dimensionen, {len(embedding_array.tobytes())} bytes")
        
        # WARNING nur wenn stark abweicht von DEFAULT
        if dimension != DEFAULT_EMBEDDING_DIM:
            logger.warning(
                f"⚠️  Embedding-Dimension {dimension} weicht von Default ({DEFAULT_EMBEDDING_DIM}) ab. "
                f"Stelle sicher, dass ALLE Emails mit dem gleichen Model embedded werden!"
            )
        
        # Model-Name: Verwende übergebenen Namen oder versuche von Client zu holen
        actual_model = model_name
        if not actual_model:
            # Versuche Model-Name vom Client zu holen
            if hasattr(ai_client, 'model'):
                actual_model = ai_client.model
            elif hasattr(ai_client, '_model'):
                actual_model = ai_client._model
            else:
                actual_model = EMBEDDING_MODEL  # Fallback
        
        return (
            embedding_array.tobytes(),
            actual_model,
            datetime.now(UTC)
        )
        
    except Exception as e:
        logger.warning(f"Embedding-Generierung fehlgeschlagen: {e}")
        return None, None, None


class SemanticSearchService:
    """Service für semantische Email-Suche"""
    
    def __init__(self, db_session: Session, ai_client=None):
        """
        Args:
            db_session: SQLAlchemy Session für DB-Queries
            ai_client: AI Client mit _get_embedding() Methode (z.B. LocalOllamaClient)
        """
        self.db = db_session
        self.ai_client = ai_client
    
    def embedding_to_vector(self, embedding_bytes: bytes) -> Optional[np.ndarray]:
        """Konvertiert gespeicherte bytes zurück zu numpy array"""
        if not embedding_bytes:
            return None
        try:
            return np.frombuffer(embedding_bytes, dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding-Konvertierung fehlgeschlagen: {e}")
            return None
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Berechnet Cosine Similarity zwischen zwei Vektoren"""
        try:
            # Dimension-Check: Vektoren müssen gleiche Länge haben!
            if vec1.shape[0] != vec2.shape[0]:
                logger.error(
                    f"❌ Dimension mismatch: vec1={vec1.shape[0]}, vec2={vec2.shape[0]}. "
                    f"Semantic Search funktioniert nicht zwischen unterschiedlichen Embedding-Models!"
                )
                return 0.0
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
        except Exception as e:
            logger.error(f"Cosine Similarity Berechnung fehlgeschlagen: {e}")
            return 0.0
    
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
            Liste von Dicts mit Email-Daten + similarity_score
        """
        if not self.ai_client:
            logger.warning("Kein AI-Client für Semantic Search")
            return []
        
        try:
            # 1. Query-Embedding generieren
            query_embedding_list = self.ai_client._get_embedding(query)
            
            if not query_embedding_list:
                logger.warning("Query-Embedding konnte nicht generiert werden")
                return []
            
            query_vector = np.array(query_embedding_list, dtype=np.float32)
            
            # 2. Alle Emails mit Embeddings laden
            query_obj = (
                self.db.query(models.RawEmail)
                .filter(
                    models.RawEmail.user_id == user_id,
                    models.RawEmail.deleted_at.is_(None),
                    models.RawEmail.email_embedding.isnot(None)
                )
            )
            
            if folder:
                query_obj = query_obj.filter(models.RawEmail.imap_folder == folder)
            
            if account_id:
                query_obj = query_obj.filter(models.RawEmail.mail_account_id == account_id)
            
            emails = query_obj.all()
            
            if not emails:
                logger.info("Keine Emails mit Embeddings gefunden")
                return []
            
            # 3. Cosine Similarity berechnen für alle Emails
            results = []
            
            for email in emails:
                email_vector = self.embedding_to_vector(email.email_embedding)
                
                if email_vector is None:
                    continue
                
                similarity = self.cosine_similarity(query_vector, email_vector)
                
                if similarity >= threshold:
                    results.append({
                        'id': email.id,
                        'encrypted_sender': email.encrypted_sender,
                        'encrypted_subject': email.encrypted_subject,
                        'received_at': email.received_at,
                        'imap_folder': email.imap_folder,
                        'mail_account_id': email.mail_account_id,
                        'similarity_score': round(similarity, 4),
                        'has_attachments': email.has_attachments,
                        'imap_is_seen': email.imap_is_seen,
                        'imap_is_flagged': email.imap_is_flagged
                    })
            
            # 4. Nach Similarity sortieren (höchste zuerst)
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            # 5. Limit anwenden
            results = results[:limit]
            
            logger.info(
                f"Semantic Search: '{query}' → {len(results)} Ergebnisse "
                f"(threshold={threshold}, total_emails={len(emails)})"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Semantic Search fehlgeschlagen: {e}")
            return []
    
    def find_similar(
        self,
        email_id: int,
        limit: int = 5,
        threshold: float = HIGH_SIMILARITY_THRESHOLD
    ) -> List[Dict[str, Any]]:
        """
        Findet ähnliche Emails zu einer gegebenen Email.
        
        Args:
            email_id: ID der Referenz-Email
            limit: Maximale Anzahl ähnlicher Emails
            threshold: Minimale Similarity (höher als bei Search!)
            
        Returns:
            Liste von ähnlichen Emails (sortiert nach Similarity)
        """
        try:
            # 1. Referenz-Email laden
            ref_email = self.db.query(models.RawEmail).filter_by(id=email_id).first()
            
            if not ref_email or not ref_email.email_embedding:
                logger.warning(f"Email {email_id} hat kein Embedding")
                return []
            
            ref_vector = self.embedding_to_vector(ref_email.email_embedding)
            
            if ref_vector is None:
                return []
            
            # 2. Alle anderen Emails des Users mit Embeddings
            other_emails = (
                self.db.query(models.RawEmail)
                .filter(
                    models.RawEmail.user_id == ref_email.user_id,
                    models.RawEmail.id != email_id,
                    models.RawEmail.deleted_at.is_(None),
                    models.RawEmail.email_embedding.isnot(None)
                )
                .all()
            )
            
            # 3. Similarity berechnen
            results = []
            
            for email in other_emails:
                email_vector = self.embedding_to_vector(email.email_embedding)
                
                if email_vector is None:
                    continue
                
                similarity = self.cosine_similarity(ref_vector, email_vector)
                
                if similarity >= threshold:
                    results.append({
                        'id': email.id,
                        'encrypted_sender': email.encrypted_sender,
                        'encrypted_subject': email.encrypted_subject,
                        'received_at': email.received_at,
                        'imap_folder': email.imap_folder,
                        'similarity_score': round(similarity, 4),
                        'thread_id': email.thread_id
                    })
            
            # 4. Sortieren und limitieren
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            results = results[:limit]
            
            logger.info(f"Similar Emails für {email_id}: {len(results)} gefunden")
            
            return results
            
        except Exception as e:
            logger.error(f"Find Similar fehlgeschlagen: {e}")
            return []
    
    def get_embedding_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Liefert Statistiken über Embeddings.
        
        Returns:
            Dict mit total, with_embedding, percentage
        """
        try:
            total = self.db.query(models.RawEmail).filter(
                models.RawEmail.user_id == user_id,
                models.RawEmail.deleted_at.is_(None)
            ).count()
            
            with_embedding = self.db.query(models.RawEmail).filter(
                models.RawEmail.user_id == user_id,
                models.RawEmail.deleted_at.is_(None),
                models.RawEmail.email_embedding.isnot(None)
            ).count()
            
            percentage = round(with_embedding / total * 100, 1) if total > 0 else 0
            
            return {
                'total': total,
                'with_embedding': with_embedding,
                'without_embedding': total - with_embedding,
                'percentage': percentage
            }
            
        except Exception as e:
            logger.error(f"Embedding Stats fehlgeschlagen: {e}")
            return {
                'total': 0,
                'with_embedding': 0,
                'without_embedding': 0,
                'percentage': 0
            }
