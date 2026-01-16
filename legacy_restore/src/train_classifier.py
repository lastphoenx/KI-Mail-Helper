"""
ML Training Pipeline - Trainiert Klassifikatoren aus User-Korrektionen
Nutzt user_override_* Spalten aus der Datenbank zur Verbesserung der Base-Pass Heuristiken

Phase 11b: Online-Learning mit SGDClassifier.partial_fit()
- Inkrementelles Lernen nach jeder User-Korrektur
- 100% lokal mit Ollama Embeddings
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np
from datetime import datetime, UTC
import os

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import SGDClassifier
    from sklearn.preprocessing import StandardScaler
    import joblib
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    joblib = None

from sqlalchemy.orm import Session
import importlib.util

src_dir = Path(__file__).parent

spec_models = importlib.util.spec_from_file_location("models", src_dir / "02_models.py")
models = importlib.util.module_from_spec(spec_models)
spec_models.loader.exec_module(models)

# Lazy import von ai_client um circular dependency zu vermeiden
LocalOllamaClient = None

def _get_ollama_client():
    """Lazy-load LocalOllamaClient um circular imports zu vermeiden"""
    global LocalOllamaClient
    if LocalOllamaClient is None:
        spec_ai = importlib.util.spec_from_file_location(
            "ai_client", src_dir / "03_ai_client.py"
        )
        ai_client = importlib.util.module_from_spec(spec_ai)
        spec_ai.loader.exec_module(ai_client)
        LocalOllamaClient = ai_client.LocalOllamaClient
    return LocalOllamaClient

logger = logging.getLogger(__name__)


class OnlineLearner:
    """Phase 11b: Online-Learning mit SGDClassifier.partial_fit()
    
    Ermöglicht inkrementelles Lernen nach jeder User-Korrektur,
    ohne komplettes Neutraining aller Daten.
    """
    
    CLASSIFIER_TYPES = ["dringlichkeit", "wichtigkeit", "spam", "kategorie"]
    
    def __init__(self, ollama_base_url: str = "http://127.0.0.1:11434"):
        if not HAS_SKLEARN:
            raise RuntimeError("scikit-learn nicht installiert")
        
        self.classifier_dir = Path(__file__).resolve().parent / "classifiers"
        self.classifier_dir.mkdir(exist_ok=True)
        
        # Lazy-load Ollama Client
        OllamaClient = _get_ollama_client()
        self.ollama_client = OllamaClient(
            model="all-minilm:22m", base_url=ollama_base_url
        )
        
        # SGD-Klassifikatoren für Online-Learning
        self._sgd_classifiers = {}
        self._scalers = {}
        self._load_or_init_classifiers()
    
    def _load_or_init_classifiers(self):
        """Lädt existierende SGD-Klassifikatoren oder initialisiert neue."""
        for clf_type in self.CLASSIFIER_TYPES:
            sgd_path = self.classifier_dir / f"{clf_type}_sgd.pkl"
            scaler_path = self.classifier_dir / f"{clf_type}_scaler.pkl"
            
            if sgd_path.exists() and joblib:
                try:
                    self._sgd_classifiers[clf_type] = joblib.load(sgd_path)
                    if scaler_path.exists():
                        self._scalers[clf_type] = joblib.load(scaler_path)
                    else:
                        self._scalers[clf_type] = StandardScaler()
                    logger.debug(f"✅ SGD-Klassifikator geladen: {clf_type}")
                except Exception as e:
                    logger.warning(f"Fehler beim Laden von {clf_type}: {e}")
                    self._init_new_classifier(clf_type)
            else:
                self._init_new_classifier(clf_type)
    
    def _init_new_classifier(self, clf_type: str):
        """Initialisiert neuen SGDClassifier für Online-Learning."""
        if clf_type == "spam":
            # Binary classification für Spam
            self._sgd_classifiers[clf_type] = SGDClassifier(
                loss="log_loss",  # Logistische Regression
                penalty="l2",
                alpha=0.0001,
                max_iter=1000,
                tol=1e-3,
                random_state=42,
                warm_start=True,  # Wichtig für partial_fit
            )
        else:
            # Multi-class für Dringlichkeit/Wichtigkeit (1-3)
            self._sgd_classifiers[clf_type] = SGDClassifier(
                loss="log_loss",
                penalty="l2",
                alpha=0.0001,
                max_iter=1000,
                tol=1e-3,
                random_state=42,
                warm_start=True,
            )
        self._scalers[clf_type] = StandardScaler()
        logger.debug(f"🆕 Neuer SGD-Klassifikator initialisiert: {clf_type}")
    
    def learn_from_correction(
        self,
        subject: str,
        body: str,
        correction_type: str,
        correction_value: int | bool | str,
    ) -> bool:
        """Inkrementelles Lernen aus einer einzelnen User-Korrektur.
        
        Args:
            subject: E-Mail Betreff
            body: E-Mail Body
            correction_type: "dringlichkeit", "wichtigkeit", "spam", oder "kategorie"
            correction_value: Korrigierter Wert (1-3, True/False, oder Kategorie-String)
            
        Returns:
            True wenn erfolgreich gelernt
        """
        if correction_type not in self.CLASSIFIER_TYPES:
            logger.warning(f"Unbekannter Korrekturtyp: {correction_type}")
            return False
        
        # Embedding generieren
        embedding = self.ollama_client._get_embedding(f"{subject}\n{body}")
        if not embedding:
            logger.warning("Embedding-Generierung fehlgeschlagen")
            return False
        
        X = np.array([embedding])
        
        # Für Spam: Boolean → int
        if correction_type == "spam":
            y = np.array([1 if correction_value else 0])
            classes = np.array([0, 1])
        elif correction_type == "kategorie":
            # Kategorie String → int (nur_information=0, aktion_erforderlich=1, dringend=2)
            label_map = {"nur_information": 0, "aktion_erforderlich": 1, "dringend": 2}
            y = np.array([label_map.get(str(correction_value), 1)])  # Default: aktion_erforderlich
            classes = np.array([0, 1, 2])
        else:
            y = np.array([int(correction_value)])
            classes = np.array([1, 2, 3])  # Dringlichkeit/Wichtigkeit 1-3
        
        try:
            clf = self._sgd_classifiers[correction_type]
            scaler = self._scalers[correction_type]
            
            # Feature Scaling (wichtig für SGD)
            # Beim ersten Sample: fit_transform, danach transform
            if not hasattr(scaler, 'mean_') or scaler.mean_ is None:
                X_scaled = scaler.fit_transform(X)
            else:
                X_scaled = scaler.transform(X)
            
            # Inkrementelles Training mit partial_fit
            clf.partial_fit(X_scaled, y, classes=classes)
            
            # Speichern
            if joblib:
                joblib.dump(clf, self.classifier_dir / f"{correction_type}_sgd.pkl")
                joblib.dump(scaler, self.classifier_dir / f"{correction_type}_scaler.pkl")
            
            logger.info(f"📚 Online-Learning: {correction_type}={correction_value} gelernt")
            return True
            
        except Exception as e:
            logger.error(f"Online-Learning Fehler: {e}")
            return False
    
    def predict(self, subject: str, body: str, clf_type: str) -> Optional[int]:
        """Prediction mit Online-Learning Modell.
        
        Args:
            subject: E-Mail Betreff
            body: E-Mail Body
            clf_type: "dringlichkeit", "wichtigkeit", oder "spam"
            
        Returns:
            Prediction (1-3 oder 0/1) oder None bei Fehler
        """
        if clf_type not in self._sgd_classifiers:
            return None
        
        clf = self._sgd_classifiers[clf_type]
        scaler = self._scalers.get(clf_type)
        
        # Prüfen ob Modell trainiert wurde
        if not hasattr(clf, 'classes_') or clf.classes_ is None:
            return None
        
        embedding = self.ollama_client._get_embedding(f"{subject}\n{body}")
        if not embedding:
            return None
        
        try:
            X = np.array([embedding])
            if scaler and hasattr(scaler, 'mean_') and scaler.mean_ is not None:
                X = scaler.transform(X)
            return int(clf.predict(X)[0])
        except Exception as e:
            logger.debug(f"Prediction Fehler: {e}")
            return None


class MLTrainer:
    """Trainiert sklearn-Klassifikatoren basierend auf User-Korrektionen"""

    def __init__(
        self, db_session: Session, ollama_base_url: str = "http://127.0.0.1:11434"
    ):
        if not HAS_SKLEARN:
            raise RuntimeError(
                "scikit-learn nicht installiert. Bitte: pip install scikit-learn"
            )

        self.db = db_session
        self.classifier_dir = Path(__file__).resolve().parent / "classifiers"
        self.classifier_dir.mkdir(exist_ok=True)
        
        # Lazy-load Ollama Client
        OllamaClient = _get_ollama_client()
        self.ollama_client = OllamaClient(
            model="all-minilm:22m", base_url=ollama_base_url
        )
        self.log_file = self.classifier_dir / "training_log.txt"

    def _log(self, msg: str):
        """Schreibt Log-Messages zu Datei und Logger"""
        logger.info(msg)
        with open(self.log_file, "a") as f:
            f.write(f"[{datetime.now(UTC).isoformat()}] {msg}\n")

    def collect_training_data(
        self,
    ) -> Tuple[
        List[np.ndarray],
        List[int],
        List[np.ndarray],
        List[int],
        List[np.ndarray],
        List[bool],
    ]:
        """
        Sammelt Embeddings + Labels aus Datenbank.
        Gibt 3 Tupel: (embeddings_dr, labels_dr), (embeddings_w, labels_w), (embeddings_spam, labels_spam)
        """
        ProcessedEmail = models.ProcessedEmail
        query = (
            self.db.query(ProcessedEmail)
            .filter(ProcessedEmail.user_override_dringlichkeit != None)
            .all()
        )

        if not query:
            self._log("⚠️ Keine User-Korrektionen gefunden. Überspringe Training.")
            return [], [], [], [], [], []

        self._log(f"📊 Sammle Daten aus {len(query)} korrigierten Emails...")

        embeddings_dr = []
        labels_dr = []
        embeddings_w = []
        labels_w = []
        embeddings_spam = []
        labels_spam = []

        failed_count = 0
        for email in query:
            try:
                raw = email.raw_email
                subject = raw.subject or ""
                body = raw.body or ""

                embedding = self.ollama_client._get_embedding(f"{subject}\n{body}")
                if not embedding:
                    failed_count += 1
                    continue

                embedding_array = np.array(embedding)

                if email.user_override_dringlichkeit:
                    embeddings_dr.append(embedding_array)
                    labels_dr.append(email.user_override_dringlichkeit)

                if email.user_override_wichtigkeit:
                    embeddings_w.append(embedding_array)
                    labels_w.append(email.user_override_wichtigkeit)

                if email.user_override_spam_flag is not None:
                    embeddings_spam.append(embedding_array)
                    labels_spam.append(1 if email.user_override_spam_flag else 0)

            except Exception as e:
                logger.debug(f"Fehler bei Email {email.id}: {e}")
                failed_count += 1

        self._log(
            f"✅ Embeddings generiert: Dringlichkeit={len(embeddings_dr)}, Wichtigkeit={len(embeddings_w)}, Spam={len(embeddings_spam)} (Failed: {failed_count})"
        )

        return (
            embeddings_dr,
            labels_dr,
            embeddings_w,
            labels_w,
            embeddings_spam,
            labels_spam,
        )

    def train_classifier(
        self, embeddings: List[np.ndarray], labels: List[int], name: str
    ) -> Optional[RandomForestClassifier]:
        """Trainiert einen RandomForest-Klassifikator"""
        if len(embeddings) < 5:
            self._log(
                f"⚠️ Zu wenige Samples für {name} ({len(embeddings)} < 5). Überspringe."
            )
            return None

        try:
            X = np.array(embeddings)
            y = np.array(labels)

            clf = RandomForestClassifier(
                n_estimators=100, random_state=42, max_depth=10
            )
            clf.fit(X, y)

            score = clf.score(X, y)
            self._log(
                f"✅ {name}: Training erfolgreich (Accuracy={score:.2%}, Samples={len(embeddings)})"
            )
            return clf

        except Exception as e:
            logger.error(f"Fehler beim Training von {name}: {e}")
            self._log(f"❌ {name}: Training fehlgeschlagen - {e}")
            return None

    def train_all(self) -> int:
        """
        Trainiert alle Klassifikatoren.
        Gibt die Anzahl erfolgreich trainierter Klassifikatoren zurück.
        """
        self._log(f"\n{'='*60}")
        self._log(f"🚀 Training gestartet um {datetime.now(UTC).isoformat()}")
        self._log(f"{'='*60}\n")

        (
            embeddings_dr,
            labels_dr,
            embeddings_w,
            labels_w,
            embeddings_spam,
            labels_spam,
        ) = self.collect_training_data()

        if not embeddings_dr and not embeddings_w and not embeddings_spam:
            self._log("❌ Keine Trainingsdaten vorhanden. Abbruch.")
            return 0

        trained_count = 0

        clf_dr = self.train_classifier(embeddings_dr, labels_dr, "Dringlichkeit")
        if clf_dr and joblib:
            joblib.dump(clf_dr, self.classifier_dir / "dringlichkeit_clf.pkl")
            self._log("💾 dringlichkeit_clf.pkl gespeichert")
            trained_count += 1
        elif clf_dr:
            self._log("⚠️  joblib nicht verfügbar, dringlichkeit_clf nicht gespeichert")

        clf_w = self.train_classifier(embeddings_w, labels_w, "Wichtigkeit")
        if clf_w and joblib:
            joblib.dump(clf_w, self.classifier_dir / "wichtigkeit_clf.pkl")
            self._log("💾 wichtigkeit_clf.pkl gespeichert")
            trained_count += 1
        elif clf_w:
            self._log("⚠️  joblib nicht verfügbar, wichtigkeit_clf nicht gespeichert")

        clf_spam = self.train_classifier(embeddings_spam, labels_spam, "Spam")
        if clf_spam and joblib:
            joblib.dump(clf_spam, self.classifier_dir / "spam_clf.pkl")
            self._log("💾 spam_clf.pkl gespeichert")
            trained_count += 1
        elif clf_spam:
            self._log("⚠️  joblib nicht verfügbar, spam_clf nicht gespeichert")

        self._log(f"\n{'='*60}")
        self._log(
            f"✅ Training abgeschlossen: {trained_count}/3 Klassifikatoren erfolgreich trainiert"
        )
        self._log(f"{'='*60}\n")

        return trained_count

    def get_training_stats(self) -> dict:
        """Gibt Statistiken über Trainingsdaten"""
        ProcessedEmail = models.ProcessedEmail
        dringlichkeit_count = (
            self.db.query(ProcessedEmail)
            .filter(ProcessedEmail.user_override_dringlichkeit != None)
            .count()
        )
        wichtigkeit_count = (
            self.db.query(ProcessedEmail)
            .filter(ProcessedEmail.user_override_wichtigkeit != None)
            .count()
        )
        spam_count = (
            self.db.query(ProcessedEmail)
            .filter(ProcessedEmail.user_override_spam_flag != None)
            .count()
        )

        return {
            "dringlichkeit": dringlichkeit_count,
            "wichtigkeit": wichtigkeit_count,
            "spam": spam_count,
            "total": max(dringlichkeit_count, wichtigkeit_count, spam_count),
        }


def train_from_corrections(
    db_path: str = "emails.db", ollama_url: str = "http://127.0.0.1:11434"
) -> int:
    """
    Hauptfunktion: Trainiert Klassifikatoren aus User-Korrektionen.
    Wird von Web-Endpoint oder Cron aufgerufen.
    """
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")

    init_db = models.init_db
    engine, SessionLocal = init_db(db_path)

    db = SessionLocal()
    try:
        trainer = MLTrainer(db, ollama_base_url=ollama_url)
        return trainer.train_all()
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    trained = train_from_corrections()
    print(f"\n✅ {trained} Klassifikatoren trainiert")
