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
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy Loading: spaCy wird erst bei Bedarf geladen
_spacy_de = None


def _load_spacy_de():
    """Lädt deutsches spaCy Model (lazy)"""
    global _spacy_de
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
        
        # Dringlichkeits-Keywords
        urgent_keywords = ['dringend', 'asap', 'urgent', 'sofort', 'umgehend']
        if any(kw in text_lower for kw in urgent_keywords):
            result['has_deadline'] = True
            result['hours_until'] = 24
        
        return result
    
    def _analyze_money(self, doc, text: str) -> Dict:
        """Extrahiert Geldbeträge"""
        result = {'amount': None, 'currency': None}
        
        # spaCy MONEY Entities
        for ent in doc.ents:
            if ent.label_ == "MONEY":
                amount = self._parse_money_string(ent.text)
                if amount:
                    result['amount'] = amount
                    result['currency'] = 'EUR' if '€' in ent.text or 'eur' in ent.text.lower() else 'USD'
                    return result
        
        # Regex Fallback
        money_patterns = [
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€',
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*EUR',
        ]
        
        for pattern in money_patterns:
            match = re.search(pattern, text)
            if match:
                amount = self._parse_money_string(match.group(1))
                if amount:
                    result['amount'] = amount
                    result['currency'] = 'EUR'
                    return result
        
        return result
    
    def _parse_money_string(self, amount_str: str) -> Optional[float]:
        """Parst Geldbeträge: "1.500,00" → 1500.0"""
        try:
            amount_str = re.sub(r'[€$£¥]', '', amount_str).strip()
            
            if ',' in amount_str and '.' in amount_str:
                if amount_str.rindex(',') > amount_str.rindex('.'):
                    amount_str = amount_str.replace('.', '').replace(',', '.')
                else:
                    amount_str = amount_str.replace(',', '')
            elif ',' in amount_str:
                if len(amount_str.split(',')[-1]) >= 3:
                    amount_str = amount_str.replace(',', '')
                else:
                    amount_str = amount_str.replace(',', '.')
            
            return float(amount_str)
        except ValueError:
            return None
    
    def _extract_action_verbs(self, doc, text: str) -> List[str]:
        """Extrahiert Action-Verben"""
        action_keywords = [
            'senden', 'schicken', 'überweisen', 'bezahlen',
            'bestätigen', 'antworten', 'rückmelden',
            'prüfen', 'genehmigen', 'unterschreiben'
        ]
        
        found = []
        text_lower = text.lower()
        
        for keyword in action_keywords:
            if keyword in text_lower and keyword not in found:
                found.append(keyword)
        
        return found[:5]
    
    def _has_authority_person(self, doc, text: str, sender: str) -> bool:
        """Prüft auf Autoritäts-Personen"""
        text_lower = text.lower()
        
        authority_titles = [
            'ceo', 'geschäftsführer', 'direktor',
            'vorstand', 'präsident', 'chef'
        ]
        
        return any(title in text_lower for title in authority_titles)
    
    def _is_invoice(self, text: str) -> bool:
        """Prüft ob Email eine Rechnung ist"""
        text_lower = text.lower()
        
        invoice_keywords = [
            'rechnung', 'invoice', 'zahlungserinnerung',
            'rechnungsnummer', 'payment reminder'
        ]
        
        matches = sum(1 for kw in invoice_keywords if kw in text_lower)
        return matches >= 2
    
    def _calculate_confidence(self, signals: Dict, urgency_score: float) -> float:
        """Berechnet Confidence-Score"""
        confidence = 0.0
        
        signal_count = sum([
            signals['time_pressure'],
            signals['money_amount'] is not None,
            len(signals['action_verbs']) > 0,
            signals['authority_person'],
            signals['invoice_detected']
        ])
        
        confidence += signal_count * 0.15
        
        if urgency_score >= 0.7:
            confidence += 0.3
        elif urgency_score >= 0.5:
            confidence += 0.2
        
        if signals['invoice_detected']:
            confidence += 0.2
        
        if signals['time_pressure'] and signals['deadline_hours'] and signals['deadline_hours'] < 24:
            confidence += 0.25
        
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

def get_urgency_booster(language: str = "de") -> UrgencyBooster:
    """Factory: Gibt Singleton-Instanz zurück"""
    global _urgency_booster_instance
    if _urgency_booster_instance is None:
        _urgency_booster_instance = UrgencyBooster(language=language)
    return _urgency_booster_instance
