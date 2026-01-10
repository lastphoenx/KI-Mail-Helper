"""
Content Sanitizer V5.2 - Email-Pseudonymisierung mit bidirektionalem Mapping

FIXES in V5.2:
- V4.0: Telefonnummern, erweiterte Blacklist, konsistente Nummern
- V4.1: Blacklist prüft erstes/letztes Wort, Zeilenumbruch-Filter
- V4.2: Smart Extraction - "Lieber Max" → "Lieber [PERSON_X]"
- V4.3: Leerzeichen nach Platzhalter wenn nächstes Zeichen Buchstabe
- V5.0: HTML→Plain Text Konvertierung via BeautifulSoup
- V5.1: inscriptis getestet - VERWORFEN (keine Zeilenumbrüche)
- V5.2: BeautifulSoup optimiert + Signatur-Zeilen zusammenführen
"""

import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import OrderedDict

logger = logging.getLogger(__name__)

# Debug Logger Import
try:
    from src.debug_logger import DebugLogger
    DEBUG_LOGGER_AVAILABLE = True
except ImportError:
    DEBUG_LOGGER_AVAILABLE = False

_nlp = None
_sanitizer_instance = None


def get_spacy_model():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            # Versuche zuerst das bessere md-Modell
            try:
                _nlp = spacy.load("de_core_news_md")
                logger.info("✅ spaCy geladen: de_core_news_md")
            except OSError:
                _nlp = spacy.load("de_core_news_sm")
                logger.info("✅ spaCy geladen: de_core_news_sm (Fallback)")
        except Exception as e:
            logger.warning(f"⚠️ spaCy nicht verfügbar: {e}")
            _nlp = False
    return _nlp if _nlp else None


def get_sanitizer():
    global _sanitizer_instance
    if _sanitizer_instance is None:
        _sanitizer_instance = ContentSanitizer()
    return _sanitizer_instance


@dataclass
class EntityMap:
    forward: Dict[str, str] = field(default_factory=OrderedDict)
    reverse: Dict[str, str] = field(default_factory=OrderedDict)
    counters: Dict[str, int] = field(default_factory=dict)
    # Normalisierungs-Map für konsistente Platzhalter
    _normalized: Dict[str, str] = field(default_factory=dict)
    
    def _normalize_key(self, key: str) -> str:
        """Normalisiert einen Key für konsistente Zuordnung."""
        return key.strip().lower()
    
    def add(self, original: str, entity_type: str) -> str:
        key = original.strip()
        if not key:
            return original
        
        # Prüfe ob normalisierte Version schon existiert
        norm_key = self._normalize_key(key)
        if norm_key in self._normalized:
            return self._normalized[norm_key]
        
        # Prüfe exakte Übereinstimmung
        if key in self.forward:
            return self.forward[key]
        
        # Neuen Platzhalter erstellen
        if entity_type not in self.counters:
            self.counters[entity_type] = 0
        self.counters[entity_type] += 1
        placeholder = f"[{entity_type}_{self.counters[entity_type]}]"
        
        self.forward[key] = placeholder
        self.reverse[placeholder] = original
        self._normalized[norm_key] = placeholder
        
        return placeholder
    
    def get_placeholder(self, original: str) -> Optional[str]:
        key = original.strip()
        # Erst exakt, dann normalisiert
        if key in self.forward:
            return self.forward[key]
        norm_key = self._normalize_key(key)
        return self._normalized.get(norm_key)
    
    def deanonymize(self, text: str) -> str:
        result = text
        for ph in sorted(self.reverse.keys(), key=len, reverse=True):
            result = result.replace(ph, self.reverse[ph])
        return result
    
    def to_dict(self) -> dict:
        return {"forward": dict(self.forward), "reverse": dict(self.reverse), "counters": self.counters}
    
    @classmethod
    def from_dict(cls, data: dict) -> "EntityMap":
        em = cls()
        em.forward = OrderedDict(data.get("forward", {}))
        em.reverse = OrderedDict(data.get("reverse", {}))
        em.counters = data.get("counters", {})
        # Rebuild normalized map
        for key, placeholder in em.forward.items():
            em._normalized[em._normalize_key(key)] = placeholder
        return em
    
    def __len__(self):
        return len(self.forward)


@dataclass
class SanitizationResult:
    subject: str
    body: str
    entity_map: EntityMap
    entities_found: int
    level: int
    processing_time_ms: float
    entities_by_type: Dict[str, int]
    
    def deanonymize_text(self, text: str) -> str:
        return self.entity_map.deanonymize(text)
    
    def get_entity_map_dict(self) -> dict:
        return self.entity_map.to_dict()


class ContentSanitizer:
    
    # Erweiterte Blacklist für deutsche Wörter die spaCy falsch als PER erkennt
    SPACY_BLACKLIST = {
        # Pronomen
        'du', 'Du', 'DU', 'sie', 'Sie', 'SIE', 'er', 'Er', 'ER',
        'ihr', 'Ihr', 'IHR', 'wir', 'Wir', 'WIR', 'ich', 'Ich', 'ICH',
        'dir', 'Dir', 'dich', 'Dich', 'ihm', 'Ihm', 'ihn', 'Ihn',
        'uns', 'Uns', 'ihnen', 'Ihnen', 'mich', 'Mich', 'mir', 'Mir',
        'dein', 'Dein', 'deine', 'Deine', 'deiner', 'Deiner',
        'sein', 'Sein', 'seine', 'Seine',
        'mein', 'Mein', 'meine', 'Meine',
        
        # Grußformeln - KOMPLETT
        'Lieber', 'Liebe', 'Lieben', 'Liebes',
        'Herzliche', 'Herzlicher', 'Herzlichen', 'Herzlich',
        'Beste', 'Bester', 'Besten', 'Beste',
        'Viele', 'Vielen',
        'Freundliche', 'Freundlicher', 'Freundlichen',
        'Guten', 'Guter', 'Gute',
        'Hallo', 'Hi', 'Hey',
        
        # Grußformeln am Ende
        'Gruss', 'Grüsse', 'Gruß', 'Grüße',
        'Grüssen', 'Grüßen',
        
        # Email-Header Wörter
        'Gesendet', 'Von', 'An', 'Betreff', 'Cc', 'Bcc',
        'Datum', 'Subject', 'From', 'To', 'Date',
        
        # Verben am Satzanfang die spaCy falsch erkennt
        'Passt', 'Danke', 'Bitte', 'Siehe', 'Anhang',
        'Vielen', 'Dank',
        
        # Modalverben + Du Kombinationen
        'müsstest', 'müsste', 'könnte', 'sollte', 'würde',
        'könntest', 'solltest', 'würdest', 'dürftest',
        'musst', 'kannst', 'sollst', 'wirst', 'darfst',
        
        # Abkürzungen
        'Person', 'm.E.', 'm.E', 'etc', 'bzw', 'ggf', 'ca',
        'LK', 'HR', 'CC', 'SAP',
        
        # Häufige Substantive die keine Namen sind
        'Stellenbeschreibungen', 'Stellenbeschreibung',
        'Stellenbeschbreibungen',  # Tippfehler!
        'Entwürfe', 'Entwurf',
        'Rückmeldung', 'Ergänzungen', 'Anpassungen',
        'Führungsspanne', 'Stellvertretung',
        'Projects', 'Leitung',
    }
    
    SPACY_ENTITY_MAP = {'PER': 'PERSON', 'ORG': 'ORG', 'GPE': 'LOCATION', 'LOC': 'LOCATION'}
    
    def _is_html(self, text: str) -> bool:
        """Prüft ob Text HTML enthält."""
        if not text:
            return False
        # Schneller Check auf typische HTML-Marker
        html_markers = ['<html', '<body', '<div', '<p ', '<p>', '<span', '<table', '<!DOCTYPE']
        text_lower = text[:1000].lower()  # Nur ersten 1000 Zeichen prüfen
        return any(marker in text_lower for marker in html_markers)
    
    def _html_to_plain_text(self, html: str) -> tuple[str, str]:
        """Konvertiert HTML zu sauberem Plain Text via inscriptis (optimiert für Emails).
        
        Returns:
            tuple: (tool_name, plain_text)
        """
        if not html:
            return ("none", "")
        
        # Methode 1: inscriptis (beste Qualität für Emails)
        try:
            from inscriptis import get_text
            from inscriptis.model.config import ParserConfig
            
            # Konfiguration für Email-optimierte Ausgabe
            config = ParserConfig(
                display_links=True,      # Links anzeigen
                display_anchors=False,   # Keine Anker
                annotation_rules=None
            )
            
            text = get_text(html, config)
            
            # Bereinige Whitespace
            import html as html_module
            text = html_module.unescape(text)
            
            # Entferne übermäßige Leerzeilen (max 2)
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
            text = text.strip()
            
            # Bereinige Markdown-Link-Artefakte von inscriptis
            text = re.sub(r'\[\s*([^\]]+)\s*\]\([^)]+\)', r'\1', text)  # [text](url) → text
            text = re.sub(r'\s+\|\s+', ' | ', text)  # Normalisiere | Trennzeichen
            
            logger.info(f"✅ HTML→Plain Text (inscriptis): {len(html)} chars → {len(text)} chars")
            return ("inscriptis", text)
            
        except ImportError:
            logger.warning("⚠️ inscriptis nicht verfügbar, versuche html2text...")
        except Exception as e:
            logger.warning(f"⚠️ inscriptis fehlgeschlagen: {e}, versuche html2text...")
        
        # Methode 2: html2text (Fallback)
        try:
            import html2text
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.ignore_emphasis = True
            h.body_width = 0  # Keine Zeilenumbrüche erzwingen
            h.unicode_snob = True
            h.skip_internal_links = True
            
            text = h.handle(html)
            
            # Bereinige Markdown-Artefakte
            text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** → bold
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [text](url) → text
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
            text = text.strip()
            
            logger.info(f"✅ HTML→Plain Text (html2text): {len(html)} chars → {len(text)} chars")
            return ("html2text", text)
            
        except ImportError:
            logger.warning("⚠️ html2text nicht verfügbar, versuche BeautifulSoup...")
        except Exception as e:
            logger.warning(f"⚠️ html2text fehlgeschlagen: {e}, versuche BeautifulSoup...")
        
        # Methode 3: BeautifulSoup (Fallback)
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Entferne Script und Style Tags
            for tag in soup.find_all(['script', 'style', 'head', 'meta', 'link']):
                tag.decompose()
            
            # Ersetze <br> mit Zeilenumbrüchen
            for br in soup.find_all('br'):
                br.replace_with('\n')
            
            # Füge Zeilenumbrüche nach Block-Elementen ein
            for tag in soup.find_all(['p', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                tag.append('\n')
            
            text = soup.get_text()
            
            import html as html_module
            text = html_module.unescape(text)
            text = re.sub(r'[^\S\n]+', ' ', text)
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
            lines = [line.strip() for line in text.split('\n')]
            text = '\n'.join(lines)
            text = text.strip()
            
            logger.info(f"✅ HTML→Plain Text (BeautifulSoup): {len(html)} chars → {len(text)} chars")
            return ("BeautifulSoup", text)
            
        except ImportError:
            logger.warning("⚠️ BeautifulSoup nicht verfügbar, Fallback auf Regex")
        except Exception as e:
            logger.warning(f"⚠️ BeautifulSoup fehlgeschlagen: {e}, Fallback auf Regex")
        
        # Methode 4: Regex (letzter Fallback)
        text = self._clean_html_fallback(html)
        logger.info(f"✅ HTML→Plain Text (regex-fallback): {len(html)} chars → {len(text)} chars")
        return ("regex-fallback", text)
    
    def _clean_html_fallback(self, text: str) -> str:
        """Fallback: Bereinigt HTML-Tags und Entities via Regex (wenn BeautifulSoup nicht verfügbar)."""
        if not text:
            return text
        # HTML-Tags entfernen (mit Zeilenumbruch für Block-Tags)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        # HTML-Entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&#43;', '+', text)
        text = re.sub(r'&#8211;', '–', text)
        text = re.sub(r'&#8230;', '…', text)
        text = re.sub(r'&#\d+;', '', text)
        text = re.sub(r'&\w+;', '', text)
        # Outlook XML
        text = re.sub(r'<o:[^>]*>', '', text)
        text = re.sub(r'</o:[^>]*>', '', text)
        # Bereinige Whitespace
        text = re.sub(r'[^\S\n]+', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        return text.strip()
    
    def sanitize(self, subject: str, body: str, level: int = 3, existing_map: Optional[EntityMap] = None, session_id: Optional[str] = None) -> SanitizationResult:
        start_time = time.perf_counter()
        entity_map = existing_map if existing_map else EntityMap()
        entities_by_type: Dict[str, int] = {}
        
        # V5.0: Automatische HTML-Erkennung und Konvertierung
        if self._is_html(body):
            logger.info("🔍 HTML im Body erkannt, starte Konvertierung...")
            tool_name, body = self._html_to_plain_text(body)
        
        if self._is_html(subject):
            tool_name, subject = self._html_to_plain_text(subject)
        
        # 🔍 DEBUG: Log nach HTML-Cleanup, VOR Anonymisierung
        if DEBUG_LOGGER_AVAILABLE and DebugLogger.is_enabled() and session_id:
            DebugLogger.log_sanitizer_cleaned(
                subject=subject,
                body=body,
                session_id=session_id
            )
        
        # Regex anwenden
        subject, body, counts = self._apply_regex(subject or "", body or "", entity_map)
        entities_by_type.update(counts)
        
        # spaCy (Level 2+)
        if level >= 2:
            nlp = get_spacy_model()
            if nlp:
                types = {'PER'} if level == 2 else set(self.SPACY_ENTITY_MAP.keys())
                subject, c1 = self._apply_spacy(subject, nlp, types, entity_map)
                body, c2 = self._apply_spacy(body, nlp, types, entity_map)
                for k in set(c1.keys()) | set(c2.keys()):
                    entities_by_type[k] = entities_by_type.get(k, 0) + c1.get(k, 0) + c2.get(k, 0)
        
        return SanitizationResult(
            subject=subject, body=body, entity_map=entity_map,
            entities_found=len(entity_map), level=level,
            processing_time_ms=(time.perf_counter() - start_time) * 1000,
            entities_by_type=entities_by_type
        )
    
    def _apply_regex(self, subject: str, body: str, em: EntityMap) -> Tuple[str, str, Dict[str, int]]:
        counts: Dict[str, int] = {}
        
        # 1. Von:/An: mit Name <email>
        def replace_von_an(m):
            prefix, name, email = m.group(1), m.group(2), m.group(3)
            name_ph = em.add(name, "PERSON")
            email_ph = em.add(email, "EMAIL")
            counts["PERSON"] = counts.get("PERSON", 0) + 1
            counts["EMAIL"] = counts.get("EMAIL", 0) + 1
            return f"{prefix}: {name_ph} <{email_ph}>"
        
        p_von = r'(Von|An|Cc|Bcc):\s*([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)\s*<([^>]+@[^>]+)>'
        body = re.sub(p_von, replace_von_an, body)
        subject = re.sub(p_von, replace_von_an, subject)
        
        # 2. Signatur: Name | Titel (NICHT Org-Zeilen, NICHT Adress-Zeilen)
        org_words = ['universität', 'university', 'hochschule', 'institut', 'eth', 'firma', 'gmbh', 'ag', 'ltd']
        addr_words = ['strasse', 'straße', 'weg', 'platz', 'gasse', 'graben', 'postfach', 'basel', 'zürich', 'bern']
        
        lines = body.split('\n')
        new_lines = []
        for line in lines:
            ll = line.lower().strip()
            
            # Skip Org/Addr Zeilen
            if any(w in ll for w in org_words) or any(w in ll for w in addr_words):
                new_lines.append(line)
                continue
            
            # Name | Titel Pattern (mit optionalem Dr./Prof.)
            m = re.match(r'^((?:Dr\.\s+|Prof\.\s+)?[A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ][a-zäöüß]+)\s*\|(.+)$', line.strip())
            if m:
                name, rest = m.group(1).strip(), m.group(2).strip()
                name_ph = em.add(name, "PERSON")
                rest_ph = em.add(rest, "TITLE")
                counts["PERSON"] = counts.get("PERSON", 0) + 1
                counts["TITLE"] = counts.get("TITLE", 0) + 1
                new_lines.append(f"{name_ph} | {rest_ph}")
            else:
                new_lines.append(line)
        body = '\n'.join(new_lines)
        
        # 3. Org-Zeilen komplett
        lines = body.split('\n')
        new_lines = []
        for line in lines:
            if any(w in line.lower() for w in org_words) and '|' in line:
                ph = em.add(line.strip(), "ORG")
                counts["ORG"] = counts.get("ORG", 0) + 1
                new_lines.append(ph)
            else:
                new_lines.append(line)
        body = '\n'.join(new_lines)
        
        # 4. Adress-Zeilen komplett
        lines = body.split('\n')
        new_lines = []
        for line in lines:
            # Adresse mit PLZ oder Postfach
            if ('|' in line and 
                (re.search(r'\b\d{4,5}\b', line) or 'postfach' in line.lower()) and
                any(w in line.lower() for w in addr_words)):
                ph = em.add(line.strip(), "ADDRESS")
                counts["ADDRESS"] = counts.get("ADDRESS", 0) + 1
                new_lines.append(ph)
            else:
                new_lines.append(line)
        body = '\n'.join(new_lines)
        
        # 5. Telefon - VERBESSERT!
        # Verschiedene Formate: Tel +41 61..., Tel. +41 61..., +41 61...
        p_tel = r'(?:Tel\.?|Telefon|Phone|Fax|Mobile?|Mobil)?[:\s]*\+\d{1,3}[\s\-\.]?\d{1,4}[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,4}[\s\-\.]?\d{0,4}'
        
        for m in re.finditer(p_tel, body, re.IGNORECASE):
            matched = m.group().strip()
            if matched and len(matched) >= 10:  # Mindestlänge für Telefon
                if matched not in em.forward:
                    em.add(matched, "PHONE")
                    counts["PHONE"] = counts.get("PHONE", 0) + 1
        
        body = re.sub(p_tel, lambda m: em.get_placeholder(m.group().strip()) or m.group() if len(m.group().strip()) >= 10 else m.group(), body, flags=re.IGNORECASE)
        
        # 6. Email (einzeln)
        p_email = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
        for m in re.finditer(p_email, body):
            if m.group() not in em.forward:
                em.add(m.group(), "EMAIL")
                counts["EMAIL"] = counts.get("EMAIL", 0) + 1
        body = re.sub(p_email, lambda m: em.get_placeholder(m.group()) or m.group(), body)
        subject = re.sub(p_email, lambda m: em.get_placeholder(m.group()) or m.group(), subject)
        
        # 7. URL
        p_url = r'https?://[^\s<>"\']+'
        for m in re.finditer(p_url, body):
            if m.group() not in em.forward:
                em.add(m.group(), "URL")
                counts["URL"] = counts.get("URL", 0) + 1
        body = re.sub(p_url, lambda m: em.get_placeholder(m.group()) or m.group(), body)
        
        # 8. Namen nach Grußformeln (Begrüßung + Verabschiedung)
        # Begrüßungen: "Lieber Max", "Hallo Maria", "Sali Peter"
        gruss_prefixes = r'(?:Lieber|Liebe|Liebes|Hallo|Hi|Hey|Sali|Salü|Ciao|Servus|Moin|Guten\s+Tag|Guten\s+Morgen|Guten\s+Abend|Sehr\s+geehrte[r]?(?:\s+(?:Herr|Frau))?)'
        p_gruss_start = gruss_prefixes + r'\s+([A-ZÄÖÜ][a-zäöüß]+)'
        
        for m in re.finditer(p_gruss_start, body):
            name = m.group(1)
            if name not in self.SPACY_BLACKLIST and name not in em.forward:
                em.add(name, "PERSON")
                counts["PERSON"] = counts.get("PERSON", 0) + 1
        
        body = re.sub(p_gruss_start, lambda m: m.group(0).replace(m.group(1), em.get_placeholder(m.group(1)) or m.group(1)) if m.group(1) not in self.SPACY_BLACKLIST else m.group(0), body)
        
        # Verabschiedungen: "Grüsse\n  Max", "Gruss\n  Peter"
        gruss_suffixes = r'(?:Herzliche|Viele|Beste|Freundliche|Liebe|Mit\s+freundlichen|Mit\s+besten)?\s*(?:Grüsse|Grüße|Gruss|Gruß|Grüssen|Grüßen)\s*\n\s*'
        p_gruss_end = gruss_suffixes + r'([A-ZÄÖÜ][a-zäöüß]+)'
        
        for m in re.finditer(p_gruss_end, body):
            name = m.group(1)
            if name not in self.SPACY_BLACKLIST and name not in em.forward:
                em.add(name, "PERSON")
                counts["PERSON"] = counts.get("PERSON", 0) + 1
        
        body = re.sub(p_gruss_end, lambda m: m.group(0)[:-len(m.group(1))] + (em.get_placeholder(m.group(1)) or m.group(1)) if m.group(1) not in self.SPACY_BLACKLIST else m.group(0), body)
        
        return subject, body, counts
    
    def _apply_spacy(self, text: str, nlp, types: set, em: EntityMap) -> Tuple[str, Dict[str, int]]:
        if not text or not nlp:
            return text, {}
        
        try:
            # Geschützte Bereiche (bereits ersetzte Platzhalter)
            protected = []
            for ph in em.reverse.keys():
                i = 0
                while True:
                    idx = text.find(ph, i)
                    if idx == -1:
                        break
                    protected.append((idx, idx + len(ph)))
                    i = idx + 1
            
            def overlaps(s, e):
                return any(not (e <= ps or s >= pe) for ps, pe in protected)
            
            doc = nlp(text)
            counts = {}
            ents = []
            
            for e in doc.ents:
                ent_text = e.text.strip()
                
                # Blacklist prüfen - EXAKT
                if ent_text in self.SPACY_BLACKLIST:
                    continue
                
                # Zu kurz
                if len(ent_text) < 2:
                    continue
                
                # Nur erlaubte Typen
                if e.label_ not in types:
                    continue
                
                # Nicht in geschütztem Bereich
                if overlaps(e.start_char, e.end_char):
                    continue
                
                # Enthält Zeilenumbruch -> Parsing-Fehler, komplett skippen
                if '\n' in ent_text:
                    continue
                
                # Enthält problematische Wörter -> komplett skippen
                if any(bl_word in ent_text for bl_word in ['Gesendet', 'Betreff', 'müsstest', 'müsste', 'könntest', 'solltest']):
                    continue
                
                # === V4.2: SMART EXTRACTION ===
                # Statt Entity zu blockieren, extrahiere den echten Namen
                words = ent_text.split()
                actual_text = ent_text
                actual_start = e.start_char
                actual_end = e.end_char
                
                if len(words) >= 2 and e.label_ == 'PER':
                    first_word = words[0]
                    last_word = words[-1]
                    
                    # "Lieber Max" → nur "Thomas" extrahieren
                    if first_word in self.SPACY_BLACKLIST:
                        remaining = ' '.join(words[1:])
                        if remaining and remaining not in self.SPACY_BLACKLIST:
                            # Berechne neue Position
                            offset = len(first_word) + 1  # +1 für Leerzeichen
                            actual_text = remaining
                            actual_start = e.start_char + offset
                            actual_end = e.end_char
                        else:
                            continue  # Nichts übrig
                    
                    # "Thomas Gesendet" → nur "Thomas" extrahieren  
                    elif last_word in self.SPACY_BLACKLIST:
                        remaining = ' '.join(words[:-1])
                        if remaining and remaining not in self.SPACY_BLACKLIST:
                            actual_text = remaining
                            actual_start = e.start_char
                            actual_end = e.start_char + len(remaining)
                        else:
                            continue  # Nichts übrig
                
                # Zusätzliche Validierung für PERSON
                if e.label_ == 'PER':
                    # Muss mindestens einen Großbuchstaben haben
                    if not any(c.isupper() for c in actual_text):
                        continue
                    # Keine reinen Zahlen
                    if actual_text.isdigit():
                        continue
                    # Nicht nur Sonderzeichen
                    if not any(c.isalpha() for c in actual_text):
                        continue
                    # Einzelnes Wort in Blacklist
                    if actual_text in self.SPACY_BLACKLIST:
                        continue
                
                ents.append((actual_start, actual_end, actual_text, e.label_))
            
            # Von hinten nach vorne ersetzen
            ents.sort(key=lambda x: x[0], reverse=True)
            
            for start, end, txt, label in ents:
                mapped = self.SPACY_ENTITY_MAP.get(label, label)
                ph = em.add(txt, mapped)
                # V4.3: Füge Leerzeichen hinzu wenn nächstes Zeichen ein Buchstabe ist
                if end < len(text) and text[end].isalpha():
                    ph = ph + ' '
                text = text[:start] + ph + text[end:]
                counts[mapped] = counts.get(mapped, 0) + 1
            
            return text, counts
        except Exception as e:
            logger.warning(f"spaCy error: {e}")
            return text, {}
    
    def sanitize_batch(self, items: List[Tuple[str, str]], level: int = 3) -> List[SanitizationResult]:
        return [self.sanitize(s, b, level) for s, b in items]


def sanitize_email(subject: str, body: str, level: int = 3) -> SanitizationResult:
    return get_sanitizer().sanitize(subject, body, level)


def deanonymize_response(response: str, entity_map: EntityMap) -> str:
    return entity_map.deanonymize(response)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # DUMMY-TESTDATEN - KEINE ECHTEN DATEN!
    test = """Lieber Max

Mit diesen Anpassungen können wir den Vertrag finalisieren.

Herzliche Grüsse
Peter

Dr. Peter Beispiel | Direktor Abteilung | Chief Example Officer
Beispiel AG | Hauptsitz | Abteilung Test
Musterstrasse 123 | Postfach | CH-1234 Musterstadt | Schweiz
Tel +41 12 345 67 89
Mail: peter.beispiel@example.com | http://www.example.com

Von: Max Mustermann <max.mustermann@example.com>
Gesendet: Montag, 1. Januar 2025 10:00
An: Peter Beispiel <peter.beispiel@example.com>

Vielen Dank für die Rückmeldung.
Anna und ich stimmen uns ab.

Passt das so für dich?

Viele Grüsse
Max

Max Mustermann | Leitung Projekt | Head Project
Beispiel AG | Hauptsitz | Abteilung Test
Testweg 456 | Postfach | 5678 Teststadt | Schweiz
Tel +41 98 765 43 21
Mail: max.mustermann@example.com | http://www.example.com
"""
    
    result = get_sanitizer().sanitize("AW: Test", test, level=3)
    
    print("=" * 70)
    print("ANONYMISIERT:")
    print("=" * 70)
    print(result.body)
    print()
    print("=" * 70)
    print(f"ENTITY MAP ({result.entities_found} Entities):")
    print("=" * 70)
    for orig, ph in result.entity_map.forward.items():
        print(f"  {ph:20} <- {orig[:50]}{'...' if len(orig) > 50 else ''}")
    
    print()
    print("TESTS:")
    print(f"  2025 intakt: {'✅' if '2025' in result.body else '❌'}")
    print(f"  Telefon erkannt: {'✅' if '[PHONE_' in result.body else '❌'}")
    print(f"  Von: korrekt: {'✅' if 'Von: [PERSON_' in result.body else '❌'}")
    print(f"  Herzliche intakt: {'✅' if 'Herzliche' in result.body else '❌'}")
    print(f"  Zeilenumbrüche: {'✅' if result.body.count(chr(10)) > 10 else '❌'}")
