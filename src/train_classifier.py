"""
ML Training Pipeline - Trainiert Klassifikatoren aus User-Korrektionen
Nutzt user_override_* Spalten aus der Datenbank zur Verbesserung der Base-Pass Heuristiken
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np
from datetime import datetime, UTC

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder
    import joblib

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from sqlalchemy.orm import Session
import sys
import importlib.util
from pathlib import Path

src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))

spec_models = importlib.util.spec_from_file_location("models", src_dir / "02_models.py")
models = importlib.util.module_from_spec(spec_models)
spec_models.loader.exec_module(models)

spec_ai = importlib.util.spec_from_file_location(
    "ai_client", src_dir / "03_ai_client.py"
)
ai_client = importlib.util.module_from_spec(spec_ai)
spec_ai.loader.exec_module(ai_client)

LocalOllamaClient = ai_client.LocalOllamaClient

logger = logging.getLogger(__name__)


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
        self.ollama_client = LocalOllamaClient(
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
        if clf_dr:
            joblib.dump(clf_dr, self.classifier_dir / "dringlichkeit_clf.pkl")
            self._log("💾 dringlichkeit_clf.pkl gespeichert")
            trained_count += 1

        clf_w = self.train_classifier(embeddings_w, labels_w, "Wichtigkeit")
        if clf_w:
            joblib.dump(clf_w, self.classifier_dir / "wichtigkeit_clf.pkl")
            self._log("💾 wichtigkeit_clf.pkl gespeichert")
            trained_count += 1

        clf_spam = self.train_classifier(embeddings_spam, labels_spam, "Spam")
        if clf_spam:
            joblib.dump(clf_spam, self.classifier_dir / "spam_clf.pkl")
            self._log("💾 spam_clf.pkl gespeichert")
            trained_count += 1

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
