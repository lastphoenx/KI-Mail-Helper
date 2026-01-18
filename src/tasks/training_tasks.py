# src/tasks/training_tasks.py
"""
Celery Tasks für Hybrid Score-Learning (Personal Classifier Training).

Implementiert:
- train_personal_classifier: Async Training mit Redis Lock + Throttling
- Atomic Write für Crash-Safety
- Circuit-Breaker bei wiederholten Fehlern

Pattern kopiert aus:
- src/tasks/email_processing_tasks.py (Task-Struktur)
- src/train_classifier.py Zeile 128-199 (OnlineLearner.learn_from_correction)
- docs/HYBRID_SCORE_LEARNING.md Zeile 142-194 (Training Pipeline)
"""

from __future__ import annotations

import importlib
import logging
import os
import tempfile
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    joblib = None
    HAS_JOBLIB = False

try:
    from sklearn.linear_model import SGDClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.utils.class_weight import compute_sample_weight
    from sklearn.model_selection import cross_val_score, LeaveOneOut
    HAS_SKLEARN = True
except ImportError:
    SGDClassifier = None
    StandardScaler = None
    compute_sample_weight = None
    cross_val_score = None
    LeaveOneOut = None
    HAS_SKLEARN = False

try:
    import redis
    from redis.lock import Lock as RedisLock
    HAS_REDIS = True
except ImportError:
    redis = None
    RedisLock = None
    HAS_REDIS = False

from celery.exceptions import Reject

from src.celery_app import celery_app
from src.helpers.database import get_session_factory
from src.services.personal_classifier_service import (
    load_global_scaler,
    invalidate_classifier_cache,
    get_classifier_dir,
    CLASSIFIER_TYPES,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Training-Konfiguration
MIN_SAMPLES_PER_CLASS = 5
MAX_IMBALANCE_RATIO = 5.0
THROTTLE_MIN_SAMPLES = 5   # Min 5 neue Korrekturen seit letztem Training
THROTTLE_MIN_MINUTES = 5   # Min 5 Minuten seit letztem Training

# Classifier-spezifische Klassen
CLASSES_CONFIG = {
    "dringlichkeit": np.array([1, 2, 3]),      # 1=niedrig, 2=mittel, 3=hoch
    "wichtigkeit": np.array([1, 2, 3]),        # 1=niedrig, 2=mittel, 3=hoch
    "spam": np.array([0, 1]),                  # 0=kein Spam, 1=Spam
    "kategorie": np.array([0, 1, 2]),          # nur_information, aktion_erforderlich, dringend
}

# Redis Lock-Konfiguration
LOCK_TIMEOUT = 600         # 10 Minuten max
LOCK_BLOCKING_TIMEOUT = 0  # Non-blocking (sofort abbrechen wenn bereits gelockt)

# Circuit-Breaker
MAX_ERROR_COUNT = 3


# =============================================================================
# REDIS HELPER
# =============================================================================

def _get_redis_client() -> "redis.Redis":
    """Verbindet zu Redis aus CELERY_BROKER_URL.
    
    Returns:
        redis.Redis Client
        
    Raises:
        RuntimeError: Wenn redis nicht installiert oder nicht erreichbar
    """
    if not HAS_REDIS:
        raise RuntimeError("redis-py nicht installiert")
    
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    
    # Parse URL: redis://host:port/db
    # Beispiel: redis://localhost:6379/1
    if broker_url.startswith("redis://"):
        broker_url = broker_url[8:]  # Remove "redis://"
    
    parts = broker_url.split("/")
    host_port = parts[0]
    db = int(parts[1]) if len(parts) > 1 else 0
    
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 6379
    
    return redis.Redis(host=host, port=port, db=db, decode_responses=False)


# =============================================================================
# PATH HELPERS
# =============================================================================

def _get_personal_classifier_path(user_id: int, classifier_type: str) -> Path:
    """Gibt Pfad für Personal Classifier zurück.
    
    Pattern: classifiers/per_user/user_{id}/{type}_classifier.pkl
    """
    return get_classifier_dir() / "per_user" / f"user_{user_id}" / f"{classifier_type}_classifier.pkl"


def _ensure_personal_classifier_dir(user_id: int) -> Path:
    """Erstellt Verzeichnis für Personal Classifier falls nicht vorhanden."""
    user_dir = get_classifier_dir() / "per_user" / f"user_{user_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


# =============================================================================
# THROTTLING
# =============================================================================

def _should_trigger_training(
    user_id: int,
    classifier_type: str,
    db,
    models
) -> Tuple[bool, str]:
    """Prüft beide Throttling-Bedingungen.
    
    Bedingung 1: >= 5 neue Korrekturen seit letztem Training
    Bedingung 2: Letztes Training >= 5 Minuten her
    
    Args:
        user_id: User ID
        classifier_type: Classifier-Typ
        db: SQLAlchemy Session
        models: Models-Modul
        
    Returns:
        (should_train, reason)
    """
    # Lade Metadata
    metadata = db.query(models.ClassifierMetadata).filter_by(
        user_id=user_id,
        classifier_type=classifier_type
    ).first()
    
    # DEBUG: Log was gefunden wurde
    logger.info(f"🔍 [Throttle Check] user={user_id}, type={classifier_type}, metadata={metadata}")
    
    # Kein Metadata = noch nie trainiert → Training erlaubt
    if not metadata:
        logger.info(f"✅ [Throttle Check] Keine Metadata → first_training erlaubt")
        return (True, "first_training")
    
    logger.info(f"📋 [Throttle Check] Metadata gefunden: error_count={metadata.error_count}, last_trained={metadata.last_trained_at}")
    
    # Circuit-Breaker Check
    if metadata.error_count >= MAX_ERROR_COUNT:
        return (False, f"circuit_breaker_open (errors={metadata.error_count})")
    
    # Bedingung 2: Letztes Training >= 5 Minuten her?
    if metadata.last_trained_at:
        min_time = datetime.now(UTC) - timedelta(minutes=THROTTLE_MIN_MINUTES)
        if metadata.last_trained_at > min_time:
            return (False, f"throttle_time (trained {(datetime.now(UTC) - metadata.last_trained_at).seconds}s ago)")
    
    # Bedingung 1: >= 5 neue Korrekturen seit letztem Training
    # Zähle Korrekturen mit correction_timestamp > last_trained_at
    override_field = _get_override_field(classifier_type)
    if not override_field:
        return (False, f"unknown_classifier_type: {classifier_type}")
    
    # ProcessedEmail hat kein user_id - muss über RawEmail joinen
    query = db.query(models.ProcessedEmail).join(
        models.RawEmail, models.ProcessedEmail.raw_email_id == models.RawEmail.id
    ).filter(
        models.RawEmail.user_id == user_id,
        getattr(models.ProcessedEmail, override_field) != None
    )
    
    if metadata.last_trained_at:
        query = query.filter(
            getattr(models.ProcessedEmail, 'correction_timestamp') > metadata.last_trained_at
        )
    
    new_corrections = query.count()
    
    if new_corrections < THROTTLE_MIN_SAMPLES:
        return (False, f"throttle_samples (only {new_corrections} new corrections)")
    
    return (True, f"ready ({new_corrections} new corrections)")


def _get_override_field(classifier_type: str) -> Optional[str]:
    """Gibt den Override-Feldnamen für einen Classifier-Typ zurück."""
    field_map = {
        "dringlichkeit": "user_override_dringlichkeit",
        "wichtigkeit": "user_override_wichtigkeit",
        "spam": "user_override_spam_flag",
        "kategorie": "user_override_kategorie",
    }
    return field_map.get(classifier_type)


# =============================================================================
# DATA COLLECTION
# =============================================================================

def _get_training_data(
    user_id: int,
    classifier_type: str,
    db,
    models
) -> Tuple[np.ndarray, np.ndarray]:
    """Sammelt Trainingsdaten für einen User.
    
    Sammelt alle ProcessedEmails wo:
    - user_id = user_id
    - user_override_{classifier_type} IS NOT NULL
    
    Features: Embedding (384) aus RawEmail
    Labels: user_override_{classifier_type}
    
    Args:
        user_id: User ID
        classifier_type: Classifier-Typ
        db: SQLAlchemy Session
        models: Models-Modul
        
    Returns:
        (X, y) mit X.shape = (n, 384), y.shape = (n,)
    """
    override_field = _get_override_field(classifier_type)
    if not override_field:
        raise ValueError(f"Unbekannter classifier_type: {classifier_type}")
    
    # Query: Alle ProcessedEmails mit Override für diesen User
    # ProcessedEmail hat kein user_id - muss über RawEmail joinen
    query = db.query(models.ProcessedEmail).join(
        models.RawEmail, models.ProcessedEmail.raw_email_id == models.RawEmail.id
    ).filter(
        models.RawEmail.user_id == user_id,
        getattr(models.ProcessedEmail, override_field) != None
    ).all()
    
    if not query:
        return np.array([]), np.array([])
    
    embeddings = []
    labels = []
    
    for processed_email in query:
        raw_email = processed_email.raw_email
        if not raw_email:
            continue
        
        # Embedding aus RawEmail
        embedding = raw_email.embedding
        if not embedding:
            logger.debug(f"Kein Embedding für RawEmail {raw_email.id}")
            continue
        
        # Parse Embedding (kann JSON-String oder Liste sein)
        if isinstance(embedding, str):
            import json
            try:
                embedding = json.loads(embedding)
            except json.JSONDecodeError:
                logger.warning(f"Ungültiges Embedding für RawEmail {raw_email.id}")
                continue
        
        if not isinstance(embedding, (list, np.ndarray)):
            logger.warning(f"Unerwarteter Embedding-Typ für RawEmail {raw_email.id}: {type(embedding)}")
            continue
        
        embeddings.append(np.array(embedding))
        
        # Label extrahieren
        label_value = getattr(processed_email, override_field)
        
        # Spam: Boolean → int
        if classifier_type == "spam":
            labels.append(1 if label_value else 0)
        else:
            labels.append(int(label_value))
    
    if not embeddings:
        return np.array([]), np.array([])
    
    return np.array(embeddings), np.array(labels)


# =============================================================================
# VALIDATION
# =============================================================================

def _validate_training_data(
    y: np.ndarray,
    classifier_type: str,
    min_per_class: int = MIN_SAMPLES_PER_CLASS
) -> Tuple[bool, str]:
    """Validiert Trainingsdaten.
    
    Prüft:
    1. Mindestens min_per_class Samples pro Klasse
    2. Max Imbalance-Ratio 5:1
    
    Args:
        y: Labels
        classifier_type: Für Klassen-Lookup
        min_per_class: Minimum Samples pro Klasse
        
    Returns:
        (is_valid, reason)
    """
    if len(y) == 0:
        return (False, "no_samples")
    
    expected_classes = CLASSES_CONFIG.get(classifier_type, np.array([]))
    
    # Zähle Samples pro Klasse
    unique, counts = np.unique(y, return_counts=True)
    class_counts = dict(zip(unique, counts))
    
    # Check: Mindestens 2 Klassen vorhanden?
    if len(unique) < 2:
        return (False, f"only_one_class ({unique[0]})")
    
    # Check: Minimum Samples pro Klasse
    for cls in unique:
        if class_counts[cls] < min_per_class:
            return (False, f"insufficient_samples_class_{cls} ({class_counts[cls]}/{min_per_class})")
    
    # Check: Imbalance-Ratio
    max_count = max(counts)
    min_count = min(counts)
    ratio = max_count / min_count if min_count > 0 else float('inf')
    
    if ratio > MAX_IMBALANCE_RATIO:
        return (False, f"imbalance_ratio ({ratio:.1f}:1 > {MAX_IMBALANCE_RATIO}:1)")
    
    return (True, f"valid ({len(y)} samples, {len(unique)} classes)")


# =============================================================================
# TRAINING
# =============================================================================

def _train_classifier(
    X: np.ndarray,
    y: np.ndarray,
    classifier_type: str,
    existing_clf: Optional[SGDClassifier] = None
) -> SGDClassifier:
    """Trainiert oder updated einen SGDClassifier.
    
    CRITICAL: fit() für neue Instanzen, partial_fit() für Updates!
    
    Args:
        X: Skalierte Features (n, 384)
        y: Labels
        classifier_type: Für classes-Parameter
        existing_clf: Existierender Classifier für partial_fit, oder None für fit
        
    Returns:
        Trainierter SGDClassifier
    """
    if not HAS_SKLEARN:
        raise RuntimeError("scikit-learn nicht installiert")
    
    classes = CLASSES_CONFIG.get(classifier_type, np.array([1, 2, 3]))
    
    # Sample-Weights für Class-Balancing
    sample_weights = compute_sample_weight('balanced', y)
    
    if existing_clf is not None:
        # UPDATE: partial_fit mit classes Parameter
        existing_clf.partial_fit(X, y, classes=classes, sample_weight=sample_weights)
        logger.info(f"📚 partial_fit(): Updated existierenden Classifier")
        return existing_clf
    else:
        # NEU: fit() für neue Instanz
        clf = SGDClassifier(
            loss='log_loss',
            warm_start=True,
            random_state=42,
            max_iter=1000,
            tol=1e-3
        )
        clf.fit(X, y, sample_weight=sample_weights)
        logger.info(f"📚 fit(): Neuer Classifier trainiert")
        return clf


# =============================================================================
# ATOMIC SAVE
# =============================================================================

def _atomic_save_model(clf: SGDClassifier, path: Path) -> None:
    """Speichert Model atomar (Crash-Safety).
    
    Pattern:
    1. Schreibe zu temp-Datei im selben Verzeichnis
    2. os.rename() (POSIX-atomar)
    
    Args:
        clf: Trainierter Classifier
        path: Zielpfad
    """
    if not HAS_JOBLIB:
        raise RuntimeError("joblib nicht installiert")
    
    # Temp-Datei im selben Verzeichnis (für atomares rename)
    temp_path = path.with_suffix('.pkl.tmp')
    
    try:
        # 1. Schreibe zu temp
        joblib.dump(clf, temp_path)
        
        # 2. Atomares rename (POSIX)
        os.rename(temp_path, path)
        
        logger.debug(f"💾 Atomic save: {path}")
        
    except Exception as e:
        # Cleanup temp file
        if temp_path.exists():
            temp_path.unlink()
        raise


# =============================================================================
# ACCURACY
# =============================================================================

def _compute_accuracy(clf: SGDClassifier, X: np.ndarray, y: np.ndarray) -> float:
    """Berechnet Accuracy mit Cross-Validation.
    
    - < 20 Samples: Leave-One-Out CV
    - >= 20 Samples: 5-Fold CV
    
    Args:
        clf: Trainierter Classifier
        X: Features
        y: Labels
        
    Returns:
        Accuracy (0.0-1.0)
    """
    if not HAS_SKLEARN:
        return 0.0
    
    n_samples = len(y)
    
    try:
        if n_samples < 20:
            # Leave-One-Out für kleine Datasets
            cv = LeaveOneOut()
            scores = cross_val_score(clf, X, y, cv=cv, scoring='accuracy')
        else:
            # 5-Fold CV für größere Datasets
            n_folds = min(5, n_samples)
            scores = cross_val_score(clf, X, y, cv=n_folds, scoring='accuracy')
        
        return float(np.mean(scores))
    
    except Exception as e:
        logger.warning(f"Accuracy-Berechnung fehlgeschlagen: {e}")
        # Fallback: Simple Training Accuracy
        return float(clf.score(X, y))


# =============================================================================
# METADATA
# =============================================================================

def _update_classifier_metadata(
    user_id: int,
    classifier_type: str,
    updates: Dict[str, Any],
    db,
    models
) -> None:
    """Aktualisiert oder erstellt ClassifierMetadata.
    
    Args:
        user_id: User ID
        classifier_type: Classifier-Typ
        updates: Dict mit Feldern zum Aktualisieren
        db: SQLAlchemy Session
        models: Models-Modul
    """
    metadata = db.query(models.ClassifierMetadata).filter_by(
        user_id=user_id,
        classifier_type=classifier_type
    ).first()
    
    if not metadata:
        # Erstelle neuen Eintrag
        metadata = models.ClassifierMetadata(
            user_id=user_id,
            classifier_type=classifier_type,
            **updates
        )
        db.add(metadata)
    else:
        # Update existierenden Eintrag
        for key, value in updates.items():
            setattr(metadata, key, value)
    
    db.commit()
    logger.debug(f"📊 Metadata updated: {user_id}/{classifier_type}")


def _increment_error_count(
    user_id: int,
    classifier_type: str,
    db,
    models
) -> int:
    """Inkrementiert error_count und prüft Circuit-Breaker.
    
    Returns:
        Neuer error_count
    """
    metadata = db.query(models.ClassifierMetadata).filter_by(
        user_id=user_id,
        classifier_type=classifier_type
    ).first()
    
    if not metadata:
        metadata = models.ClassifierMetadata(
            user_id=user_id,
            classifier_type=classifier_type,
            error_count=1,
            is_active=True
        )
        db.add(metadata)
    else:
        metadata.error_count += 1
        if metadata.error_count >= MAX_ERROR_COUNT:
            metadata.is_active = False
            logger.error(
                f"⚠️ Circuit-Breaker OPEN: {user_id}/{classifier_type} "
                f"deaktiviert nach {metadata.error_count} Fehlern"
            )
    
    try:
        db.commit()
    except Exception as e:
        logger.error(f"❌ Commit failed for {user_id}/{classifier_type}: {e}")
        db.rollback()
        raise
    
    return metadata.error_count


def _get_next_version(user_id: int, classifier_type: str, db, models) -> int:
    """Gibt nächste Version für Classifier zurück."""
    metadata = db.query(models.ClassifierMetadata).filter_by(
        user_id=user_id,
        classifier_type=classifier_type
    ).first()
    
    if metadata and metadata.model_version:
        return metadata.model_version + 1
    return 1


# =============================================================================
# MAIN CELERY TASK
# =============================================================================

@celery_app.task(
    bind=True,
    name="tasks.training.train_personal_classifier",
    max_retries=3,
    default_retry_delay=60,
    time_limit=600,        # 10 Min hard limit
    soft_time_limit=480,   # 8 Min soft limit
    acks_late=True,
    reject_on_worker_lost=True
)
def train_personal_classifier(
    self,
    user_id: int,
    classifier_type: str,
    force: bool = False
) -> Dict[str, Any]:
    """
    Trainiert Personal Classifier mit Online-Learning.
    
    10 Schritte aus HYBRID_SCORE_LEARNING.md:
    1. Redis Lock akquirieren
    2. Throttling prüfen
    3. Daten sammeln
    4. Validierung
    5. Scaler transform
    6. Sample-Weights (in _train_classifier)
    7. fit/partial_fit Decision
    8. Atomic Write
    9. Accuracy compute
    10. Metadata + Cache
    
    Args:
        user_id: User ID
        classifier_type: 'dringlichkeit' | 'wichtigkeit' | 'spam' | 'kategorie'
        force: Wenn True, ignoriere Throttling + Min-Samples
    
    Returns:
        dict mit status, samples, accuracy, version
    """
    # Validierung
    if classifier_type not in CLASSIFIER_TYPES:
        raise Reject(f"Ungültiger classifier_type: {classifier_type}", requeue=False)
    
    if not HAS_SKLEARN or not HAS_JOBLIB:
        raise Reject("scikit-learn oder joblib nicht installiert", requeue=False)
    
    logger.info(
        f"🎓 [Task {self.request.id}] Training Personal Classifier: "
        f"user={user_id}, type={classifier_type}, force={force}"
    )
    
    # Lazy imports um Circular Imports zu vermeiden
    models = importlib.import_module(".02_models", "src")
    SessionFactory = get_session_factory()
    
    db = SessionFactory()
    redis_lock = None
    
    try:
        # =================================================================
        # STEP 1: Redis Lock akquirieren (Non-blocking)
        # =================================================================
        lock_key = f"train:{user_id}:{classifier_type}"
        
        try:
            redis_client = _get_redis_client()
            redis_lock = RedisLock(
                redis_client,
                lock_key,
                timeout=LOCK_TIMEOUT,
                blocking_timeout=LOCK_BLOCKING_TIMEOUT
            )
            
            if not redis_lock.acquire(blocking=False):
                logger.info(f"🔒 Training bereits aktiv für {user_id}/{classifier_type}")
                return {"status": "skipped", "reason": "already_training"}
            
        except Exception as e:
            logger.warning(f"Redis Lock fehlgeschlagen, fahre ohne Lock fort: {e}")
            redis_lock = None
        
        try:
            # =============================================================
            # STEP 2: Throttling prüfen
            # =============================================================
            if not force:
                should_train, reason = _should_trigger_training(
                    user_id, classifier_type, db, models
                )
                if not should_train:
                    logger.debug(f"⏳ Throttling: {reason}")
                    return {"status": "skipped", "reason": reason}
            
            # =============================================================
            # STEP 3: Daten sammeln
            # =============================================================
            X, y = _get_training_data(user_id, classifier_type, db, models)
            
            if len(y) == 0:
                logger.warning(f"Keine Trainingsdaten für {user_id}/{classifier_type}")
                return {"status": "skipped", "reason": "no_training_data"}
            
            logger.info(f"📊 Gesammelt: {len(y)} Samples für {classifier_type}")
            
            # =============================================================
            # STEP 4: Validierung
            # =============================================================
            if not force:
                is_valid, reason = _validate_training_data(y, classifier_type)
                if not is_valid:
                    logger.warning(f"Validierung fehlgeschlagen: {reason}")
                    return {"status": "skipped", "reason": reason}
            
            # =============================================================
            # STEP 5: Skalierung mit Global-Scaler (transform, NICHT fit_transform!)
            # =============================================================
            scaler = load_global_scaler(classifier_type)
            
            if scaler is None:
                logger.warning(f"⚠️ Kein Global-Scaler für {classifier_type}, Training übersprungen")
                return {"status": "skipped", "reason": "no_global_scaler"}
            
            X_scaled = scaler.transform(X)
            logger.debug(f"✅ Skalierung: {X.shape} → {X_scaled.shape}")
            
            # =============================================================
            # STEP 6 + 7: Training (fit vs partial_fit Entscheidung)
            # =============================================================
            personal_clf_path = _get_personal_classifier_path(user_id, classifier_type)
            _ensure_personal_classifier_dir(user_id)
            
            existing_clf = None
            if personal_clf_path.exists():
                try:
                    existing_clf = joblib.load(personal_clf_path)
                    logger.debug(f"📂 Existierender Classifier geladen: {personal_clf_path}")
                except Exception as e:
                    logger.warning(f"Laden fehlgeschlagen, erstelle neuen: {e}")
                    existing_clf = None
            
            # _train_classifier entscheidet fit() vs partial_fit()
            clf = _train_classifier(X_scaled, y, classifier_type, existing_clf)
            
            # =============================================================
            # STEP 8: Atomic Write
            # =============================================================
            _atomic_save_model(clf, personal_clf_path)
            logger.info(f"💾 Classifier gespeichert: {personal_clf_path}")
            
            # =============================================================
            # STEP 9: Accuracy berechnen
            # =============================================================
            accuracy = _compute_accuracy(clf, X_scaled, y)
            logger.info(f"📈 Accuracy: {accuracy:.2%}")
            
            # =============================================================
            # STEP 10: Metadata + Cache + error_count reset
            # =============================================================
            next_version = _get_next_version(user_id, classifier_type, db, models)
            
            _update_classifier_metadata(
                user_id, classifier_type,
                {
                    'training_samples': len(y),
                    'accuracy_score': accuracy,
                    'last_trained_at': datetime.now(UTC),
                    'model_version': next_version,
                    'error_count': 0,  # Reset bei Erfolg
                    'is_active': True,
                },
                db, models
            )
            
            # Cache invalidieren
            invalidate_classifier_cache(user_id, classifier_type)
            
            logger.info(
                f"✅ Training erfolgreich: {user_id}/{classifier_type} "
                f"(accuracy={accuracy:.2%}, samples={len(y)}, version={next_version})"
            )
            
            return {
                "status": "success",
                "user_id": user_id,
                "classifier_type": classifier_type,
                "samples": len(y),
                "accuracy": round(accuracy, 4),
                "version": next_version,
            }
        
        finally:
            # Lock immer freigeben
            if redis_lock:
                try:
                    redis_lock.release()
                except Exception as e:
                    logger.warning(f"Redis Lock Release fehlgeschlagen: {e}")
    
    except Exception as e:
        # =================================================================
        # ERROR HANDLING: Circuit-Breaker + Retry
        # =================================================================
        db.rollback()
        error_count = _increment_error_count(user_id, classifier_type, db, models)
        
        logger.error(
            f"❌ Training fehlgeschlagen: {user_id}/{classifier_type} "
            f"(error_count={error_count}, error={e})",
            exc_info=True
        )
        
        # Retry wenn noch nicht max erreicht
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        else:
            return {
                "status": "failed",
                "reason": str(e),
                "retries": self.request.retries,
                "error_count": error_count,
            }
    
    finally:
        db.close()


# =============================================================================
# TRIGGER HELPER (für API-Aufrufe)
# =============================================================================

def trigger_training_async(
    user_id: int,
    classifier_type: str,
    force: bool = False
) -> str:
    """Triggert Training asynchron via Celery.
    
    Args:
        user_id: User ID
        classifier_type: Classifier-Typ
        force: Ignoriere Throttling wenn True
        
    Returns:
        Celery Task ID
    """
    task = train_personal_classifier.delay(user_id, classifier_type, force)
    logger.info(f"📤 Training Task gestartet: {task.id}")
    return task.id


def trigger_all_classifiers_async(user_id: int, force: bool = False) -> List[str]:
    """Triggert Training für alle Classifier-Typen.
    
    Args:
        user_id: User ID
        force: Ignoriere Throttling wenn True
        
    Returns:
        Liste von Celery Task IDs
    """
    task_ids = []
    for classifier_type in CLASSIFIER_TYPES:
        task_id = trigger_training_async(user_id, classifier_type, force)
        task_ids.append(task_id)
    return task_ids
