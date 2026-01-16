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
    Generiert Embedding aus Subject + Body mit Chunking + Normalisierung.
    
    WICHTIG: Aufrufen BEVOR verschlüsselt wird (Klartext nötig)!
    
    BUGFIX (03.01.2026): Nutzt LocalOllamaClient._get_embedding() MIT Chunking
    für lange Emails (>512 tokens), aber normalisiert am Ende für konsistente
    Similarity mit Tag-Embeddings (die auch normalisiert sind).
    
    Args:
        subject: Email-Betreff (Klartext)
        body: Email-Body (Klartext)
        ai_client: AI Client mit _get_embedding() Methode (LocalOllamaClient)
        max_body_length: Maximale Body-Länge für Embedding
        model_name: Optional - Name des verwendeten Models (z.B. "all-minilm:22m")
        
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
        
        # BUGFIX 2026-01-14: Mindestlänge prüfen um sinnlose Embeddings zu vermeiden
        # Test-Mails mit nur Signatur haben ~500 Zeichen aber keinen Inhalt
        MIN_MEANINGFUL_LENGTH = 50
        if len(text) < MIN_MEANINGFUL_LENGTH:
            logger.debug(f"Text zu kurz ({len(text)} < {MIN_MEANINGFUL_LENGTH} chars), kein Embedding generiert")
            return None, None, None
        
        logger.info(f"📝 Generiere Embedding für Text ({len(text)} Zeichen)...")
        
        # Embedding mit Chunking generieren (für lange Emails wichtig!)
        embedding_list = ai_client._get_embedding(text)
        
        if not embedding_list:
            logger.warning("❌ AI-Client lieferte kein Embedding")
            return None, None, None
        
        # Zu numpy array konvertieren
        embedding_array = np.array(embedding_list, dtype=np.float32)
        
        # 🆕 WICHTIG: Normalisieren für konsistente Similarity mit Tag-Embeddings!
        # Tag-Embeddings sind von Ollama normalisiert (Norm = 1.0)
        # Email-Embeddings waren mean-pooled (Norm < 1.0) → Similarity war zu niedrig!
        norm = np.linalg.norm(embedding_array)
        if norm > 0:
            embedding_array = embedding_array / norm
            logger.debug(f"📊 Email-Embedding normalisiert: {norm:.4f} → 1.0")
        else:
            logger.warning("⚠️  Email-Embedding hat Norm = 0, keine Normalisierung möglich")
        
        # Als bytes speichern
        embedding_array = embedding_array.astype(np.float32)
        
        # Validierung: Check gegen erste Email im System (wenn vorhanden)
        dimension = embedding_array.shape[0]
        
        # Log Dimension für Debugging
        logger.info(f"✅ Embedding generiert: {dimension} Dimensionen, {len(embedding_array.tobytes())} bytes, Norm = 1.0")
        
        # WARNING nur beim ersten Mal pro Session (nicht bei jedem Embedding)
        # Cache: Track ob bereits gewarnt wurde für diese Dimension
        if not hasattr(generate_embedding_for_email, '_dimension_warned'):
            generate_embedding_for_email._dimension_warned = set()
        
        if dimension != DEFAULT_EMBEDDING_DIM and dimension not in generate_embedding_for_email._dimension_warned:
            logger.warning(
                f"⚠️  Embedding-Dimension {dimension} weicht von Default ({DEFAULT_EMBEDDING_DIM}) ab. "
                f"Stelle sicher, dass ALLE Emails mit dem gleichen Model embedded werden!"
            )
            generate_embedding_for_email._dimension_warned.add(dimension)
        
        # Model-Name: Verwende übergebenen Namen oder hole von Client
        actual_model = model_name
        if not actual_model:
            # Hole Model-Name vom Client
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
        try:
            # 0. Ermittle das Embedding-Model aus der Datenbank (von Emails)
            sample_email = (
                self.db.query(models.RawEmail)
                .filter(
                    models.RawEmail.user_id == user_id,
                    models.RawEmail.email_embedding.isnot(None),
                    models.RawEmail.embedding_model.isnot(None)
                )
                .first()
            )
            
            if not sample_email:
                logger.warning("Keine Emails mit Embeddings gefunden für Semantic Search")
                return []
            
            embedding_model = sample_email.embedding_model
            logger.info(f"🔍 Semantic Search: Nutze Embedding-Model '{embedding_model}' (von Emails)")
            
            # AI-Client mit dem richtigen Model erstellen
            import importlib
            ai_client_module = importlib.import_module("src.03_ai_client")
            query_client = ai_client_module.LocalOllamaClient(
                model=embedding_model,
                base_url="http://127.0.0.1:11434"
            )
            
            # 1. Query-Embedding generieren MIT RICHTIGEM MODEL!
            query_embedding_list = query_client._get_embedding(query)
            
            if not query_embedding_list:
                logger.warning("Query-Embedding konnte nicht generiert werden")
                return []
            
            query_vector = np.array(query_embedding_list, dtype=np.float32)
            
            # Normalisieren für konsistente Similarity
            norm = np.linalg.norm(query_vector)
            if norm > 0:
                query_vector = query_vector / norm
                logger.debug(f"📊 Query-Embedding normalisiert: {norm:.4f} → 1.0")
            
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
        threshold: float = HIGH_SIMILARITY_THRESHOLD,
        account_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Findet ähnliche Emails zu einer gegebenen Email.
        
        Args:
            email_id: ID der Referenz-Email
            limit: Maximale Anzahl ähnlicher Emails
            threshold: Minimale Similarity (höher als bei Search!)
            account_id: Optional - nur in bestimmtem Account suchen
            
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
            query_obj = (
                self.db.query(models.RawEmail)
                .filter(
                    models.RawEmail.user_id == ref_email.user_id,
                    models.RawEmail.id != email_id,
                    models.RawEmail.deleted_at.is_(None),
                    models.RawEmail.email_embedding.isnot(None)
                )
            )
            
            # Account-Filter: Default ist gleicher Account wie Referenz-Email
            if account_id is None:
                # Standard: nur gleicher Account
                query_obj = query_obj.filter(models.RawEmail.mail_account_id == ref_email.mail_account_id)
            elif account_id > 0:
                # Explizit angegebener Account
                query_obj = query_obj.filter(models.RawEmail.mail_account_id == account_id)
            # Wenn account_id == -1: alle Accounts (kein Filter)
            
            other_emails = query_obj.all()
            
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
