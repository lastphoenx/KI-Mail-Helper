# src/services/personal_classifier_service.py
"""
Personal Classifier Service - Loading + Caching für Hybrid Score-Learning.

Implementiert:
- Laden von Global- und Personal-Classifiern
- TTL-basiertes Caching (5 Min)
- Fallback-Logik basierend auf User-Präferenz

Pattern kopiert aus:
- src/03_ai_client.py Zeile 430-528 (_load_classifiers, _load_classifier_safely)
- src/train_classifier.py Zeile 81-99 (_load_or_init_classifiers)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional, Tuple, TYPE_CHECKING

try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    joblib = None
    HAS_JOBLIB = False

try:
    from sklearn.linear_model import SGDClassifier
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    SGDClassifier = None
    StandardScaler = None
    HAS_SKLEARN = False

from cachetools import TTLCache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

CLASSIFIER_TYPES = ["dringlichkeit", "wichtigkeit", "spam", "kategorie"]
CACHE_TTL_SECONDS = 300  # 5 Minuten
CACHE_MAX_SIZE = 1000

# Sentinel für Negative-Caching (unterscheidet "nicht gecacht" von "gecacht als nicht vorhanden")
_NOT_FOUND = object()


# =============================================================================
# GLOBAL CACHE (Thread-safe)
# =============================================================================

_classifier_cache: TTLCache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)
_scaler_cache: TTLCache = TTLCache(maxsize=100, ttl=CACHE_TTL_SECONDS)
_cache_lock = threading.Lock()


# =============================================================================
# PATH HELPERS
# =============================================================================

def get_classifier_dir() -> Path:
    """Gibt den Pfad zum classifiers-Verzeichnis zurück.
    
    Returns:
        Path: src/classifiers/
    """
    return Path(__file__).resolve().parent.parent / "classifiers"


def _get_global_classifier_path(classifier_type: str) -> Path:
    """Pfad zum globalen Classifier.
    
    Pattern: classifiers/global/{classifier_type}_sgd.pkl
    """
    return get_classifier_dir() / "global" / f"{classifier_type}_sgd.pkl"


def _get_personal_classifier_path(user_id: int, classifier_type: str) -> Path:
    """Pfad zum Personal Classifier.
    
    Pattern: classifiers/per_user/{user_id}/{classifier_type}.joblib
    """
    return get_classifier_dir() / "per_user" / str(user_id) / f"{classifier_type}.joblib"


def _get_global_scaler_path(classifier_type: str) -> Path:
    """Pfad zum globalen Scaler.
    
    Pattern: classifiers/global/{classifier_type}_scaler.pkl
    """
    return get_classifier_dir() / "global" / f"{classifier_type}_scaler.pkl"


# =============================================================================
# LOW-LEVEL LOADING (kopiert aus src/03_ai_client.py Zeile 494-528)
# =============================================================================

def _load_pickle_safely(pkl_path: Path) -> Any:
    """Lädt Pickle-Files mit optionaler Integrity-Prüfung.
    
    Security-Note: Pickle-Deserialization kann zu RCE führen wenn Attacker
    malicious .pkl Files platziert. Optional kann via CLASSIFIER_HMAC_KEY
    Environment-Variable HMAC-Verification aktiviert werden.
    
    Kopiert aus: src/03_ai_client.py Zeile 494-528 (_load_classifier_safely)
    
    Args:
        pkl_path: Pfad zur .pkl/.joblib Datei
        
    Returns:
        Geladenes Objekt (Classifier, Scaler, etc.)
        
    Raises:
        FileNotFoundError: Wenn Datei nicht existiert
        ValueError: Wenn HMAC-Check fehlschlägt
        Exception: Bei anderen Ladefehlern
    """
    if not HAS_JOBLIB:
        raise RuntimeError("joblib nicht installiert")
    
    if not pkl_path.exists():
        raise FileNotFoundError(f"Classifier nicht gefunden: {pkl_path}")
    
    secret_key = os.getenv("CLASSIFIER_HMAC_KEY", "").encode()

    # Optional: HMAC verification wenn Secret Key gesetzt
    if secret_key:
        sig_path = pkl_path.with_suffix(pkl_path.suffix + ".sig")
        if sig_path.exists():
            with open(pkl_path, "rb") as f:
                file_data = f.read()
            with open(sig_path, "r") as f:
                expected_hash = f.read().strip()

            computed_hash = hmac.new(
                secret_key, file_data, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(computed_hash, expected_hash):
                raise ValueError(f"Classifier integrity check failed: {pkl_path}")
            logger.debug(f"🔒 Integrity verified: {pkl_path.name}")
        else:
            logger.warning(
                f"⚠️ No signature file for {pkl_path.name} (HMAC key set but no .sig)"
            )

    return joblib.load(pkl_path)


# =============================================================================
# BASIS-FUNKTIONEN (Datei-IO)
# =============================================================================

def load_global_classifier(classifier_type: str) -> Optional[SGDClassifier]:
    """Lädt globalen SGD-Classifier.
    
    Pattern kopiert aus: src/03_ai_client.py Zeile 449-461
    
    Args:
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        
    Returns:
        SGDClassifier oder None wenn nicht vorhanden
    """
    if classifier_type not in CLASSIFIER_TYPES:
        logger.warning(f"Unbekannter classifier_type: {classifier_type}")
        return None
    
    clf_path = _get_global_classifier_path(classifier_type)
    
    if not clf_path.exists():
        logger.debug(f"Global classifier nicht gefunden: {clf_path}")
        return None
    
    try:
        clf = _load_pickle_safely(clf_path)
        logger.debug(f"✅ Global classifier geladen: {classifier_type}")
        return clf
    except Exception as e:
        logger.warning(f"Fehler beim Laden von global/{classifier_type}: {e}")
        return None


def load_personal_classifier(user_id: int, classifier_type: str) -> Optional[SGDClassifier]:
    """Lädt Personal Classifier für einen User.
    
    Wie load_global_classifier, aber aus: per_user/{user_id}/{classifier_type}.joblib
    
    Args:
        user_id: User ID
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        
    Returns:
        SGDClassifier oder None wenn nicht vorhanden
    """
    if classifier_type not in CLASSIFIER_TYPES:
        logger.warning(f"Unbekannter classifier_type: {classifier_type}")
        return None
    
    clf_path = _get_personal_classifier_path(user_id, classifier_type)
    
    if not clf_path.exists():
        logger.debug(f"Personal classifier nicht gefunden: user_{user_id}/{classifier_type}")
        return None
    
    try:
        clf = _load_pickle_safely(clf_path)
        logger.debug(f"✅ Personal classifier geladen: user_{user_id}/{classifier_type}")
        return clf
    except Exception as e:
        logger.warning(f"Fehler beim Laden von personal user_{user_id}/{classifier_type}: {e}")
        return None


def load_global_scaler(classifier_type: str) -> Optional[StandardScaler]:
    """Lädt globalen Scaler für einen Classifier-Typ.
    
    WICHTIG: Immer Global-Scaler nutzen, auch für Personal-Modelle!
    (Konsistente Feature-Skalierung über alle Modelle)
    
    Pattern aus: src/train_classifier.py Zeile 91-93
    
    Args:
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        
    Returns:
        StandardScaler oder None wenn nicht vorhanden
    """
    if classifier_type not in CLASSIFIER_TYPES:
        logger.warning(f"Unbekannter classifier_type: {classifier_type}")
        return None
    
    scaler_path = _get_global_scaler_path(classifier_type)
    
    if not scaler_path.exists():
        logger.debug(f"Global scaler nicht gefunden: {scaler_path}")
        return None
    
    try:
        scaler = _load_pickle_safely(scaler_path)
        logger.debug(f"✅ Global scaler geladen: {classifier_type}")
        return scaler
    except Exception as e:
        logger.warning(f"Fehler beim Laden von scaler/{classifier_type}: {e}")
        return None


# =============================================================================
# CACHING LAYER
# =============================================================================

def load_classifier_cached(
    user_id: Optional[int],
    classifier_type: str
) -> Optional[SGDClassifier]:
    """Lädt Classifier mit TTLCache (5 Min).
    
    Thread-safe via _cache_lock.
    
    Args:
        user_id: User ID oder None für Global
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        
    Returns:
        SGDClassifier oder None wenn nicht vorhanden
    """
    cache_key = f"{user_id or 'global'}:{classifier_type}"
    
    # Check Cache (inkl. Negative-Caching mit Sentinel)
    with _cache_lock:
        if cache_key in _classifier_cache:
            cached = _classifier_cache[cache_key]
            if cached is _NOT_FOUND:
                logger.debug(f"🎯 Cache hit (not found): {cache_key}")
                return None
            logger.debug(f"🎯 Cache hit: {cache_key}")
            return cached
    
    # Load from Disk
    if user_id is None:
        clf = load_global_classifier(classifier_type)
    else:
        clf = load_personal_classifier(user_id, classifier_type)
    
    # Cache result (auch None als _NOT_FOUND Sentinel)
    with _cache_lock:
        if clf is not None:
            _classifier_cache[cache_key] = clf
            logger.debug(f"💾 Cached: {cache_key}")
        else:
            _classifier_cache[cache_key] = _NOT_FOUND
            logger.debug(f"💾 Cached (not found): {cache_key}")
    
    return clf


def load_scaler_cached(classifier_type: str) -> Optional[StandardScaler]:
    """Lädt Global-Scaler mit TTLCache (5 Min).
    
    Args:
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        
    Returns:
        StandardScaler oder None wenn nicht vorhanden
    """
    cache_key = f"scaler:{classifier_type}"
    
    # Check Cache (inkl. Negative-Caching)
    with _cache_lock:
        if cache_key in _scaler_cache:
            cached = _scaler_cache[cache_key]
            if cached is _NOT_FOUND:
                return None
            return cached
    
    scaler = load_global_scaler(classifier_type)
    
    # Cache result (auch None als _NOT_FOUND Sentinel)
    with _cache_lock:
        if scaler is not None:
            _scaler_cache[cache_key] = scaler
        else:
            _scaler_cache[cache_key] = _NOT_FOUND
    
    return scaler


def invalidate_classifier_cache(
    user_id: Optional[int] = None,
    classifier_type: Optional[str] = None
) -> int:
    """Invalidiert Cache-Einträge.
    
    Args:
        user_id: Wenn gesetzt, lösche nur Einträge für diesen User
        classifier_type: Wenn gesetzt, lösche nur Einträge für diesen Typ
        
    Returns:
        Anzahl gelöschter Einträge
        
    Beispiele:
        invalidate_classifier_cache()  # Alles löschen
        invalidate_classifier_cache(user_id=1)  # Nur User 1
        invalidate_classifier_cache(classifier_type="spam")  # Nur Spam-Classifier
        invalidate_classifier_cache(user_id=1, classifier_type="spam")  # Spezifisch
    """
    deleted = 0
    
    with _cache_lock:
        if user_id is None and classifier_type is None:
            # Alles löschen
            deleted = len(_classifier_cache)
            _classifier_cache.clear()
            _scaler_cache.clear()
            logger.info(f"🗑️ Cache komplett geleert ({deleted} Einträge)")
            return deleted
        
        # Selektiv löschen
        keys_to_delete = []
        
        for key in list(_classifier_cache.keys()):
            # Key format: "{user_id or 'global'}:{classifier_type}"
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            
            key_user, key_type = parts
            
            # Filter-Logik
            user_match = (user_id is None) or (key_user == str(user_id))
            type_match = (classifier_type is None) or (key_type == classifier_type)
            
            if user_match and type_match:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del _classifier_cache[key]
            deleted += 1
        
        # Scaler-Cache nur bei classifier_type löschen
        if classifier_type is not None:
            scaler_key = f"scaler:{classifier_type}"
            if scaler_key in _scaler_cache:
                del _scaler_cache[scaler_key]
                deleted += 1
    
    if deleted > 0:
        logger.info(f"🗑️ Cache invalidiert: {deleted} Einträge (user={user_id}, type={classifier_type})")
    
    return deleted


# =============================================================================
# HIGH-LEVEL FLOW
# =============================================================================

def get_classifier_for_user(
    user_id: int,
    classifier_type: str,
    db_session: "Session"
) -> Tuple[Optional[SGDClassifier], str]:
    """Gibt (classifier, source) basierend auf User-Präferenz.
    
    Logik aus docs/HYBRID_SCORE_LEARNING.md:
    1. Lade user.prefer_personal_classifier aus DB
    2. Falls False: nutze Global
    3. Falls True:
       a. Versuche load_personal_classifier()
       b. Falls None: Fallback zu Global (log warning)
       c. Falls vorhanden: return (classifier, "personal")
    
    Args:
        user_id: User ID
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        db_session: SQLAlchemy Session für User-Lookup
        
    Returns:
        Tuple[classifier, source] mit source = "personal" | "global"
        classifier kann None sein wenn auch Global nicht vorhanden
        
    Raises:
        ValueError: Wenn User nicht gefunden
    """
    # Import Models hier um Circular Import zu vermeiden
    # Benutze importlib wegen Ziffer im Dateinamen (02_models.py)
    from importlib import import_module
    models = import_module("src.02_models")
    User = models.User
    
    # 1. User-Präferenz laden
    user = db_session.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} nicht gefunden")
    
    # 2. Falls User Global bevorzugt
    if not user.prefer_personal_classifier:
        clf = load_classifier_cached(None, classifier_type)
        return (clf, "global")
    
    # 3. User will Personal-Modell
    clf = load_classifier_cached(user_id, classifier_type)
    
    if clf is not None:
        # Personal-Modell gefunden
        return (clf, "personal")
    
    # 3b. Fallback zu Global
    logger.warning(
        f"⚠️ Personal classifier nicht verfügbar für user_{user_id}/{classifier_type}, "
        f"Fallback zu Global"
    )
    clf = load_classifier_cached(None, classifier_type)
    return (clf, "global")


def get_scaler_for_prediction(classifier_type: str) -> Optional[StandardScaler]:
    """Gibt den Scaler für Predictions zurück.
    
    IMMER Global-Scaler, auch für Personal-Modelle!
    
    Args:
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        
    Returns:
        StandardScaler oder None wenn nicht vorhanden
    """
    return load_scaler_cached(classifier_type)


def predict_with_classifier(
    user_id: int,
    classifier_type: str,
    embedding: "np.ndarray",
    db_session: "Session"
) -> Tuple[Optional[int], float, str]:
    """Macht Vorhersage mit Personal oder Global Classifier.
    
    High-Level Wrapper für Prediction mit User-Präferenz + Fallback.
    
    Args:
        user_id: User ID
        classifier_type: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
        embedding: Email-Embedding (np.ndarray mit 384 dims)
        db_session: SQLAlchemy Session
        
    Returns:
        Tuple[prediction, confidence, source]:
        - prediction: Vorhergesagte Klasse (int) oder None wenn Fehler
        - confidence: Konfidenz (0.0-1.0), 0.0 wenn Fehler
        - source: "personal" | "global" | "fallback_global" | "error"
        
    Error-Cases (alle geben (None, 0.0, "error") zurück):
    - Classifier nicht vorhanden
    - Scaler nicht vorhanden
    - Features ungültig (NaN)
    - Classifier beschädigt
    
    Note:
        Diese Funktion wirft KEINE Exceptions! Bei Fehler → Fallback-Werte.
        Caller muss prüfen ob prediction None ist.
    """
    import numpy as np
    
    # Validierung: classifier_type
    if classifier_type not in CLASSIFIER_TYPES:
        logger.error(f"❌ Ungültiger classifier_type: {classifier_type}")
        return (None, 0.0, "error")
    
    # Validierung: Embedding
    if embedding is None or not isinstance(embedding, np.ndarray):
        logger.warning(f"⚠️ Ungültiges Embedding für {classifier_type}")
        return (None, 0.0, "error")
    
    if np.isnan(embedding).any():
        logger.warning(f"⚠️ Embedding enthält NaN-Werte für {classifier_type}")
        return (None, 0.0, "error")
    
    try:
        # 1. Classifier laden (Personal oder Global basierend auf User-Pref)
        clf, source = get_classifier_for_user(user_id, classifier_type, db_session)
        
        if clf is None:
            logger.warning(
                f"⚠️ Kein Classifier verfügbar für user_{user_id}/{classifier_type}"
            )
            return (None, 0.0, "error")
        
        # 2. Scaler laden (immer Global)
        scaler = get_scaler_for_prediction(classifier_type)
        
        if scaler is None:
            logger.warning(
                f"⚠️ Kein Scaler verfügbar für {classifier_type}, "
                f"Prediction ohne Skalierung"
            )
            # Fallback: Prediction ohne Skalierung (riskant aber besser als nichts)
            embedding_scaled = embedding.reshape(1, -1)
        else:
            # 3. Transform Embedding
            embedding_scaled = scaler.transform(embedding.reshape(1, -1))
        
        # 4. Vorhersage
        pred = clf.predict(embedding_scaled)[0]
        
        # 5. Confidence berechnen
        if hasattr(clf, 'predict_proba'):
            try:
                proba = clf.predict_proba(embedding_scaled)[0]
                confidence = float(max(proba))
            except Exception as e:
                logger.debug(f"predict_proba fehlgeschlagen: {e}")
                confidence = 0.5  # Default-Confidence wenn proba nicht verfügbar
        else:
            confidence = 0.5  # Classifier ohne Probability-Support
        
        # Logging
        logger.debug(
            f"🎯 Prediction: {classifier_type} für user_{user_id} → "
            f"{pred} (conf={confidence:.2f}, source={source})"
        )
        
        return (int(pred), confidence, source)
    
    except ValueError as e:
        # User nicht gefunden
        logger.error(f"❌ User-Fehler bei Prediction: {e}")
        return (None, 0.0, "error")
    
    except Exception as e:
        # Unerwarteter Fehler
        logger.error(
            f"❌ Prediction fehlgeschlagen für user_{user_id}/{classifier_type}: {e}",
            exc_info=True
        )
        return (None, 0.0, "error")


def enhance_with_personal_predictions(
    user_id: int,
    raw_email,
    result: dict,
    db_session: "Session"
) -> Tuple[dict, str]:
    """Erweitert AI-Analyse-Ergebnis mit Personal Classifier Predictions.
    
    Diese Funktion wird NACH der AI-Analyse (client.analyze_email()) aufgerufen
    und überschreibt dringlichkeit/wichtigkeit/spam mit Personal-Classifier-Werten
    wenn verfügbar und besser.
    
    Args:
        user_id: User ID
        raw_email: RawEmail-Objekt (für Embedding)
        result: Dict mit AI-Analyse-Ergebnis (dringlichkeit, wichtigkeit, etc.)
        db_session: SQLAlchemy Session
        
    Returns:
        Tuple[enhanced_result, used_model_source]:
        - enhanced_result: Kopie von result mit ggf. überschriebenen Werten
        - used_model_source: "global" | "personal" | "ai_only"
        
    Note:
        - Wenn kein Embedding → Original-Ergebnis unverändert
        - Wenn Prediction fehlschlägt → Original-Ergebnis beibehalten
        - used_model_source = "ai_only" wenn keine ML-Prediction erfolgte
    """
    import numpy as np
    
    # Kopiere Result um Original nicht zu verändern
    enhanced = result.copy()
    used_source = "ai_only"
    
    # Embedding aus RawEmail holen
    if not hasattr(raw_email, 'email_embedding') or raw_email.email_embedding is None:
        logger.debug(f"Kein Embedding für RawEmail {raw_email.id}, nutze AI-only")
        return (enhanced, "ai_only")
    
    try:
        # Embedding dekodieren (LargeBinary → numpy array)
        embedding_bytes = raw_email.email_embedding
        embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
        
        if len(embedding) == 0:
            logger.debug(f"Leeres Embedding für RawEmail {raw_email.id}")
            return (enhanced, "ai_only")
        
    except Exception as e:
        logger.warning(f"Embedding-Dekodierung fehlgeschlagen: {e}")
        return (enhanced, "ai_only")
    
    # Track welche Sources genutzt wurden
    sources_used = set()
    
    # Dringlichkeit
    pred, conf, source = predict_with_classifier(
        user_id, "dringlichkeit", embedding, db_session
    )
    if pred is not None:
        enhanced["dringlichkeit"] = pred
        enhanced["dringlichkeit_confidence"] = conf
        sources_used.add(source)
        logger.debug(f"📊 Dringlichkeit überschrieben: {pred} (source={source})")
    
    # Wichtigkeit
    pred, conf, source = predict_with_classifier(
        user_id, "wichtigkeit", embedding, db_session
    )
    if pred is not None:
        enhanced["wichtigkeit"] = pred
        enhanced["wichtigkeit_confidence"] = conf
        sources_used.add(source)
        logger.debug(f"📊 Wichtigkeit überschrieben: {pred} (source={source})")
    
    # Spam
    pred, conf, source = predict_with_classifier(
        user_id, "spam", embedding, db_session
    )
    if pred is not None:
        enhanced["spam_flag"] = bool(pred)
        enhanced["spam_confidence"] = conf
        sources_used.add(source)
        logger.debug(f"📊 Spam überschrieben: {bool(pred)} (source={source})")
    
    # Bestimme dominante Source
    if "personal" in sources_used:
        used_source = "personal"
    elif "global" in sources_used:
        used_source = "global"
    else:
        used_source = "ai_only"
    
    logger.info(
        f"🎯 Personal Predictions für user_{user_id}: "
        f"sources={sources_used}, dominant={used_source}"
    )
    
    return (enhanced, used_source)


# =============================================================================
# UTILITIES
# =============================================================================

def ensure_classifier_dirs() -> None:
    """Erstellt die Verzeichnisstruktur für Classifiers falls nicht vorhanden."""
    base_dir = get_classifier_dir()
    (base_dir / "global").mkdir(parents=True, exist_ok=True)
    (base_dir / "per_user").mkdir(parents=True, exist_ok=True)
    logger.debug(f"✅ Classifier-Verzeichnisse erstellt: {base_dir}")


def get_cache_stats() -> dict:
    """Gibt Cache-Statistiken zurück (für Debugging/Monitoring)."""
    with _cache_lock:
        return {
            "classifier_cache_size": len(_classifier_cache),
            "classifier_cache_maxsize": _classifier_cache.maxsize,
            "classifier_cache_ttl": _classifier_cache.ttl,
            "scaler_cache_size": len(_scaler_cache),
            "scaler_cache_maxsize": _scaler_cache.maxsize,
        }
