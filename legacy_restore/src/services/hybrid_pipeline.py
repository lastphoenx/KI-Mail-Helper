"""
Phase Y2: Hybrid Pipeline
Kombiniert 8 Detektoren + Ensemble Learning für finale Scores.
"""

import spacy
from typing import Dict, Tuple
from sqlalchemy.orm import Session

from src.services.spacy_detectors import (
    ImperativeDetector,
    DeadlineDetector,
    KeywordDetector,
    QuestionDetector,
    NegationDetector,
    VIPDetector,
    InternalExternalDetector,
)
from src.services.spacy_config_manager import SpacyConfigManager
from src.services.ensemble_combiner import EnsembleCombiner


class HybridPipeline:
    """
    Phase Y Hybrid Pipeline: spaCy NLP + Keywords + Ensemble Learning.
    
    Workflow:
    1. Lade spaCy Modell (de_core_news_md)
    2. Initialisiere 8 Detektoren
    3. Analysiere Email mit allen Detektoren
    4. Kombiniere Ergebnisse zu spaCy-Scores
    5. Ensemble: spaCy + SGD → Finale Scores
    
    Architektur:
    [Email] → [8 Detectors] → [spaCy Scores] → [Ensemble] → [Final Scores]
                                                    ↑
                                                 [SGD ML]
    """

    def __init__(self, db_session: Session, sgd_classifier=None):
        """
        Initialisiert Hybrid Pipeline.
        
        Args:
            db_session: SQLAlchemy Session
            sgd_classifier: Optional OnlineLearner für SGD Predictions
        """
        self.db = db_session
        self.sgd_classifier = sgd_classifier

        # spaCy Modell laden (cached)
        self.nlp = spacy.load("de_core_news_md")

        # Config Manager
        self.config_manager = SpacyConfigManager(db_session)

        # Ensemble Combiner
        self.ensemble = EnsembleCombiner(db_session)

        # 8 Detektoren initialisieren
        self.imperative_detector = ImperativeDetector(self.nlp)
        self.deadline_detector = DeadlineDetector(self.nlp)
        self.keyword_detector = KeywordDetector(self.nlp)
        self.question_detector = QuestionDetector(self.nlp)
        self.negation_detector = NegationDetector(self.nlp)
        self.vip_detector = VIPDetector(self.config_manager)
        self.internal_external_detector = InternalExternalDetector(self.config_manager)

    def analyze(
        self, account_id: int, sender_email: str, subject: str, body: str
    ) -> Dict:
        """
        Vollständige Analyse einer Email.
        
        Args:
            account_id: ID des Mail-Accounts
            sender_email: Absender (z.B. "boss@example.com")
            subject: Email-Betreff
            body: Email-Body
            
        Returns:
            {
                "wichtigkeit": 4,  # 1-5
                "dringlichkeit": 3,  # 1-5
                "spacy_details": {...},  # Raw Detector Results
                "ensemble_stats": {...},  # Ensemble Learning Stats
                "final_method": "ensemble"  # "spacy_only" oder "ensemble"
            }
        """
        # Volltext für NLP-Analyse
        full_text = f"{subject}\n\n{body}"

        # Account-Config laden
        config = self.config_manager.load_account_config(account_id)
        scoring_config = config["scoring_config"]
        keyword_sets = config["keyword_sets"]

        # ===== 1. ALLE DETEKTOREN AUSFÜHREN =====

        # NLP Detektoren
        imperative_result = self.imperative_detector.analyze(
            full_text, keyword_fallback=keyword_sets.get("imperative_verbs", [])
        )

        deadline_result = self.deadline_detector.analyze(
            full_text, keyword_fallback=keyword_sets.get("deadline_markers", [])
        )

        # Keyword-Gewichte definieren
        keyword_weights = {
            "urgency_time": 4,
            "deadline_markers": 4,
            "escalation_words": 3,
            "follow_up_signals": 3,
            "confidential_markers": 2,
            "contract_terms": 2,
            "financial_words": 2,
            "meeting_terms": 1,
            "question_words": -2,  # Senkt Urgency
            "negation_terms": -2,  # Senkt Urgency
        }

        keyword_result = self.keyword_detector.analyze(
            full_text, keyword_sets, keyword_weights
        )

        question_result = self.question_detector.analyze(full_text)
        negation_result = self.negation_detector.analyze(full_text)

        # Sender-basierte Detektoren
        vip_result = self.vip_detector.analyze(account_id, sender_email)
        internal_external_result = self.internal_external_detector.analyze(
            account_id, sender_email
        )

        # ===== 2. SPACY SCORES BERECHNEN =====

        spacy_scores = self._calculate_spacy_scores(
            imperative_result=imperative_result,
            deadline_result=deadline_result,
            keyword_result=keyword_result,
            question_result=question_result,
            negation_result=negation_result,
            vip_result=vip_result,
            internal_external_result=internal_external_result,
            scoring_config=scoring_config,
        )

        # ===== 3. ENSEMBLE: SPACY + SGD =====

        final_scores = self.ensemble.compute_final_scores(
            account_id=account_id,
            email_content=full_text,
            spacy_pipeline_result=spacy_scores,
            sgd_classifier=self.sgd_classifier,
        )

        # ===== 4. ERGEBNIS ZUSAMMENSTELLEN =====

        return {
            "wichtigkeit": final_scores["wichtigkeit"],
            "dringlichkeit": final_scores["dringlichkeit"],
            "spacy_details": {
                "imperative": imperative_result,
                "deadline": deadline_result,
                "keywords": keyword_result,
                "questions": question_result,
                "negations": negation_result,
                "vip": vip_result,
                "internal_external": internal_external_result,
                "spacy_wichtigkeit": spacy_scores["wichtigkeit"],
                "spacy_dringlichkeit": spacy_scores["dringlichkeit"],
            },
            "ensemble_stats": self.ensemble.get_ensemble_stats(account_id),
            "final_method": "ensemble"
            if self.ensemble.should_trigger_sgd_learning(
                self.ensemble.get_correction_count(account_id)
            )
            else "spacy_only",
        }

    def _calculate_spacy_scores(
        self,
        imperative_result: Dict,
        deadline_result: Dict,
        keyword_result: Dict,
        question_result: Dict,
        negation_result: Dict,
        vip_result: Dict,
        internal_external_result: Dict,
        scoring_config: Dict,
    ) -> Dict[str, int]:
        """
        Berechnet Wichtigkeit/Dringlichkeit aus Detector-Ergebnissen.
        
        Scoring-Formel:
        - Dringlichkeit = Imperative + Deadline + Keywords - Questions - Negations + External
        - Wichtigkeit = VIP + Keywords + Imperative + External
        
        Returns:
            {"wichtigkeit": 4, "dringlichkeit": 3}
        """
        # ===== DRINGLICHKEIT (Urgency) =====

        urgency_raw = 0

        # Imperative → Hohe Dringlichkeit
        urgency_raw += imperative_result["urgency_boost"] * scoring_config.get(
            "imperative_weight", 3
        )

        # Deadlines → Sehr hohe Dringlichkeit
        urgency_raw += deadline_result["urgency_boost"] * scoring_config.get(
            "deadline_weight", 4
        )

        # Keywords → Moderate Dringlichkeit
        urgency_raw += keyword_result["total_score"] * scoring_config.get(
            "keyword_weight", 2
        )

        # External → Externe Emails dringender
        urgency_raw += internal_external_result["urgency_boost"]

        # Fragen → Senken Dringlichkeit (Info-Anfrage)
        urgency_raw += question_result["urgency_penalty"] * scoring_config.get(
            "question_threshold", 1
        )

        # Negationen → Senken Dringlichkeit
        urgency_raw += negation_result["urgency_penalty"] * scoring_config.get(
            "negation_sensitivity", 2
        )

        # ===== WICHTIGKEIT (Importance) =====

        importance_raw = 0

        # VIP → Sehr hohe Wichtigkeit
        importance_raw += vip_result["importance_boost"] * scoring_config.get(
            "vip_weight", 3
        )

        # External → Externe Emails wichtiger
        importance_raw += internal_external_result["importance_boost"]

        # Imperative → Moderate Wichtigkeit (Handlungsaufforderung)
        importance_raw += imperative_result["urgency_boost"] * 0.5

        # Keywords → Moderate Wichtigkeit
        importance_raw += keyword_result["total_score"] * 0.3

        # ===== NORMALISIERUNG AUF 1-5 SKALA =====

        dringlichkeit = self._normalize_score(urgency_raw, min_val=-10, max_val=30)
        wichtigkeit = self._normalize_score(importance_raw, min_val=-5, max_val=25)

        return {"dringlichkeit": dringlichkeit, "wichtigkeit": wichtigkeit}

    def _normalize_score(self, raw_score: float, min_val: int, max_val: int) -> int:
        """
        Normalisiert Raw-Score auf 1-5 Skala.
        
        Args:
            raw_score: Berechneter Score (kann negativ sein)
            min_val: Minimum-Erwartungswert
            max_val: Maximum-Erwartungswert
            
        Returns:
            Normalisierter Score zwischen 1 und 5
        """
        # Clamp auf [min_val, max_val]
        clamped = max(min_val, min(max_val, raw_score))

        # Linear mapping auf [1, 5]
        normalized = 1 + (clamped - min_val) / (max_val - min_val) * 4

        # Auf Integer runden
        return max(1, min(5, round(normalized)))

    def get_pipeline_stats(self) -> Dict:
        """
        Gibt Pipeline-Statistiken zurück (für Monitoring/Debugging).
        
        Returns:
            {
                "spacy_model": "de_core_news_md",
                "detectors_count": 8,
                "cache_size": 5
            }
        """
        return {
            "spacy_model": self.nlp.meta["name"],
            "spacy_version": self.nlp.meta["version"],
            "detectors_count": 7,  # 7 spaCy + 1 VIP + 1 Internal/External
            "config_cache_size": len(self.config_manager._cache),
        }
