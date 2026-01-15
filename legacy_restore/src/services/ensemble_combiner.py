"""
Phase Y: Ensemble Learning - spaCy Rules + SGD Machine Learning
Kombiniert regelbasierte spaCy Detektoren mit SGD Online Learning.
"""

from typing import Dict, Tuple
from sqlalchemy.orm import Session
import importlib.util
from pathlib import Path

# Dynamischer Import von 02_models.py (relative path)
src_dir = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location(
    "models", src_dir / "02_models.py"
)
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)

ProcessedEmail = models.ProcessedEmail


class EnsembleCombiner:
    """
    Ensemble-System für Phase Y: spaCy NLP + SGD Learning.
    
    Strategie:
    - <20 Korrekturen: 100% spaCy (SGD noch untrainiert)
    - 20-50 Korrekturen: 30% spaCy + 70% SGD (Lernphase)
    - 50+ Korrekturen: 15% spaCy + 85% SGD (personalisiert)
    
    Vorteile:
    - Day 1: Sofort nutzbar dank spaCy Rules
    - Langfristig: Lernt Nutzerverhalten über SGD
    - Hybrid: Beste aus beiden Welten
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def combine_predictions(
        self,
        account_id: int,
        spacy_scores: Dict[str, int],
        sgd_scores: Dict[str, int],
        num_corrections: int,
    ) -> Dict[str, int]:
        """
        Kombiniert spaCy und SGD Predictions basierend auf Lernfortschritt.
        
        Args:
            account_id: ID des Mail-Accounts
            spacy_scores: {"wichtigkeit": 3, "dringlichkeit": 2} von spaCy Pipeline
            sgd_scores: {"wichtigkeit": 4, "dringlichkeit": 3} von SGD Classifier
            num_corrections: Anzahl User-Korrekturen für diesen Account
            
        Returns:
            Finale Scores: {"wichtigkeit": X, "dringlichkeit": Y}
        """
        spacy_weight, sgd_weight = self._get_weights(num_corrections)

        final_scores = {}
        for key in ["wichtigkeit", "dringlichkeit"]:
            spacy_val = spacy_scores.get(key, 0)
            sgd_val = sgd_scores.get(key, 0)

            # Gewichteter Durchschnitt
            weighted = (spacy_val * spacy_weight + sgd_val * sgd_weight) / 100
            final_scores[key] = round(weighted)

        return final_scores

    def _get_weights(self, num_corrections: int) -> Tuple[int, int]:
        """
        Bestimmt Ensemble-Gewichte basierend auf Anzahl Korrekturen.
        
        Args:
            num_corrections: Anzahl User-Korrekturen
            
        Returns:
            (spacy_weight, sgd_weight) - Summe ist immer 100
            
        Beispiele:
            - 10 Korrekturen → (100, 0)
            - 30 Korrekturen → (30, 70)
            - 60 Korrekturen → (15, 85)
        """
        if num_corrections < 20:
            # SGD noch untrainiert, nur spaCy nutzen
            return (100, 0)
        elif num_corrections < 50:
            # Lernphase: SGD wird wichtiger, spaCy bleibt Backup
            return (30, 70)
        else:
            # Vollständig personalisiert: SGD dominant, spaCy als Baseline
            return (15, 85)

    def get_correction_count(self, account_id: int) -> int:
        """
        Zählt User-Korrekturen für Account (aus processed_emails).
        
        User-Korrekturen sind gespeichert in:
        - user_override_category
        - user_override_urgency
        - user_override_importance
        
        Returns:
            Anzahl Emails mit mindestens einer Korrektur
        """
        count = (
            self.db.query(ProcessedEmail)
            .join(ProcessedEmail.raw_email)
            .filter(
                ProcessedEmail.raw_email.has(mail_account_id=account_id),
                (
                    (ProcessedEmail.user_override_kategorie.isnot(None))
                    | (ProcessedEmail.user_override_dringlichkeit.isnot(None))
                    | (ProcessedEmail.user_override_wichtigkeit.isnot(None))
                ),
            )
            .count()
        )

        return count

    def should_trigger_sgd_learning(self, num_corrections: int) -> bool:
        """
        Prüft ob SGD Learning aktiviert werden soll.
        
        Args:
            num_corrections: Anzahl User-Korrekturen
            
        Returns:
            True wenn SGD trainiert werden sollte (≥20 Korrekturen)
        """
        return num_corrections >= 20

    def get_learning_phase(self, num_corrections: int) -> str:
        """
        Gibt aktuelle Lernphase zurück (für UI/Monitoring).
        
        Returns:
            - "initial": <20 Korrekturen (nur spaCy)
            - "learning": 20-50 Korrekturen (Hybrid)
            - "trained": 50+ Korrekturen (SGD-dominant)
        """
        if num_corrections < 20:
            return "initial"
        elif num_corrections < 50:
            return "learning"
        else:
            return "trained"

    # ===== ENSEMBLE SCORING LOGIC =====

    def compute_final_scores(
        self,
        account_id: int,
        email_content: str,
        spacy_pipeline_result: Dict,
        sgd_classifier=None,
    ) -> Dict[str, int]:
        """
        Kompletter Ensemble-Workflow: spaCy + SGD → finale Scores.
        
        Args:
            account_id: ID des Mail-Accounts
            email_content: Email-Text für SGD Prediction
            spacy_pipeline_result: Output von spaCy Hybrid Pipeline
                {"wichtigkeit": 3, "dringlichkeit": 2, "details": {...}}
            sgd_classifier: Optional - OnlineLearner Instanz für SGD Predictions
            
        Returns:
            Finale Scores: {"wichtigkeit": X, "dringlichkeit": Y}
        """
        # 1. spaCy Scores extrahieren
        spacy_scores = {
            "wichtigkeit": spacy_pipeline_result.get("wichtigkeit", 0),
            "dringlichkeit": spacy_pipeline_result.get("dringlichkeit", 0),
        }

        # 2. Anzahl Korrekturen prüfen
        num_corrections = self.get_correction_count(account_id)

        # 3. SGD Scores berechnen (falls SGD verfügbar)
        sgd_scores = {"wichtigkeit": 0, "dringlichkeit": 0}
        if sgd_classifier and self.should_trigger_sgd_learning(num_corrections):
            try:
                sgd_predictions = sgd_classifier.predict(email_content)
                sgd_scores = {
                    "wichtigkeit": sgd_predictions.get("wichtigkeit", 0),
                    "dringlichkeit": sgd_predictions.get("dringlichkeit", 0),
                }
            except Exception as e:
                # Fallback auf spaCy wenn SGD fehlschlägt
                print(f"⚠️  SGD Prediction failed: {e}")
                sgd_scores = {"wichtigkeit": 0, "dringlichkeit": 0}

        # 4. Ensemble-Kombination
        final_scores = self.combine_predictions(
            account_id=account_id,
            spacy_scores=spacy_scores,
            sgd_scores=sgd_scores,
            num_corrections=num_corrections,
        )

        return final_scores

    # ===== MONITORING & DEBUGGING =====

    def get_ensemble_stats(self, account_id: int) -> Dict:
        """
        Gibt Ensemble-Statistiken zurück (für UI/Monitoring).
        
        Returns:
            {
                "num_corrections": 35,
                "learning_phase": "learning",
                "spacy_weight": 30,
                "sgd_weight": 70,
                "sgd_enabled": True
            }
        """
        num_corrections = self.get_correction_count(account_id)
        spacy_weight, sgd_weight = self._get_weights(num_corrections)

        return {
            "num_corrections": num_corrections,
            "learning_phase": self.get_learning_phase(num_corrections),
            "spacy_weight": spacy_weight,
            "sgd_weight": sgd_weight,
            "sgd_enabled": self.should_trigger_sgd_learning(num_corrections),
        }
