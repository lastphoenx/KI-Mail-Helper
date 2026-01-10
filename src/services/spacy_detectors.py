"""
Phase Y2: spaCy Hybrid Detectors
Intelligente NLP-basierte Detection für Urgency/Importance Scoring.
"""

import spacy
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import re


class SpacyDetectorBase:
    """Base Class für alle spaCy Detectors."""

    def __init__(self, nlp=None):
        self.nlp = nlp or spacy.load("de_core_news_md")

    def analyze(self, text: str) -> Dict:
        """
        Analysiert Text und gibt Ergebnis zurück.
        
        Returns:
            Dict mit detector-spezifischen Ergebnissen
        """
        raise NotImplementedError


class ImperativeDetector(SpacyDetectorBase):
    """
    Erkennt Imperative (Befehle/Aufforderungen) mittels spaCy Parser.
    
    Imperative = Hohe Urgency/Importance (Handlungsaufforderung)
    
    spaCy Features:
    - Dependency Parser: Erkennt Verb-Modus (IMPERATIVE vs. INDICATIVE)
    - Morphology: token.morph.get("Mood") = "Imp"
    - POS-Tags: VERB am Satzanfang + keine Subjekt-Abhängigkeit
    
    Beispiele:
    - "Prüfen Sie bitte das Dokument" → Imperativ erkannt
    - "Könnten Sie das prüfen?" → Höfliche Anfrage (kein direkter Imperativ)
    - "Sie sollten das prüfen" → Empfehlung (kein Imperativ)
    """

    def analyze(self, text: str, keyword_fallback: List[str] = None) -> Dict:
        """
        Erkennt Imperative im Text.
        
        Args:
            text: Email-Text (Subject + Body)
            keyword_fallback: Fallback-Keywords falls spaCy nichts findet
            
        Returns:
            {
                "imperative_count": 2,
                "imperative_verbs": ["prüfen", "freigeben"],
                "urgency_boost": 3,  # +1 bis +5
                "details": "2 Imperative erkannt: prüfen, freigeben"
            }
        """
        doc = self.nlp(text[:2000])  # Limit für Performance
        imperatives = []

        # Deutsche Imperative sind schwierig für spaCy
        # Heuristik: Verb + "Sie" / "bitte" / Infinitiv am Satzanfang
        
        for sent in doc.sents:
            sent_text = sent.text.lower()
            
            # Methode 1: Morphologie-Check (falls erkannt)
            for token in sent:
                if token.pos_ == "VERB" and "Imp" in token.morph.get("Mood", []):
                    imperatives.append(token.lemma_.lower())
                    continue
            
            # Methode 2: Höfliche Form "bitte" + Verb
            if "bitte" in sent_text:
                for token in sent:
                    if token.pos_ == "VERB":
                        imperatives.append(token.lemma_.lower())
            
            # Methode 3: Verb + "Sie" (höflicher Imperativ)
            for i, token in enumerate(sent):
                if token.pos_ == "VERB" and i+1 < len(sent):
                    next_token = list(sent)[i+1]
                    if next_token.text.lower() == "sie":
                        imperatives.append(token.lemma_.lower())

        # Fallback: Keyword-Matching (wichtig für deutsche Emails!)
        if not imperatives and keyword_fallback:
            text_lower = text.lower()
            for kw in keyword_fallback:
                # Suche nach Keyword mit Kontext "bitte", "könnten", etc.
                if kw in text_lower:
                    context_words = ["bitte", "könnten", "würden", "sollten", "müssen"]
                    for ctx in context_words:
                        if ctx in text_lower:
                            imperatives.append(kw)
                            break

        # Scoring: Je mehr Imperative, desto höher Urgency
        imperative_count = len(set(imperatives))  # Unique count
        if imperative_count >= 3:
            urgency_boost = 5
        elif imperative_count == 2:
            urgency_boost = 4
        elif imperative_count == 1:
            urgency_boost = 3
        else:
            urgency_boost = 0

        return {
            "imperative_count": imperative_count,
            "imperative_verbs": list(set(imperatives))[:5],  # Max 5 für Übersicht
            "urgency_boost": urgency_boost,
            "details": f"{imperative_count} Imperative erkannt: {', '.join(list(set(imperatives))[:3])}"
            if imperatives
            else "Keine Imperative erkannt",
        }


class DeadlineDetector(SpacyDetectorBase):
    """
    Erkennt Deadlines/Termine mittels spaCy NER + Pattern Matching.
    
    spaCy Features:
    - Named Entity Recognition (NER): Erkennt DATE entities
    - Lemmatizer: "morgen", "heute", "nächste Woche"
    - Context-Aware: "bis Freitag", "spätestens 15.01."
    
    Urgency-Logik:
    - Heute/Morgen → Sehr hohe Urgency (+5)
    - Diese Woche → Hohe Urgency (+4)
    - Nächste Woche → Mittlere Urgency (+3)
    - >2 Wochen → Niedrige Urgency (+1)
    """

    # Deadline-Keywords für Context-Matching
    DEADLINE_MARKERS = [
        "deadline",
        "frist",
        "termin",
        "spätestens",
        "bis",
        "stichtag",
        "ablauf",
        "zeitlimit",
    ]

    TIME_URGENCY_MAP = {
        "heute": 5,
        "heute abend": 5,
        "heute nachmittag": 5,
        "morgen": 5,
        "morgen früh": 5,
        "asap": 5,
        "sofort": 5,
        "umgehend": 5,
        "diese woche": 4,
        "diese woche noch": 4,
        "nächste woche": 3,
        "nächsten monat": 2,
    }

    def analyze(self, text: str, keyword_fallback: List[str] = None) -> Dict:
        """
        Erkennt Deadlines und berechnet Urgency basierend auf Zeitnähe.
        
        Returns:
            {
                "deadline_detected": True,
                "deadline_date": "2026-01-10",
                "days_until": 2,
                "urgency_boost": 5,
                "details": "Deadline in 2 Tagen: Freitag"
            }
        """
        doc = self.nlp(text[:2000])
        deadlines = []
        urgency_boost = 0

        # 1. spaCy NER: DATE entities
        for ent in doc.ents:
            if ent.label_ == "DATE":
                deadlines.append(ent.text)

        # 2. Pattern Matching: Deadline-Keywords + Date
        text_lower = text.lower()
        for marker in self.DEADLINE_MARKERS:
            if marker in text_lower:
                # Extrahiere Kontext (20 Zeichen nach Marker)
                idx = text_lower.find(marker)
                context = text_lower[idx : idx + 50]
                # Prüfe auf Zeit-Keywords im Kontext
                for time_phrase, urgency in self.TIME_URGENCY_MAP.items():
                    if time_phrase in context:
                        deadlines.append(f"{marker} {time_phrase}")
                        urgency_boost = max(urgency_boost, urgency)

        # 3. Zeitnähe-Urgency aus NER Dates berechnen
        if not urgency_boost:
            urgency_boost = self._calculate_date_urgency(deadlines)

        # 4. Fallback: Keyword-Only Matching
        if not deadlines and keyword_fallback:
            for kw in keyword_fallback:
                if kw in text_lower:
                    deadlines.append(kw)
                    urgency_boost = max(urgency_boost, 2)  # Moderate Urgency

        return {
            "deadline_detected": bool(deadlines),
            "deadlines": deadlines[:3],  # Max 3 für Übersicht
            "urgency_boost": urgency_boost,
            "details": f"Deadline erkannt: {deadlines[0]}" if deadlines else "Keine Deadline",
        }

    def _calculate_date_urgency(self, deadlines: List[str]) -> int:
        """
        Berechnet Urgency basierend auf erkannten Datums-Strings.
        
        Heuristik für deutsche Datumsformate:
        - "Freitag" / Wochentage → Diese Woche
        - "15.01." / DD.MM. → Parse Date
        """
        # Vereinfachte Heuristik (kann später mit dateparser erweitert werden)
        text_combined = " ".join(deadlines).lower()

        if any(word in text_combined for word in ["heute", "morgen", "asap"]):
            return 5
        if any(
            word in text_combined for word in ["diese woche", "diese woche", "freitag"]
        ):
            return 4
        if "nächste woche" in text_combined:
            return 3

        return 1  # Default für erkannte Deadline ohne klare Zeitangabe


class KeywordDetector(SpacyDetectorBase):
    """
    Keyword-Matching mit spaCy Lemmatizer für robustes Matching.
    
    Vorteil Lemmatizer:
    - 1 Keyword "prüfen" matched: prüfen, prüfe, prüfst, prüft, geprüft, prüfend
    - Reduziert Keyword-Menge von 200 auf 80 Keywords
    
    12 Keyword-Sets aus SpacyConfigManager:
    1. imperative_verbs (Fallback für ImperativeDetector)
    2. urgency_time
    3. deadline_markers
    4. follow_up_signals
    5. question_words (senkt Urgency)
    6. negation_terms
    7. escalation_words
    8. confidential_markers
    9. contract_terms
    10. financial_words
    11. meeting_terms
    12. sender_hierarchy
    """

    def analyze(
        self, text: str, keyword_sets: Dict[str, List[str]], weights: Dict[str, int]
    ) -> Dict:
        """
        Matched Keywords und berechnet gewichteten Score.
        
        Args:
            text: Email-Text
            keyword_sets: 12 Keyword-Sets aus Config Manager
            weights: Gewichte pro Set (z.B. {"urgency_time": 4, "question_words": -2})
            
        Returns:
            {
                "matched_sets": {"urgency_time": 2, "escalation_words": 1},
                "total_score": 10,
                "details": "2x Urgency-Time, 1x Eskalation"
            }
        """
        doc = self.nlp(text[:2000])
        lemmas = [token.lemma_.lower() for token in doc if not token.is_punct]

        matched_sets = {}
        total_score = 0

        for set_name, keywords in keyword_sets.items():
            match_count = sum(1 for kw in keywords if kw in lemmas)
            if match_count > 0:
                matched_sets[set_name] = match_count
                weight = weights.get(set_name, 1)
                total_score += match_count * weight

        details_parts = [
            f"{count}x {set_name}" for set_name, count in matched_sets.items()
        ]

        return {
            "matched_sets": matched_sets,
            "total_score": total_score,
            "details": ", ".join(details_parts[:3]) if details_parts else "Keine Keywords",
        }


class QuestionDetector(SpacyDetectorBase):
    """
    Erkennt Fragen (senken Urgency, da oft Info-Anfragen statt Aktionen).
    
    Features:
    - Fragewörter: warum, wieso, wie, wann, wo, wer
    - Dependency Parsing: Fragesätze haben spezielle Struktur
    - Satzzeichen: "?" am Satzende
    
    Logik:
    - 1-2 Fragen → Leichte Urgency-Reduktion (-1)
    - 3+ Fragen → Starke Urgency-Reduktion (-2 bis -3)
    """

    QUESTION_WORDS = [
        "warum",
        "wieso",
        "weshalb",
        "wie",
        "wann",
        "wo",
        "wer",
        "welche",
        "welcher",
        "welches",
    ]

    def analyze(self, text: str) -> Dict:
        """
        Zählt Fragen im Text.
        
        Returns:
            {
                "question_count": 3,
                "urgency_penalty": -2,
                "details": "3 Fragen erkannt (Info-Anfrage)"
            }
        """
        doc = self.nlp(text[:2000])

        question_count = 0

        # Methode 1: Fragewörter zählen
        for token in doc:
            if token.lemma_.lower() in self.QUESTION_WORDS:
                question_count += 1

        # Methode 2: Sätze mit "?" zählen
        question_marks = text.count("?")
        question_count = max(question_count, question_marks)

        # Penalty berechnen
        if question_count >= 3:
            urgency_penalty = -3
        elif question_count == 2:
            urgency_penalty = -2
        elif question_count == 1:
            urgency_penalty = -1
        else:
            urgency_penalty = 0

        return {
            "question_count": question_count,
            "urgency_penalty": urgency_penalty,
            "details": f"{question_count} Fragen erkannt (Info-Anfrage)"
            if question_count > 0
            else "Keine Fragen",
        }


class NegationDetector(SpacyDetectorBase):
    """
    Erkennt Negationen mittels spaCy Dependency Parsing.
    
    Negationen können Urgency reduzieren:
    - "Sie müssen NICHT antworten" → Niedrige Urgency
    - "Kein Problem wenn später" → Niedrige Urgency
    
    spaCy Dependencies:
    - "neg" dependency: Negations-Marker
    - Context-Aware: Negation + Imperativ-Verb
    """

    def analyze(self, text: str) -> Dict:
        """
        Erkennt Negationen und deren Kontext.
        
        Returns:
            {
                "negation_count": 2,
                "urgency_penalty": -2,
                "details": "2 Negationen: nicht, kein"
            }
        """
        doc = self.nlp(text[:2000])

        negations = []

        for token in doc:
            # spaCy Dependency: "neg" = Negation
            if token.dep_ == "ng" or token.dep_ == "neg":
                negations.append(token.text.lower())

            # Zusätzlich: Häufige Negations-Wörter
            if token.lemma_.lower() in ["nicht", "kein", "keine", "niemals", "nie"]:
                negations.append(token.lemma_.lower())

        negation_count = len(set(negations))

        # Penalty: Negationen senken Urgency
        if negation_count >= 2:
            urgency_penalty = -3
        elif negation_count == 1:
            urgency_penalty = -2
        else:
            urgency_penalty = 0

        return {
            "negation_count": negation_count,
            "urgency_penalty": urgency_penalty,
            "details": f"{negation_count} Negationen: {', '.join(list(set(negations))[:3])}"
            if negations
            else "Keine Negationen",
        }


class VIPDetector:
    """
    Prüft ob Absender VIP ist (ohne spaCy, nutzt Config Manager).
    
    VIP = Höhere Importance (Chef, Kunde, Partner)
    """

    def __init__(self, config_manager):
        self.config_manager = config_manager

    def analyze(self, account_id: int, sender_email: str) -> Dict:
        """
        Prüft VIP-Status des Absenders.
        
        Returns:
            {
                "is_vip": True,
                "importance_boost": 5,
                "details": "VIP: Geschäftsführung"
            }
        """
        boost = self.config_manager.get_vip_boost(account_id, sender_email)

        return {
            "is_vip": boost > 0,
            "importance_boost": boost,
            "details": f"VIP-Boost: +{boost}" if boost > 0 else "Kein VIP",
        }


class InternalExternalDetector:
    """
    Erkennt ob Email intern oder extern ist.
    
    Externe Emails = Höhere Urgency/Importance (Kunden, Partner)
    Interne Emails = Niedrigere Urgency (Kollegen)
    """

    def __init__(self, config_manager):
        self.config_manager = config_manager

    def analyze(self, account_id: int, sender_email: str) -> Dict:
        """
        Prüft ob Email intern ist.
        
        Returns:
            {
                "is_internal": False,
                "urgency_boost": 2,
                "importance_boost": 1,
                "details": "Externe Email (Kunde/Partner)"
            }
        """
        is_internal = self.config_manager.is_internal_email(account_id, sender_email)

        if is_internal:
            return {
                "is_internal": True,
                "urgency_boost": 0,
                "importance_boost": 0,
                "details": "Interne Email",
            }
        else:
            return {
                "is_internal": False,
                "urgency_boost": 2,
                "importance_boost": 1,
                "details": "Externe Email (Kunde/Partner)",
            }
