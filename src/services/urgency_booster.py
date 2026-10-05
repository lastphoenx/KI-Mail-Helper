"""
UrgencyBooster - Entity-basierte Dringlichkeits-Erkennung mit spaCy (Phase X)

Nutzt Named Entity Recognition (NER) für schnelle Email-Klassifikation:
- Zeitdruck-Erkennung: Deadlines in <48h
- Geldbeträge: Rechnungen >1000€
- Action-Verben: senden, überweisen, dringend

Performance: ~100-300ms pro Email (vs. 5-10 Min LLM-Call)

WICHTIG: Läuft NUR auf Trusted Senders (User-definiert)!
         Schützt vor Marketing/Scam-False-Positives.
"""

import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError

logger = logging.getLogger(__name__)


def safe_regex_search(pattern: str, text: str, timeout_seconds: int = 2) -> Optional[re.Match]:
    """
    Thread-safe regex search with timeout using ThreadPoolExecutor.
    Works in background threads (unlike signal.alarm()).
    
    Args:
        pattern: Regex pattern
        text: Text to search in
        timeout_seconds: Timeout in seconds
    
    Returns:
        Match object or None
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(re.search, pattern, text, re.IGNORECASE)
            return future.result(timeout=timeout_seconds)
    except TimeoutError:
        logger.warning(f"⚠️ Regex timeout on pattern: {pattern[:80]}...")
        return None
    except Exception as e:
        logger.error(f"Error in safe_regex_search: {e}")
        return None

_spacy_de = None
_spacy_lock = threading.Lock()

ACTION_VERBS_SET = {
    'senden', 'schicken', 'überweisen', 'bezahlen',
    'bestätigen', 'antworten', 'rückmelden',
    'prüfen', 'genehmigen', 'unterschreiben',
    'bitte', 'könntest', 'würdest', 'kannst',
    'müssen', 'sollten', 'brauche', 'benötige',
    'erledigen', 'abschließen', 'bearbeiten', 'klären'
}

AUTHORITY_TITLES_SET = {
    'ceo', 'geschäftsführer', 'direktor',
    'vorstand', 'präsident', 'chef'
}

INVOICE_KEYWORDS_SET = {
    'rechnung', 'invoice', 'zahlungserinnerung',
    'rechnungsnummer', 'payment reminder'
}


def _load_spacy_de():
    """Lädt deutsches spaCy Model (lazy) mit Thread-Safety"""
    global _spacy_de
    if _spacy_de is None:
        with _spacy_lock:
            if _spacy_de is None:
                try:
                    import spacy
                    _spacy_de = spacy.load("de_core_news_sm")
                    logger.info("✅ spaCy Deutsch-Model geladen (de_core_news_sm)")
                except Exception as e:
                    logger.warning(f"⚠️ spaCy Deutsch-Model konnte nicht geladen werden: {e}")
                    logger.warning(f"   Installieren Sie mit: python -m spacy download de_core_news_sm")
                    _spacy_de = False
    return _spacy_de if _spacy_de else None


class UrgencyBooster:
    """Entity-basierte Dringlichkeits-Erkennung mit spaCy NER."""
    
    HIGH_URGENCY_THRESHOLD = 0.7
    CONFIDENCE_THRESHOLD = 0.5
    
    def __init__(self, language: str = "de"):
        self.language = language
        self.nlp = _load_spacy_de() if language == "de" else None
        
        if not self.nlp:
            logger.warning(f"⚠️ UrgencyBooster: spaCy {language} nicht verfügbar")
    
    def analyze_urgency(self, subject: str, body: str, sender: str = "") -> Dict:
        """
        Hauptmethode: Analysiert Email auf Dringlichkeit.
        
        Returns:
            {
                'urgency_score': float (0-1),
                'importance_score': float (0-1),
                'category': str,
                'confidence': float (0-1),
                'signals': dict,
                'method': 'entity_rules'
            }
        """
        if not self.nlp:
            return self._fallback_heuristics(subject, body)
        
        text = f"{subject} {body[:1000]}"
        doc = self.nlp(text)
        
        signals = {
            'time_pressure': False,
            'deadline_hours': None,
            'money_amount': None,
            'action_verbs': [],
            'authority_person': False,
            'invoice_detected': False
        }
        
        urgency_score = 0.0
        importance_score = 0.0
        
        # 1. ZEITDRUCK
        deadline_info = self._analyze_deadlines(doc, text)
        if deadline_info['has_deadline']:
            signals['time_pressure'] = True
            signals['deadline_hours'] = deadline_info['hours_until']
            
            if deadline_info['hours_until'] and deadline_info['hours_until'] < 24:
                urgency_score += 0.4
            elif deadline_info['hours_until'] and deadline_info['hours_until'] < 48:
                urgency_score += 0.3
            else:
                urgency_score += 0.2
        
        # 2. GELDBETRÄGE
        money_info = self._analyze_money(doc, text)
        if money_info['amount']:
            signals['money_amount'] = money_info['amount']
            importance_score += 0.3
            
            if money_info['amount'] > 5000:
                importance_score += 0.2
            
            if self._is_invoice(text):
                signals['invoice_detected'] = True
                urgency_score += 0.3
                importance_score += 0.2
        
        # 3. ACTION-VERBEN
        action_verbs = self._extract_action_verbs(doc, text)
        if action_verbs:
            signals['action_verbs'] = action_verbs
            urgency_score += min(len(action_verbs) * 0.15, 0.4)
        
        # 4. AUTORITÄTS-PERSONEN
        if self._has_authority_person(doc, text, sender):
            signals['authority_person'] = True
            importance_score += 0.3
            urgency_score += 0.2
        
        # Normalize
        urgency_score = min(urgency_score, 1.0)
        importance_score = min(importance_score, 1.0)
        
        # Kategorie
        if urgency_score >= 0.7 or signals['invoice_detected']:
            category = "dringend"
        elif urgency_score >= 0.4 or signals['action_verbs']:
            category = "aktion_erforderlich"
        else:
            category = "nur_information"
        
        # Confidence
        confidence = self._calculate_confidence(signals, urgency_score)
        
        # Debug-Logging für Trusted Senders
        logger.info(
            f"📊 UrgencyBooster Analysis: "
            f"urgency={urgency_score:.2f}, importance={importance_score:.2f}, "
            f"category={category}, confidence={confidence:.2f}, "
            f"signals={sum([1 for k, v in signals.items() if v and k != 'deadline_hours' and k != 'money_amount'])}"
        )
        
        return {
            'urgency_score': urgency_score,
            'importance_score': importance_score,
            'category': category,
            'confidence': confidence,
            'signals': signals,
            'method': 'entity_rules'
        }
    
    def _analyze_deadlines(self, doc, text: str) -> Dict:
        """Extrahiert Deadline-Informationen"""
        result = {'has_deadline': False, 'hours_until': None, 'deadline_text': None}
        
        text_lower = text.lower()
        
        # Relative Zeitangaben
        relative_times = {
            'heute': 0,
            'morgen': 24,
            'übermorgen': 48,
            'bis heute': 0,
            'bis morgen': 24,
        }
        
        for phrase, hours in relative_times.items():
            if phrase in text_lower:
                result['has_deadline'] = True
                result['hours_until'] = hours
                result['deadline_text'] = phrase
                return result
        
        # spaCy DATE Entities
        for ent in doc.ents:
            if ent.label_ == "DATE":
                result['has_deadline'] = True
                result['deadline_text'] = ent.text
                break
        
        # Dringlichkeits-Keywords (erweitert)
        urgent_keywords = [
            'dringend', 'asap', 'urgent', 'sofort', 'umgehend',
            'schnell', 'baldmöglichst', 'zeitnah', 'eilig',
            'bis spätestens', 'bis zum', 'deadline', 'termin',
            'frist', 'rechtzeitig', 'pünktlich'
        ]
        if any(kw in text_lower for kw in urgent_keywords):
            result['has_deadline'] = True
            result['hours_until'] = 24
        
        return result
    
    def _analyze_money(self, doc, text: str) -> Dict:
        """Extrahiert Geldbeträge mit Timeout-Schutz"""
        result = {'amount': None, 'currency': None}
        
        try:
            for ent in doc.ents:
                if ent.label_ == "MONEY":
                    amount = self._parse_money_string(ent.text)
                    if amount:
                        result['amount'] = amount
                        result['currency'] = 'EUR' if '€' in ent.text or 'eur' in ent.text.lower() else 'USD'
                        return result
        except Exception as e:
            logger.debug(f"spaCy MONEY entity parsing failed: {e}")
        
        money_patterns = [
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€',
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*EUR',
        ]
        
        for pattern in money_patterns:
            match = safe_regex_search(pattern, text)
            if match:
                amount = self._parse_money_string(match.group(1))
                if amount:
                    result['amount'] = amount
                    result['currency'] = 'EUR'
                    return result
        
        return result
    
    def _parse_money_string(self, amount_str: str) -> Optional[float]:
        """
        Parst Geldbeträge mit korrekter DE/US Format-Erkennung.
        
        DE: 1.234,56 → 1234.56
        US: 1,234.56 → 1234.56
        
        Heuristik: Last separator determines decimal point
        """
        try:
            amount_str = re.sub(r'[€$£¥]', '', amount_str).strip()
            
            if not amount_str:
                return None
            
            if ',' in amount_str and '.' in amount_str:
                last_comma_pos = amount_str.rfind(',')
                last_dot_pos = amount_str.rfind('.')
                
                if last_comma_pos > last_dot_pos:
                    amount_str = amount_str.replace('.', '').replace(',', '.')
                else:
                    amount_str = amount_str.replace(',', '')
            elif ',' in amount_str:
                parts = amount_str.split(',')
                if len(parts[-1]) == 2:
                    amount_str = amount_str.replace(',', '.')
                else:
                    amount_str = amount_str.replace(',', '')
            
            return float(amount_str)
        except (ValueError, AttributeError):
            return None
    
    def _extract_action_verbs(self, doc, text: str) -> List[str]:
        """Extrahiert Action-Verben (optimiert mit Set)"""
        found = []
        text_lower = text.lower()
        
        for keyword in ACTION_VERBS_SET:
            if keyword in text_lower:
                found.append(keyword)
        
        return found[:5]
    
    def _has_authority_person(self, doc, text: str, sender: str) -> bool:
        """Prüft auf Autoritäts-Personen (optimiert mit Set)"""
        text_lower = text.lower()
        return any(title in text_lower for title in AUTHORITY_TITLES_SET)
    
    def _is_invoice(self, text: str) -> bool:
        """Prüft ob Email eine Rechnung ist (optimiert mit Set)"""
        text_lower = text.lower()
        matches = sum(1 for kw in INVOICE_KEYWORDS_SET if kw in text_lower)
        return matches >= 2
    
    def _calculate_confidence(self, signals: Dict, urgency_score: float) -> float:
        """
        Berechnet Confidence-Score mit gewichteten Signalen.
        
        Nutzt gewichtete Durchschnitte statt additiver Bonuses,
        um unrealistisch hohe Scores zu vermeiden.
        
        Wichtig: Für Trusted Senders gibt es eine Mindest-Confidence von 0.6,
        auch wenn keine starken Dringlichkeits-Signale erkannt wurden.
        """
        signal_weights = {}
        total_weight = 0.0
        
        if signals['time_pressure'] and signals['deadline_hours']:
            if signals['deadline_hours'] < 24:
                signal_weights['deadline_critical'] = 0.40
                total_weight += 0.40
            elif signals['deadline_hours'] < 48:
                signal_weights['deadline_medium'] = 0.25
                total_weight += 0.25
            else:
                signal_weights['deadline_loose'] = 0.10
                total_weight += 0.10
        
        if signals['money_amount'] is not None:
            if signals['money_amount'] > 5000:
                signal_weights['money_high'] = 0.25
                total_weight += 0.25
            else:
                signal_weights['money_low'] = 0.15
                total_weight += 0.15
        
        if signals['invoice_detected']:
            signal_weights['invoice'] = 0.35
            total_weight += 0.35
        
        if signals['authority_person']:
            signal_weights['authority'] = 0.20
            total_weight += 0.20
        
        if len(signals['action_verbs']) > 0:
            signal_weights['action_verbs'] = min(0.10 * len(signals['action_verbs']), 0.20)
            total_weight += signal_weights['action_verbs']
        
        # Berechne base_confidence aus erkannten Signalen
        base_confidence = 0.0
        if total_weight > 0:
            base_confidence = sum(signal_weights.values()) / total_weight
        
        # Kombiniere base_confidence mit urgency_score
        if urgency_score >= 0.7:
            confidence = base_confidence * 0.7 + urgency_score * 0.3
        elif urgency_score >= 0.5:
            confidence = base_confidence * 0.6 + urgency_score * 0.4
        else:
            confidence = base_confidence * 0.5 + urgency_score * 0.5
        
        # WICHTIG: Mindest-Confidence von 0.6 für Trusted Senders
        # Auch wenn keine starken Signale erkannt wurden, vertrauen wir
        # der spaCy-Analyse für Whitelist-Absender
        if confidence < 0.6:
            confidence = 0.6
        
        return min(confidence, 1.0)
    
    def _fallback_heuristics(self, subject: str, body: str) -> Dict:
        """Fallback wenn spaCy nicht verfügbar"""
        text = f"{subject} {body[:500]}".lower()
        
        urgency_score = 0.0
        
        urgent_keywords = ['dringend', 'urgent', 'asap', 'sofort']
        action_keywords = ['bitte', 'senden', 'antworten']
        money_keywords = ['rechnung', 'invoice', '€', '$']
        
        if any(kw in text for kw in urgent_keywords):
            urgency_score += 0.4
        if any(kw in text for kw in action_keywords):
            urgency_score += 0.3
        if any(kw in text for kw in money_keywords):
            urgency_score += 0.3
        
        return {
            'urgency_score': min(urgency_score, 1.0),
            'importance_score': 0.5,
            'category': 'aktion_erforderlich' if urgency_score > 0.5 else 'nur_information',
            'confidence': 0.4,
            'signals': {},
            'method': 'fallback_heuristics'
        }


# Singleton
_urgency_booster_instance = None
_hybrid_pipeline_instance = None

def get_urgency_booster(language: str = "de") -> UrgencyBooster:
    """
    Factory: Gibt Singleton-Instanz zurück.
    
    DEPRECATED: Wird durch get_hybrid_pipeline() ersetzt (Phase Y).
    Behalten für Rückwärtskompatibilität.
    """
    global _urgency_booster_instance
    if _urgency_booster_instance is None:
        _urgency_booster_instance = UrgencyBooster(language=language)
    return _urgency_booster_instance


def get_hybrid_pipeline(db_session, sgd_classifier=None):
    """
    Factory: Gibt Phase Y Hybrid Pipeline zurück (Singleton).
    
    Phase Y: spaCy NLP + Keywords + SGD Ensemble Learning
    
    Args:
        db_session: SQLAlchemy Session für Config-Zugriff
        sgd_classifier: Optional OnlineLearner für SGD Predictions
        
    Returns:
        HybridPipeline Instanz
    """
    global _hybrid_pipeline_instance
    
    # Neues Pipeline-Objekt pro Session (wegen DB-Binding)
    try:
        from src.services.hybrid_pipeline import HybridPipeline
        return HybridPipeline(db_session, sgd_classifier)
    except ImportError as e:
        logger.warning(f"⚠️ Phase Y Hybrid Pipeline nicht verfügbar: {e}")
        logger.warning(f"   Fallback auf alten UrgencyBooster")
        return None
