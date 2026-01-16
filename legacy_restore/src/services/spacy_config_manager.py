"""
Phase Y: spaCy Hybrid Pipeline - Configuration Manager
Lädt und verwaltet Account-spezifische Konfigurationen für die spaCy Pipeline.
"""

import json
from typing import Dict, List, Optional
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

SpacyVIPSender = models.SpacyVIPSender
SpacyKeywordSet = models.SpacyKeywordSet
SpacyScoringConfig = models.SpacyScoringConfig
SpacyUserDomain = models.SpacyUserDomain


class SpacyConfigManager:
    """
    Zentrale Verwaltung für Phase Y Konfigurationen.
    
    Lädt und cached Account-Konfigurationen:
    - VIP-Absender mit Importance-Boost
    - 12 Keyword-Sets für verschiedene Kategorien
    - Scoring-Gewichte und Thresholds
    - User-Domains für intern/extern Detection
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self._cache: Dict[int, Dict] = {}  # {account_id: config_dict}

    def load_account_config(self, account_id: int) -> Dict:
        """
        Lädt vollständige Konfiguration für einen Account.
        
        Args:
            account_id: ID des Mail-Accounts
            
        Returns:
            Dict mit Keys: vip_senders, keyword_sets, scoring_config, user_domains
        """
        if account_id in self._cache:
            return self._cache[account_id]

        config = {
            "vip_senders": self._load_vip_senders(account_id),
            "keyword_sets": self._load_keyword_sets(account_id),
            "scoring_config": self._load_scoring_config(account_id),
            "user_domains": self._load_user_domains(account_id),
        }

        self._cache[account_id] = config
        return config

    def _load_vip_senders(self, account_id: int) -> List[Dict]:
        """Lädt VIP-Absender für Account."""
        vips = (
            self.db.query(SpacyVIPSender)
            .filter(
                SpacyVIPSender.account_id == account_id,
                SpacyVIPSender.is_active == True,
            )
            .all()
        )

        return [
            {
                "pattern": vip.sender_pattern.lower(),
                "type": vip.pattern_type,
                "boost": vip.importance_boost,
                "label": vip.label,
            }
            for vip in vips
        ]

    def _load_keyword_sets(self, account_id: int) -> Dict[str, List[str]]:
        """
        Lädt alle Keyword-Sets für Account.
        
        Returns:
            Dict mit 12 Keyword-Sets:
            {
                "imperative_verbs": ["prüfen", "freigeben", ...],
                "urgency_time": ["heute", "morgen", ...],
                ...
            }
        """
        keyword_sets = (
            self.db.query(SpacyKeywordSet)
            .filter(
                SpacyKeywordSet.account_id == account_id,
                SpacyKeywordSet.is_active == True,
            )
            .all()
        )

        result = {}
        for ks in keyword_sets:
            try:
                keywords = json.loads(ks.keywords_json)
                result[ks.set_type] = [kw.lower() for kw in keywords]
            except json.JSONDecodeError:
                result[ks.set_type] = []

        # Fallback auf Default-Sets wenn leer
        if not result:
            result = self._get_default_keyword_sets()

        return result

    def _load_scoring_config(self, account_id: int) -> Dict:
        """
        Lädt Scoring-Konfiguration für Account.
        
        Returns:
            Dict mit Gewichten und Thresholds
        """
        config = (
            self.db.query(SpacyScoringConfig)
            .filter(SpacyScoringConfig.account_id == account_id)
            .first()
        )

        if not config:
            # Fallback auf Default-Werte
            return self._get_default_scoring_config()

        return {
            "imperative_weight": config.imperative_weight,
            "deadline_weight": config.deadline_weight,
            "keyword_weight": config.keyword_weight,
            "vip_weight": config.vip_weight,
            "question_threshold": config.question_threshold,
            "negation_sensitivity": config.negation_sensitivity,
            "spacy_weight_initial": config.spacy_weight_initial,
            "spacy_weight_learning": config.spacy_weight_learning,
            "spacy_weight_trained": config.spacy_weight_trained,
        }

    def _load_user_domains(self, account_id: int) -> List[str]:
        """Lädt User-Domains für intern/extern Detection."""
        domains = (
            self.db.query(SpacyUserDomain)
            .filter(
                SpacyUserDomain.account_id == account_id,
                SpacyUserDomain.is_active == True,
            )
            .all()
        )

        return [d.domain.lower() for d in domains]

    def clear_cache(self, account_id: Optional[int] = None):
        """Löscht Cache (z.B. nach Config-Änderungen)."""
        if account_id:
            self._cache.pop(account_id, None)
        else:
            self._cache.clear()

    # ===== DEFAULT CONFIGURATIONS =====

    def _get_default_keyword_sets(self) -> Dict[str, List[str]]:
        """
        80 Keywords verteilt auf 12 Sets (Hybrid-Ansatz).
        spaCy NLP übernimmt 80% der Arbeit, Keywords sind Fallback.
        """
        return {
            # 1. Imperative Verben (10 Keywords)
            # spaCy Parser erkennt Imperative automatisch, Keywords sind Fallback
            "imperative_verbs": [
                "prüfen",
                "freigeben",
                "bestätigen",
                "unterschreiben",
                "genehmigen",
                "autorisieren",
                "entscheiden",
                "antworten",
                "ergänzen",
                "korrigieren",
            ],
            # 2. Dringlichkeits-Zeit (8 Keywords)
            "urgency_time": [
                "heute",
                "morgen",
                "asap",
                "dringend",
                "sofort",
                "umgehend",
                "schnellstmöglich",
                "eilt",
            ],
            # 3. Deadline-Marker (7 Keywords)
            # spaCy NER erkennt Daten, Keywords ergänzen Formulierungen
            "deadline_markers": [
                "deadline",
                "frist",
                "termin",
                "spätestens",
                "stichtag",
                "zeitlimit",
                "ablauf",
            ],
            # 4. Nachfrage-Signale (6 Keywords)
            "follow_up_signals": [
                "nachfrage",
                "erinnerung",
                "mahnung",
                "rückmeldung",
                "status",
                "update",
            ],
            # 5. Fragewörter (7 Keywords)
            # Senken Urgency (reine Info-Anfrage statt Aktion)
            "question_words": [
                "warum",
                "wieso",
                "weshalb",
                "wie",
                "wann",
                "wo",
                "wer",
            ],
            # 6. Negations-Begriffe (6 Keywords)
            # spaCy Dependency Parsing erkennt Negationen, Keywords ergänzen
            "negation_terms": [
                "nicht",
                "kein",
                "keine",
                "niemals",
                "nie",
                "nichts",
            ],
            # 7. Eskalations-Wörter (8 Keywords)
            "escalation_words": [
                "beschwerde",
                "reklamation",
                "problem",
                "fehler",
                "dringlichkeit",
                "eskalation",
                "kritisch",
                "notfall",
            ],
            # 8. Vertraulichkeits-Marker (6 Keywords)
            "confidential_markers": [
                "vertraulich",
                "geheim",
                "intern",
                "confidential",
                "nda",
                "vertraulichkeit",
            ],
            # 9. Vertrags-Begriffe (7 Keywords)
            "contract_terms": [
                "vertrag",
                "vereinbarung",
                "vertragsänderung",
                "kündigung",
                "verlängerung",
                "konditionen",
                "klausel",
            ],
            # 10. Finanz-Wörter (6 Keywords)
            "financial_words": [
                "rechnung",
                "zahlung",
                "budget",
                "kosten",
                "bezahlung",
                "faktura",
            ],
            # 11. Meeting-Begriffe (5 Keywords)
            "meeting_terms": [
                "meeting",
                "besprechung",
                "call",
                "termin",
                "telefonat",
            ],
            # 12. Absender-Hierarchie (4 Keywords)
            # Ergänzt VIP-System für flexible Matching
            "sender_hierarchy": [
                "geschäftsführung",
                "vorstand",
                "direktion",
                "leitung",
            ],
        }

    def _get_default_scoring_config(self) -> Dict:
        """Default Scoring-Konfiguration."""
        return {
            # Gewichte für Detektoren
            "imperative_weight": 3,
            "deadline_weight": 4,
            "keyword_weight": 2,
            "vip_weight": 3,
            # Thresholds
            "question_threshold": 3,  # Min. 3 Fragewörter für Urgency-Reduktion
            "negation_sensitivity": 2,  # Negationen senken Score um 2
            # Ensemble-Gewichte (dynamisch basierend auf Lernfortschritt)
            "spacy_weight_initial": 100,  # <20 Korrekturen: 100% spaCy
            "spacy_weight_learning": 30,  # 20-50 Korrekturen: 30% spaCy + 70% SGD
            "spacy_weight_trained": 15,  # 50+ Korrekturen: 15% spaCy + 85% SGD
        }

    # ===== HELPER METHODS =====

    def get_vip_boost(self, account_id: int, sender_email: str) -> int:
        """
        Prüft ob Absender VIP ist und gibt Boost zurück.
        
        Args:
            account_id: ID des Mail-Accounts
            sender_email: Email-Adresse des Absenders (z.B. "boss@example.com")
            
        Returns:
            Importance Boost (0 bis +5)
        """
        config = self.load_account_config(account_id)
        sender_email = sender_email.lower()
        sender_domain = sender_email.split("@")[-1] if "@" in sender_email else ""

        max_boost = 0
        for vip in config["vip_senders"]:
            if vip["type"] == "email" and vip["pattern"] == sender_email:
                max_boost = max(max_boost, vip["boost"])
            elif vip["type"] == "domain" and sender_domain == vip["pattern"]:
                max_boost = max(max_boost, vip["boost"])

        return max_boost

    def is_internal_email(self, account_id: int, sender_email: str) -> bool:
        """
        Prüft ob Email intern ist (gleiche Domain wie User).
        
        Externe Emails erhalten höhere Urgency/Importance.
        """
        config = self.load_account_config(account_id)
        sender_domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""

        return sender_domain in config["user_domains"]

    def get_keywords(self, account_id: int, set_name: str) -> List[str]:
        """Gibt spezifisches Keyword-Set zurück."""
        config = self.load_account_config(account_id)
        return config["keyword_sets"].get(set_name, [])

    def get_scoring_weight(self, account_id: int, weight_name: str) -> int:
        """Gibt spezifisches Scoring-Gewicht zurück."""
        config = self.load_account_config(account_id)
        return config["scoring_config"].get(weight_name, 0)
