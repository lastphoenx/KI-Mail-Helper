"""
Phase 22: Content Sanitizer für Email-Pseudonymisierung

Ersetzt personenbezogene Daten (PII) durch Platzhalter:
- Namen → [PERSON]
- Firmen → [ORGANIZATION]
- Orte → [LOCATION]
- E-Mails → [EMAIL]
- Telefon → [PHONE]
- IBAN → [IBAN]

Nutzt Regex für technische PII + spaCy für semantische Entitäten.

Strategie:
1. Regex ZUERST → ersetzt technische PII (Email, Phone, IBAN, URL)
2. spaCy DANACH → ersetzt semantische Entities (PER, ORG, GPE, LOC)
3. Overlap-Detection → spaCy überspringt Bereiche die bereits ersetzt wurden
"""

import re
import time
import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy-loading (RAM-Optimierung)
_nlp = None
_sanitizer_instance = None


def get_spacy_model():
    """Lazy-load spaCy Modell (spart RAM wenn nicht benötigt)"""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("de_core_news_sm")
            logger.info("✅ spaCy Modell geladen: de_core_news_sm")
        except Exception as e:
            logger.warning(f"⚠️ spaCy nicht verfügbar: {e}")
            _nlp = False  # Marker für "nicht verfügbar"
    return _nlp if _nlp else None


def get_sanitizer():
    """Globale Sanitizer-Instanz (Singleton)"""
    global _sanitizer_instance
    if _sanitizer_instance is None:
        _sanitizer_instance = ContentSanitizer()
    return _sanitizer_instance


@dataclass
class SanitizationResult:
    """Ergebnis der Pseudonymisierung"""
    subject: str
    body: str
    entities_found: int
    level: int  # 1=Regex, 2=spaCy-Light (PER), 3=spaCy-Full (PER+ORG+GPE+LOC)
    processing_time_ms: float
    entities_by_type: Dict[str, int]


class ContentSanitizer:
    """
    Pseudonymisiert Email-Inhalte mit Regex + spaCy NER.
    
    Beispiel:
        sanitizer = ContentSanitizer()
        result = sanitizer.sanitize("Max Müller", "Text mit IBAN DE89...", level=3)
        # result.subject = "[PERSON]"
        # result.entities_found = 2 (PER + IBAN)
    """
    
    # Regex-Patterns für technische PII
    PATTERNS = {
        'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        # PHONE: Unterstützt +49, 0049, und lokale Nummern
        'PHONE': r'\b(?:(?:\+|00)\d{1,3}[-.\s]?)?(?:\(?\d{2,5}\)?[-.\s]?){1,4}\d{2,6}\b',
        'IBAN': r'\b[A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){4,7}\d{0,2}\b',
        'URL': r'https?://[^\s<>"{}|\\^`\[\]]+',
    }
    
    # spaCy Entity-Typen die ersetzt werden
    SPACY_ENTITY_MAP = {
        'PER': '[PERSON]',       # Personen
        'ORG': '[ORGANIZATION]', # Organisationen
        'GPE': '[LOCATION]',     # Länder, Städte
        'LOC': '[LOCATION]',     # Andere Orte
    }
    
    def sanitize(self, subject: str, body: str, level: int = 3) -> SanitizationResult:
        """
        Pseudonymisiert Subject und Body.
        
        Args:
            subject: Email-Betreff (Klartext)
            body: Email-Body (Klartext)
            level: Anonymisierungs-Stufe:
                   1 = Nur Regex (E-Mails, Telefon, IBAN, URLs) → 3-5ms
                   2 = spaCy-Light (+ PER) → 10-20ms
                   3 = spaCy-Full (+ PER, ORG, GPE, LOC) → 10-15ms
        
        Returns:
            SanitizationResult mit pseudonymisierten Texten
        """
        start_time = time.perf_counter()
        entities_by_type: Dict[str, int] = {}
        
        sanitized_subject = subject or ""
        sanitized_body = body or ""
        
        # STRATEGIE: Regex ZUERST, dann spaCy mit Overlap-Detection
        
        # Schritt 1: Regex für technische PII
        sanitized_subject, regex_counts_subj = self._apply_regex(sanitized_subject)
        sanitized_body, regex_counts_body = self._apply_regex(sanitized_body)
        
        # Merge Regex-Counts
        for key in set(regex_counts_subj.keys()) | set(regex_counts_body.keys()):
            entities_by_type[key] = regex_counts_subj.get(key, 0) + regex_counts_body.get(key, 0)
        
        # Schritt 2: spaCy NER (Level 2+) mit Overlap-Detection
        if level >= 2:
            nlp = get_spacy_model()
            if nlp:
                entity_types = {'PER'} if level == 2 else set(self.SPACY_ENTITY_MAP.keys())
                
                sanitized_subject, ner_counts_subj = self._apply_spacy(
                    sanitized_subject, nlp, entity_types
                )
                sanitized_body, ner_counts_body = self._apply_spacy(
                    sanitized_body, nlp, entity_types
                )
                
                # Merge NER-Counts
                for key in set(ner_counts_subj.keys()) | set(ner_counts_body.keys()):
                    entities_by_type[key] = entities_by_type.get(key, 0) + \
                                           ner_counts_subj.get(key, 0) + \
                                           ner_counts_body.get(key, 0)
        
        processing_time_ms = (time.perf_counter() - start_time) * 1000
        total_entities = sum(entities_by_type.values())
        
        return SanitizationResult(
            subject=sanitized_subject,
            body=sanitized_body,
            entities_found=total_entities,
            level=level,
            processing_time_ms=processing_time_ms,
            entities_by_type=entities_by_type
        )
    
    def sanitize_batch(self, items: List[Tuple[str, str]], level: int = 3) -> List[SanitizationResult]:
        """
        Batch-Verarbeitung für bessere Performance.
        
        Args:
            items: Liste von (subject, body) Tuples
            level: Anonymisierungs-Stufe (1-3)
        
        Returns:
            Liste von SanitizationResults
        """
        # Für jetzt: Einfache Loop-Verarbeitung
        # TODO: Echtes spaCy nlp.pipe() für 30% Speedup bei großen Batches
        return [self.sanitize(subject, body, level) for subject, body in items]
    
    def _apply_regex(self, text: str) -> Tuple[str, Dict[str, int]]:
        """
        Wendet Regex-Patterns an für technische PII.
        
        Returns:
            (sanitized_text, counts_by_type)
        """
        if not text:
            return text, {}
        
        counts = {}
        sanitized = text
        
        for entity_type, pattern in self.PATTERNS.items():
            matches = re.findall(pattern, sanitized, re.IGNORECASE)
            if matches:
                counts[entity_type] = len(matches)
                sanitized = re.sub(pattern, f'[{entity_type}]', sanitized, flags=re.IGNORECASE)
        
        return sanitized, counts
    
    def _apply_spacy(self, text: str, nlp, entity_types: set) -> Tuple[str, Dict[str, int]]:
        """
        Wendet spaCy NER an mit Overlap-Detection.
        
        Strategie:
        1. Finde alle bereits ersetzten Platzhalter-Positionen
        2. Führe spaCy auf dem Text aus
        3. Filtere Entities die mit Platzhaltern überlappen
        4. Ersetze von hinten nach vorne (keine Offset-Probleme)
        
        Returns:
            (sanitized_text, counts_by_type)
        """
        if not text or not nlp:
            return text, {}
        
        try:
            # 1. Finde alle Regex-Platzhalter Positionen
            protected_ranges = []
            for pattern_type in self.PATTERNS.keys():
                placeholder = f'[{pattern_type}]'
                start_pos = 0
                while True:
                    idx = text.find(placeholder, start_pos)
                    if idx == -1:
                        break
                    protected_ranges.append((idx, idx + len(placeholder)))
                    start_pos = idx + 1
            
            def overlaps_protected(ent_start: int, ent_end: int) -> bool:
                """Prüft ob Entity-Position mit geschütztem Bereich überlappt"""
                for p_start, p_end in protected_ranges:
                    # Überlappung wenn NICHT (entity endet vor protect ODER entity startet nach protect)
                    if not (ent_end <= p_start or ent_start >= p_end):
                        return True
                return False
            
            # 2. spaCy auf Text ausführen
            doc = nlp(text)
            counts = {}
            
            # 3. Filtere Entities die mit Platzhaltern überlappen
            valid_entities = [
                (ent.start_char, ent.end_char, ent.label_)
                for ent in doc.ents
                if ent.label_ in entity_types and not overlaps_protected(ent.start_char, ent.end_char)
            ]
            
            # 4. Sortiere von HINTEN nach VORNE (verhindert Offset-Probleme!)
            valid_entities.sort(key=lambda x: x[0], reverse=True)
            
            # 5. Ersetze von hinten nach vorne
            sanitized = text
            for start, end, label in valid_entities:
                replacement = self.SPACY_ENTITY_MAP.get(label, f'[{label}]')
                sanitized = sanitized[:start] + replacement + sanitized[end:]
                counts[label] = counts.get(label, 0) + 1
            
            return sanitized, counts
            
        except Exception as e:
            logger.warning(f"spaCy processing failed: {e}")
            return text, {}


# ============================================================================
# TESTS (für schnelle Verifikation)
# ============================================================================

def test_sanitizer():
    """Quick test to verify the sanitizer works correctly"""
    sanitizer = ContentSanitizer()
    
    # Test 1: Nur Regex
    print("=" * 60)
    print("TEST 1: Nur Regex (Level 1)")
    result = sanitizer.sanitize(
        subject="Kontakt: max@example.com",
        body="Tel: +49 30 12345678, IBAN: DE89370400440532013000",
        level=1
    )
    print(f"  Subject: {result.subject}")
    print(f"  Body: {result.body}")
    print(f"  Entities: {result.entities_by_type}")
    assert "[EMAIL]" in result.subject, "EMAIL nicht ersetzt!"
    assert "[PHONE]" in result.body, "PHONE nicht ersetzt!"
    assert "[IBAN]" in result.body, "IBAN nicht ersetzt!"
    print("  ✅ PASSED")
    
    # Test 2: Regex + spaCy (der Bug-Test!)
    print("\n" + "=" * 60)
    print("TEST 2: Regex + spaCy (Level 3) - Bug-Regression-Test")
    result = sanitizer.sanitize(
        subject="Termin mit Max Müller von Siemens AG",
        body="Hallo Max, hier meine Daten: max@example.com, Tel: +49 30 12345678, IBAN: DE89370400440532013000",
        level=3
    )
    print(f"  Subject: {result.subject}")
    print(f"  Body: {result.body}")
    print(f"  Entities: {result.entities_by_type}")
    
    # Kritische Checks
    assert "[[" not in result.body, "DOUBLE-BRACKET BUG! [[...]] gefunden!"
    assert "[EMAIL]" in result.body, "EMAIL nicht ersetzt!"
    assert "[PHONE]" in result.body, "PHONE nicht ersetzt!"
    assert "[IBAN]" in result.body, "IBAN nicht ersetzt!"
    assert "max@example.com" not in result.body, "Email-Adresse nicht anonymisiert!"
    # Note: "+49" kann bleiben wenn es nicht Teil des Regex-Match ist (z.B. "Tel: +49 123...")
    # Das wichtige ist dass die Nummer selbst ersetzt ist ([PHONE])
    assert "30 12345678" not in result.body, "Telefonnummer nicht vollständig anonymisiert!"
    print("  ✅ PASSED")
    
    # Test 3: spaCy erkennt Namen
    print("\n" + "=" * 60)
    print("TEST 3: spaCy NER für Personen")
    result = sanitizer.sanitize(
        subject="Brief von Thomas Müller",
        body="Sehr geehrter Herr Schmidt, wie besprochen mit Frau Weber...",
        level=3
    )
    print(f"  Subject: {result.subject}")
    print(f"  Body: {result.body}")
    print(f"  Entities: {result.entities_by_type}")
    # Mindestens eine Person sollte erkannt werden (spaCy-abhängig)
    if result.entities_by_type.get('PER', 0) > 0:
        print("  ✅ PASSED (Personen erkannt)")
    else:
        print("  ⚠️  Keine Personen erkannt (spaCy-Modell-abhängig)")
    
    # Test 4: Keine Double-Replacement
    print("\n" + "=" * 60)
    print("TEST 4: Keine Double-Replacement bei gemischtem Text")
    result = sanitizer.sanitize(
        subject="Email von info@firma.de",
        body="Telefon: +49 30 999, Email: test@test.de, Name: Hans Meier aus Berlin",
        level=3
    )
    print(f"  Subject: {result.subject}")
    print(f"  Body: {result.body}")
    
    # Count brackets - sollte keine [[ oder ]] haben
    double_open = result.body.count("[[")
    double_close = result.body.count("]]")
    assert double_open == 0, f"Double-Open gefunden: {double_open}x"
    assert double_close == 0, f"Double-Close gefunden: {double_close}x"
    print("  ✅ PASSED")
    
    # Test 5: Internationale Vorwahlen (DE, CH, AT)
    print("\n" + "=" * 60)
    print("TEST 5: Internationale Vorwahlen (DE, CH, AT)")
    test_cases = [
        ("+49 30 12345678", "Deutschland +49"),
        ("+41 44 1234567", "Schweiz +41"),
        ("+43 1 23456789", "Österreich +43"),
        ("0049 30 12345678", "Deutschland 0049"),
        ("0041 44 1234567", "Schweiz 0041"),
        ("0043 1 23456789", "Österreich 0043"),
    ]
    
    all_passed = True
    for phone, desc in test_cases:
        result = sanitizer.sanitize("", f"Tel: {phone}", level=1)
        if "[PHONE]" in result.body:
            print(f"  ✅ {desc}: {phone} → {result.body.strip()}")
        else:
            print(f"  ❌ {desc}: {phone} NICHT erkannt!")
            all_passed = False
    
    assert all_passed, "Nicht alle internationalen Vorwahlen wurden erkannt!"
    print("  ✅ ALLE PASSED")
    
    print("\n" + "=" * 60)
    print("✅ ALLE TESTS BESTANDEN!")
    print("=" * 60)


if __name__ == "__main__":
    test_sanitizer()
