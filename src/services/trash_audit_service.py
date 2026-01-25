"""
Trash Audit Service - Analysiert Papierkorb-Emails für sichere Löschung

Verwendet Heuristiken zur Kategorisierung:
- 🟢 SAFE: Newsletter, Spam, Marketing, Scam → sicher löschbar
- 🟡 REVIEW: Unbekannte Absender, ältere Mails → manuell prüfen  
- 🔴 IMPORTANT: Bekannte Kontakte, Rechnungen, etc. → nicht löschen

Kein AI-API-Call nötig - rein lokale Analyse.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum
import importlib
from email.header import decode_header as mime_decode_header, make_header

logger = logging.getLogger(__name__)

# Lazy-loaded module cache (wird einmal geladen, nicht 3,500x)
_models_cache = None
_mail_sync_cache = None
_trusted_senders_cache = None

def _get_models():
    """Cached import of models module."""
    global _models_cache
    if _models_cache is None:
        _models_cache = importlib.import_module(".02_models", "src")
    return _models_cache

def _get_mail_sync():
    """Cached import of mail_sync module."""
    global _mail_sync_cache
    if _mail_sync_cache is None:
        _mail_sync_cache = importlib.import_module(".16_mail_sync", "src")
    return _mail_sync_cache

def _get_trusted_senders():
    """Cached import of trusted_senders module."""
    global _trusted_senders_cache
    if _trusted_senders_cache is None:
        _trusted_senders_cache = importlib.import_module(".services.trusted_senders", "src")
    return _trusted_senders_cache


# =============================================================================
# Audit Config Loader (aus DB statt hardcoded)
# =============================================================================

class AuditConfigCache:
    """Cache für Audit-Konfiguration aus DB.
    
    Lädt einmal pro Session und cached die Werte für schnellen Zugriff.
    """
    _cache = {}  # Key: (user_id, account_id)
    
    @classmethod
    def get_config(cls, db_session, user_id: int, account_id: Optional[int] = None) -> dict:
        """Lädt Audit-Config aus DB mit Caching.
        
        Returns:
            {
                'trusted_domains': set(['ubs.com', 'iliad.it', ...]),
                'important_keywords': set(['rechnung', 'fattura', ...]),
                'safe_subject_patterns': set(['newsletter', 'rabatt', ...]),
                'safe_sender_patterns': set(['newsletter@', 'noreply@', ...]),
                'vip_senders': set(['chef@firma.de', '@wichtig.de', ...]),
                'auto_delete_rules': [...],  # Liste von Regel-Dicts
            }
        """
        cache_key = (user_id, account_id)
        
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        models = _get_models()
        config = {
            'trusted_domains': set(),
            'important_keywords': set(),
            'safe_subject_patterns': set(),
            'safe_sender_patterns': set(),
            'vip_senders': set(),
            'vip_pattern_types': {},  # pattern -> pattern_type
            'auto_delete_rules': [],  # Liste von Regeln
        }
        
        try:
            # Trusted Domains
            domains = db_session.query(models.AuditTrustedDomain).filter(
                models.AuditTrustedDomain.user_id == user_id,
                models.AuditTrustedDomain.is_active == True,
                (models.AuditTrustedDomain.account_id == account_id) | 
                (models.AuditTrustedDomain.account_id == None)
            ).all()
            config['trusted_domains'] = {d.domain.lower() for d in domains}
            
            # Important Keywords
            keywords = db_session.query(models.AuditImportantKeyword).filter(
                models.AuditImportantKeyword.user_id == user_id,
                models.AuditImportantKeyword.is_active == True,
                (models.AuditImportantKeyword.account_id == account_id) | 
                (models.AuditImportantKeyword.account_id == None)
            ).all()
            config['important_keywords'] = {k.keyword.lower() for k in keywords}
            
            # Safe Patterns
            patterns = db_session.query(models.AuditSafePattern).filter(
                models.AuditSafePattern.user_id == user_id,
                models.AuditSafePattern.is_active == True,
                (models.AuditSafePattern.account_id == account_id) | 
                (models.AuditSafePattern.account_id == None)
            ).all()
            
            for p in patterns:
                if p.pattern_type == 'subject':
                    config['safe_subject_patterns'].add(p.pattern.lower())
                elif p.pattern_type == 'sender':
                    config['safe_sender_patterns'].add(p.pattern.lower())
            
            # VIP Senders
            vips = db_session.query(models.AuditVIPSender).filter(
                models.AuditVIPSender.user_id == user_id,
                models.AuditVIPSender.is_active == True,
                (models.AuditVIPSender.account_id == account_id) | 
                (models.AuditVIPSender.account_id == None)
            ).all()
            
            for v in vips:
                pattern = v.sender_pattern.lower()
                config['vip_senders'].add(pattern)
                config['vip_pattern_types'][pattern] = v.pattern_type
            
            # Auto-Delete Rules
            if hasattr(models, 'AuditAutoDeleteRule'):
                try:
                    rules = db_session.query(models.AuditAutoDeleteRule).filter(
                        models.AuditAutoDeleteRule.user_id == user_id,
                        models.AuditAutoDeleteRule.is_active == True,
                        (models.AuditAutoDeleteRule.account_id == account_id) | 
                        (models.AuditAutoDeleteRule.account_id == None)
                    ).all()
                    
                    for r in rules:
                        config['auto_delete_rules'].append({
                            'sender_pattern': r.sender_pattern.lower() if r.sender_pattern else None,
                            'subject_pattern': r.subject_pattern.lower() if r.subject_pattern else None,
                            'disposition': r.disposition,
                            'max_age_days': r.max_age_days,
                            'description': r.description,
                        })
                except Exception as e:
                    logger.debug(f"Auto-delete rules not available yet: {e}")
            
            logger.debug(f"Loaded audit config for user {user_id}: "
                        f"{len(config['trusted_domains'])} domains, "
                        f"{len(config['important_keywords'])} keywords, "
                        f"{len(config['safe_subject_patterns'])} safe subject patterns, "
                        f"{len(config['safe_sender_patterns'])} safe sender patterns, "
                        f"{len(config['vip_senders'])} VIP senders, "
                        f"{len(config['auto_delete_rules'])} auto-delete rules")
            
        except Exception as e:
            logger.warning(f"Failed to load audit config from DB: {e}")
        
        cls._cache[cache_key] = config
        return config
    
    @classmethod
    def clear_cache(cls, user_id: Optional[int] = None):
        """Löscht Cache (bei Config-Änderungen)."""
        if user_id:
            keys_to_remove = [k for k in cls._cache if k[0] == user_id]
            for k in keys_to_remove:
                del cls._cache[k]
        else:
            cls._cache.clear()


def _match_vip_sender(sender_email: str, vip_senders: set, vip_pattern_types: dict) -> Optional[str]:
    """Prüft ob Absender ein VIP ist.
    
    Returns:
        Matching pattern oder None
    """
    if not sender_email or not vip_senders:
        return None
    
    sender_lower = sender_email.lower()
    domain = sender_lower.split('@')[-1] if '@' in sender_lower else ''
    
    for pattern in vip_senders:
        pattern_type = vip_pattern_types.get(pattern, 'domain')
        
        if pattern_type == 'exact':
            if sender_lower == pattern:
                return pattern
        elif pattern_type == 'email_domain':
            # @firma.de
            if pattern.startswith('@') and sender_lower.endswith(pattern):
                return pattern
        else:  # domain
            if domain == pattern or domain.endswith('.' + pattern):
                return pattern
    
    return None


def _match_auto_delete_rule(
    sender_email: str, 
    subject: str, 
    email_date: Optional[datetime],
    rules: list
) -> Optional[dict]:
    """Prüft ob Email einer Auto-Delete-Regel entspricht.
    
    Args:
        sender_email: Absender-Email (lowercase)
        subject: Betreff (lowercase)
        email_date: Email-Datum für Altersberechnung
        rules: Liste von Regel-Dicts aus AuditConfigCache
        
    Returns:
        Matching Rule-Dict oder None
        {
            'disposition': 'DELETABLE'|'PROTECTED'|'JUNK',
            'max_age_days': int|None,
            'description': str|None,
            'age_ok': bool  # True wenn Email alt genug ist
        }
    """
    if not rules:
        return None
    
    sender_lower = sender_email.lower() if sender_email else ""
    subject_lower = subject.lower() if subject else ""
    
    for rule in rules:
        sender_pattern = rule.get('sender_pattern')
        subject_pattern = rule.get('subject_pattern')
        
        # Beide Patterns müssen matchen (falls gesetzt)
        sender_matches = True
        subject_matches = True
        
        # Sender Pattern prüfen
        if sender_pattern:
            sender_matches = False
            if sender_pattern in sender_lower:
                sender_matches = True
        
        # Subject Pattern prüfen (unterstützt Regex)
        if subject_pattern:
            subject_matches = False
            try:
                if re.search(subject_pattern, subject_lower):
                    subject_matches = True
            except re.error:
                # Fallback: einfacher String-Match
                if subject_pattern in subject_lower:
                    subject_matches = True
        
        # Nur wenn BEIDE matchen (falls gesetzt)
        if sender_matches and subject_matches:
            disposition = rule.get('disposition')
            max_age_days = rule.get('max_age_days')
            
            # Alter prüfen für DELETABLE
            age_ok = True
            if disposition == 'DELETABLE' and max_age_days is not None and email_date:
                try:
                    now = datetime.now(UTC)
                    if email_date.tzinfo is None:
                        email_date = email_date.replace(tzinfo=UTC)
                    age_days = (now - email_date).days
                    age_ok = age_days >= max_age_days
                except Exception:
                    age_ok = False
            
            return {
                'disposition': disposition,
                'max_age_days': max_age_days,
                'description': rule.get('description'),
                'age_ok': age_ok,
            }
    
    return None


# =============================================================================
# MIME Header Decoding Helper
# =============================================================================

def decode_mime_header(value: str) -> str:
    """Dekodiert MIME Encoded-Word Header (RFC 2047).
    
    Nutzt make_header(decode_header(...)) für robuste Behandlung von:
    - Mehrteiligen Headers (über mehrere Zeilen gesplittet)
    - Verschiedenen Charsets in einem Header
    
    Beispiele:
        =?UTF-8?Q?Hallo_Welt?= → "Hallo Welt"
        =?UTF-8?B?SGFsbG8gV2VsdA==?= → "Hallo Welt"
    """
    if not value:
        return ""
    
    try:
        # Prüfen ob es ein encoded-word ist
        if '=?' not in value:
            return value
        
        # Robusteste Methode: make_header fügt alle Teile korrekt zusammen
        decoded = str(make_header(mime_decode_header(value)))
        return decoded.strip()
        
    except Exception as e:
        # Fallback: Manuelle Dekodierung
        try:
            decoded_parts = []
            parts = mime_decode_header(value)
            
            for content, charset in parts:
                if isinstance(content, bytes):
                    charset = charset or 'utf-8'
                    try:
                        decoded_parts.append(content.decode(charset, errors='replace'))
                    except (LookupError, UnicodeDecodeError):
                        decoded_parts.append(content.decode('utf-8', errors='replace'))
                else:
                    decoded_parts.append(content)
            
            return ' '.join(decoded_parts).strip()
        except Exception as e2:
            logger.debug(f"MIME decode error: {e2}")
            return value


class TrashCategory(Enum):
    """Kategorien für Trash-Audit"""
    SAFE = "safe"           # Sicher löschbar (Newsletter, Spam)
    REVIEW = "review"       # Manuell prüfen
    IMPORTANT = "important" # Möglicherweise wichtig
    SCAM = "scam"           # Definitiv bösartig/betrügerisch → sofort vernichten


@dataclass
class TrashEmailInfo:
    """Metadaten einer Email im Papierkorb"""
    uid: int
    subject: str
    sender: str
    sender_name: str
    date: Optional[datetime]
    has_attachments: bool
    flags: List[str]
    size: int
    
    # Attachment-Namen (aus BODYSTRUCTURE, ohne Body zu laden)
    attachment_names: List[str] = field(default_factory=list)
    content_summary: str = ""  # z.B. "HTML", "Text", "2 Bilder"
    
    # Power-Header (Server-seitige Vorarbeit nutzen)
    has_list_unsubscribe: bool = False      # Newsletter-Indikator (99% zuverlässig)
    is_reply: bool = False                   # Hat In-Reply-To Header (echte Konversation)
    in_reply_to_msgid: Optional[str] = None  # Message-ID der referenzierten Mail
    spam_score: Optional[float] = None       # X-Spam-Score vom Server
    auth_results: Optional[str] = None       # SPF/DKIM/DMARC Ergebnisse
    reply_to: Optional[str] = None           # Reply-To Header (für Mismatch-Erkennung)
    
    # Analyse-Ergebnisse
    category: TrashCategory = TrashCategory.REVIEW
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    
    # Clustering
    cluster_key: Optional[str] = None  # Normalisierter Key für Gruppierung
    folder: str = ""                   # Ordner aus dem die Email stammt
    
    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "subject": self.subject,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "date": self.date.isoformat() if self.date else None,
            "has_attachments": self.has_attachments,
            "attachment_names": self.attachment_names,
            "content_summary": self.content_summary,
            "size": self.size,
            "category": self.category.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "is_reply": self.is_reply,
            "cluster_key": self.cluster_key,
            "folder": self.folder,
        }


@dataclass
class TrashEmailCluster:
    """Ein Cluster von ähnlichen Emails"""
    cluster_key: str                    # Normalisierter Key
    display_name: str                   # Lesbare Beschreibung
    sender_domain: str                  # Domain des Absenders
    count: int = 0                      # Anzahl Emails
    category: TrashCategory = TrashCategory.REVIEW  # Dominante Kategorie
    uids: List[int] = field(default_factory=list)
    sample_subject: str = ""            # Beispiel-Betreff
    sample_sender: str = ""             # Beispiel-Absender (vollständig)
    oldest_date: Optional[datetime] = None
    newest_date: Optional[datetime] = None
    total_size: int = 0
    # Zähler pro Kategorie für genaue Statistiken
    safe_count: int = 0
    review_count: int = 0
    important_count: int = 0
    scam_count: int = 0                 # NEU: Scam-Emails im Cluster
    
    def to_dict(self) -> dict:
        return {
            "cluster_key": self.cluster_key,
            "display_name": self.display_name,
            "sender_domain": self.sender_domain,
            "count": self.count,
            "category": self.category.value,
            "uids": self.uids,
            "sample_subject": self.sample_subject,
            "sample_sender": self.sample_sender,
            "oldest_date": self.oldest_date.isoformat() if self.oldest_date else None,
            "newest_date": self.newest_date.isoformat() if self.newest_date else None,
            "total_size_kb": round(self.total_size / 1024, 1),
            "safe_count": self.safe_count,
            "review_count": self.review_count,
            "important_count": self.important_count,
            "scam_count": self.scam_count,
        }


@dataclass
class TrashAuditResult:
    """Gesamtergebnis des Trash-Audits"""
    total: int = 0
    safe_count: int = 0
    review_count: int = 0
    important_count: int = 0
    scam_count: int = 0                     # NEU: Anzahl Scam-Emails
    emails: List[TrashEmailInfo] = field(default_factory=list)
    clusters: List[TrashEmailCluster] = field(default_factory=list)  # NEU: Cluster-Liste
    scan_duration_ms: int = 0
    
    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "safe_count": self.safe_count,
            "review_count": self.review_count,
            "important_count": self.important_count,
            "scam_count": self.scam_count,
            "scan_duration_ms": self.scan_duration_ms,
            "emails": [e.to_dict() for e in self.emails],
            "clusters": [c.to_dict() for c in self.clusters],
        }


# =============================================================================
# Provider-Domain Konfiguration (für Authentication-Results Vertrauen)
# =============================================================================
# Nur wenn der Authentication-Results Header von DEINEM Provider stammt,
# kann ihm vertraut werden. Ein Angreifer kann Header "unten" hinzufügen,
# aber nie "über" den Header deines Servers.

TRUSTED_AUTH_PROVIDER_DOMAINS = [
    "hostpoint.ch",      # Schweizer Provider
    "google.com",        # Gmail
    "outlook.com",       # Microsoft
    "microsoft.com",     # Microsoft 365
    "yahoo.com",         # Yahoo
    "protonmail.com",    # ProtonMail
    "proton.me",         # ProtonMail neu
    "infomaniak.com",    # Schweizer Provider
    "mailbox.org",       # Deutscher Privacy Provider
    "icloud.com",        # Apple
]


# =============================================================================
# Lazy Imports
# =============================================================================

_known_newsletters = None


def _get_known_newsletters():
    global _known_newsletters
    if _known_newsletters is None:
        _known_newsletters = importlib.import_module(".known_newsletters", "src")
    return _known_newsletters


# =============================================================================
# Brand-Domain Mapping (Scam Detection)
# =============================================================================
# Wenn jemand behauptet "TWINT" zu sein aber von @nanayojapan.co.jp sendet = SCAM!
# WICHTIG: Nur auf Absender-Namen und Absender-Email prüfen, NICHT auf Betreff!
# (Tech-News schreiben ÜBER Apple/Microsoft etc. - das ist kein Scam!)

BRAND_DOMAIN_MAP = {
    # Swiss Brands (nur Marken die oft für Phishing missbraucht werden)
    "twint": ["twint.ch", "news.twint.ch"],
    "swisscom": ["swisscom.com", "swisscom.ch"],
    "sbb": ["sbb.ch", "mailings.sbb.ch", "mailing.swisspass.ch", "swisspass.ch"],
    "postfinance": ["postfinance.ch"],
    "yuh": ["yuh.com"],
    # Swiss Insurance (oft Phishing-Ziel)
    "helsana": ["helsana.ch", "myhelsana.ch"],
    "css": ["css.ch", "mycss.ch"],
    "swica": ["swica.ch"],
    "sanitas": ["sanitas.ch"],
    # Swiss Universities
    "unibas": ["unibas.ch"],
    "ethz": ["ethz.ch"],
    "uzh": ["uzh.ch"],
    
    # International Brands (häufig für Phishing missbraucht)
    "paypal": ["paypal.com", "paypal.ch"],
    "mcafee": ["mcafee.com"],
    "norton": ["norton.com", "nortonlifelock.com"],
}

# Homoglyph-Map für Typosquatting-Erkennung
# Zeichen die visuell ähnlich aussehen
HOMOGLYPH_MAP = {
    '0': 'o',   # Zero → O
    '1': 'l',   # One → L
    'I': 'l',   # großes i → kleines L
    'l': 'l',   # bereits L
    'O': 'o',   # bereits O
    'o': 'o',
    '|': 'l',   # Pipe → L
    'rn': 'm',  # r+n sieht aus wie m
}

def normalize_homoglyphs(text: str) -> str:
    """Normalisiert Homoglyphen für Vergleiche.
    
    z.B. "myHeIsana" → "myhelsana"
    z.B. "unIbas" → "unlbas" → erkennt Typo
    """
    result = text.lower()
    # Erst rn → m (muss vor einzelnen Zeichen passieren)
    result = result.replace('rn', 'm')
    # Dann einzelne Zeichen
    for char, replacement in HOMOGLYPH_MAP.items():
        if char.lower() != replacement:  # Nur wenn unterschiedlich
            result = result.replace(char.lower(), replacement)
    # Großes I separat (case-sensitive)
    result_chars = list(result)
    for i, c in enumerate(text):
        if c == 'I':  # Großes I im Original
            result_chars[i] = 'l'
    return ''.join(result_chars)


# Bekannte Marken für Typosquatting-Check (mit korrekter Schreibweise)
TYPOSQUATTING_TARGETS = {
    "helsana": ["helsana.ch", "myhelsana.ch"],
    "css": ["css.ch", "mycss.ch"],
    "unibas": ["unibas.ch"],
    "swisscom": ["swisscom.ch", "swisscom.com"],
    "postfinance": ["postfinance.ch"],
    "raiffeisen": ["raiffeisen.ch"],
    "migros": ["migros.ch"],
    "coop": ["coop.ch"],
}

# Diese Marken werden NICHT geprüft wenn sie von bekannten News/Shop-Domains kommen:
# (um False Positives wie "heise schreibt über Apple" zu vermeiden)
# NUR allgemein bekannte Domains - persönliche gehören in DB-Config!
BRAND_CHECK_WHITELIST_DOMAINS = {
    # === TECH-NEWS (schreiben ÜBER Brands) ===
    "heise.de", "newsletter.heise.de",
    "chip.de", "golem.de", "t3n.de",
    
    # === SCHWEIZER SHOPS (mehrere Marken) ===
    "digitec.ch", "galaxus.ch",
    "zalando.ch", "aboutyou.ch",
    
    # === SOCIAL MEDIA ===
    "linkedin.com", "instagram.com", "facebook.com",
    
    # === PAYMENT/RESELLER ===
    "digitalriver.com", "fastspring.com", "stripe.com",
    "amazon.de", "amazon.com", "amazon.ch",
}

# Trusted Swiss Domains (Whitelist) - NUR allgemein gültige CH/EU Domains
# Persönliche/spezifische Domains gehören in die DB-Konfiguration!
# =============================================================================
# TRUSTED DOMAINS - NUR absolutes Minimum im Code!
# Alles andere kommt aus der DB via audit_config['trusted_domains']
# =============================================================================

# Globale Plattformen (für ALLE User weltweit relevant)
TRUSTED_GLOBAL_DOMAINS = {
    # Big Tech (weltweit relevant)
    "google.com", "microsoft.com", "apple.com",
    "amazon.de", "amazon.com", "amazon.ch",
    # Payment (weltweit)
    "paypal.com", "stripe.com", "paddle.com",
    # Social (weltweit)
    "linkedin.com", "instagram.com", "facebook.com", "twitter.com",
    # Email Provider (eigener = nie Scam)
    "gmx.ch", "gmx.de", "gmx.net", "gmx.at",
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com",
    "protonmail.com", "proton.me",
    "icloud.com",
}

# Schweizer Grundversorgung (für alle CH-User relevant, nicht personalisierbar)
TRUSTED_SWISS_BASE = {
    # Behörden (Basis)
    "admin.ch",
    # Transport
    "sbb.ch", "post.ch",
    # Telco
    "swisscom.com", "swisscom.ch",
}

# Kombiniert für Rückwärtskompatibilität
TRUSTED_SWISS_DOMAINS = TRUSTED_GLOBAL_DOMAINS | TRUSTED_SWISS_BASE

# Spam/Scam Domain Patterns - diese Domains sind IMMER verdächtig
SCAM_DOMAIN_PATTERNS = [
    r"@.*\.onmicrosoft\.com$",  # Oft missbraucht für Phishing
    r"@.*shopping-infos\.com$",
    r"@.*selected-sales\.de$",
    r"@.*select-traffic\.de$",
    r"@.*\-schutzwarnungen.*@",  # Fake Virus-Warnungen
    r"@.*boshamier\.info$",
    r"@.*hostservicenet.*\.interhost\.it$",
    r"@.*traffic\..*\.com$",  # traffic subdomains
    r"@.*\.info$.*@.*\.ru$",  # Kombination .info/.ru oft Spam
]

# Disposable/Wegwerf Email Domain Patterns
DISPOSABLE_DOMAIN_PATTERNS = [
    r"@tempmail",
    r"@temp-mail",
    r"@throwaway",
    r"@mailinator",
    r"@guerrillamail",
    r"@10minutemail",
    r"@fakeinbox",
    r"@trashmail",
    r"@dispostable",
]

# Clickbait/Scam Subject Patterns - Diese übersteuern "wichtige" Keywords!
# WICHTIG: Nur Patterns die FAST IMMER Scam sind!
# Marketing-Newsletter (Sale, Rabatt) sind NICHT Scam!
CLICKBAIT_SCAM_PATTERNS = [
    # Extreme Phishing-Phrasen
    r"banken.*?panik|crash.*?warnung",
    r"\bfree\s+money\b|gratis.*?geld\b",
    r"nigeria|prince|prinz.*?(million|hilfe|transfer)",
    r"inheritance|erbschaft.*?(million|mio|begünstigt)",
    r"dringend.*?(million|transfer|überweisung)",
    r"geheime.*?(methode|trick|strategie|formel)",
    r"(euro|dollar|chf|usd)\s*spende",
    # Nur bei SEHR hohen Beträgen + verdächtigen Phrasen
    r"\b[1-9]\d*\s*(million|mio|milliarden).*?(gewinn|prize|preis|erhalten|bekommen|claim)",
    r"(gewinn|prize|preis).*?\b[1-9]\d*\s*(million|mio)",
    # Account-Drohungen (aber nicht von legitimen Domains - das prüfen wir separat)
    r"(konto|account).*?(gesperrt|suspended|locked|closed).*?(sofort|immediately|urgent)",
    r"(letzte|final|last)\s*(chance|warnung|warning).*?(sperrung|suspension|löschung)",
]


# =============================================================================
# Heuristik-Patterns
# =============================================================================

# Subject-Patterns die auf unwichtige Emails hindeuten
SAFE_SUBJECT_PATTERNS = [
    r"newsletter",
    r"weekly\s+digest",
    r"daily\s+digest",
    r"unsubscribe",
    r"rabatt|discount|sale|%\s*off",
    r"angebot|offer|deal",
    r"gutschein|coupon|voucher",
    r"black\s*friday|cyber\s*monday",
    r"newsletter.*kw\d+",
    r"your\s+weekly",
    r"new\s+arrivals?",
    r"just\s+dropped",
    r"flash\s+sale",
    r"limited\s+time",
    r"don'?t\s+miss",
    r"last\s+chance",
    r"reminder:\s*your\s+cart",
    r"items?\s+in\s+your\s+cart",
    r"we\s+miss\s+you",
    r"come\s+back",
]

# Subject-Patterns die auf wichtige Emails hindeuten
IMPORTANT_SUBJECT_PATTERNS = [
    r"rechnung|invoice|billing",
    r"vertrag|contract",
    r"kündigung|cancellation|termination",
    r"mahnung|reminder.*payment|overdue",
    r"(ihr|your|dein).?termin|termin.?(am|um|bei|bestätig)|appointment|meeting\s+(invite|request)",
    r"bewerbung|application|job",
    r"gehalt|salary|payroll",
    r"steuer|tax\s+(return|document)",
    r"versicherung|insurance\s+(claim|policy)",
    r"arzt|doctor|medical",
    r"anwalt|lawyer|legal",
    r"gericht|court",
    r"polizei|police",
    r"bank|konto|account.*statement",
    r"passwort|password.*reset",
    r"zwei.?faktor|2fa|verification\s+code",
    r"(sehr\s+)?wichtig|important\s+(notice|update)|urgent|dringend",
    r"action\s+required",
    r"confirm.*email|verify.*email",
    r"shipping|versand|tracking",
    r"order.*confirm|bestellung.*bestätigt",
]

# Sender-Patterns für sichere Löschung (Newsletter/Marketing)
SAFE_SENDER_PATTERNS = [
    r"newsletter@",
    r"@newsletter\.",          # Newsletter subdomain (z.B. @newsletter.heise.de)
    r"@mailings?\.",           # Mailings subdomain (z.B. @mailings.sbb.ch)
    r"noreply.*newsletter",
    r"marketing@",
    r"promo@",
    r"deals@",
    r"offers@",
    r"news@",
    r"digest@",
    r"weekly@",
    r"updates@",
    r"notifications?@",
    r"@mailchimp\.",
    r"@sendgrid\.",
    r"@hubspot\.",
    r"@klaviyo\.",
    r"@constantcontact\.",
    r"@ch-news\.",             # Adidas CH etc.
    r"@info\.",                # Info subdomain
    r"-club@",                 # z.B. ct-club@
]

# System/Automatisierungs-Mails (sehr wahrscheinlich löschbar)
SYSTEM_SENDER_PATTERNS = [
    r"^root@",               # Cron-Jobs, System-Mails
    r"^cron@",               # Cron-Daemon
    r"^daemon@",             # System-Daemon
    r"^postmaster@",         # Postmaster
    r"^mailer-daemon@",      # Mail-Daemon
    r"@localhost$",          # Lokale Mails
    r"@.*\.local$",          # Lokale Domains
    r"@.*\.internal$",       # Interne Domains
    r"^noreply@.*\.local",   # NoReply von lokalen Diensten
]

# Erfolgs-/Status-Meldungen im Subject (kombiniert mit SYSTEM_SENDER → sehr safe)
SUCCESS_STATUS_PATTERNS = [
    r"(rsync|rclone|backup|sync).*?(erfolgreich|erfolg|success|completed|done)",
    r"(erfolgreich|erfolg|success|completed|done).*?(rsync|rclone|backup|sync)",
    r"backup.*?(complete|fertig|abgeschlossen)",
    r"(job|task|cronjob).*?(completed|finished|done|erfolgreich)",
    r"(scheduled|geplant).*?(task|job).*?(complete|fertig)",
    r"(system|server).*?(notification|benachrichtigung|status)",
    r"(unifi|ubiquiti).*?(changed|settings|update)",
]

# Sender-Patterns für wichtige Emails
IMPORTANT_SENDER_PATTERNS = [
    r"@.*bank\.ch",          # Schweizer Banken
    r"@.*bank\.de",          # Deutsche Banken  
    r"@.*bank\.at",          # Österreichische Banken
    r"@.*versicherung\.",
    r"@.*insurance\.",
    r"@finanzamt\.",
    r"@.*steuer\.",
    # Regierungen: Nur DACH (nicht weltweit!)
    r"@.*\.admin\.ch",       # Schweizer Bundesverwaltung
    r"@.*\.gv\.at",          # Österreich
    r"@.*bund\.de",          # Deutschland (bund.de oder subdomain.bund.de)
    r"@.*gericht\.",
    r"@.*anwalt\.",
    r"@.*lawyer\.",
    r"@paypal\.",
    r"@amazon\.",  # Bestellungen können wichtig sein
    r"@apple\.com",
    r"@google\.com",
    r"@microsoft\.com",
]


class TrashAuditService:
    """Service für Trash-Audit Analyse"""
    
    # =============================================================================
    # Subject Normalisierung für Clustering
    # =============================================================================
    
    @staticmethod
    def normalize_subject_for_clustering(subject: str) -> str:
        """Normalisiert Betreff für Clustering.
        
        Entfernt variable Teile wie Datum, Pfade, IDs, um Muster zu erkennen.
        
        Beispiele:
            "Rsync erfolgreich: von /media/nc_data/..." → "rsync erfolgreich: von <PATH>"
            "Backup 2025-01-15 completed" → "backup <DATE> completed"
            "Order #12345 confirmed" → "order #<ID> confirmed"
        """
        if not subject:
            return ""
        
        normalized = subject.lower().strip()
        
        # Entferne Re:/Fwd:/AW:/WG: Präfixe
        normalized = re.sub(r'^(re:|aw:|fwd:|wg:|fw:)\s*', '', normalized, flags=re.IGNORECASE)
        
        # Entferne Datum-Formate
        normalized = re.sub(r'\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}', '<DATE>', normalized)
        normalized = re.sub(r'\d{4}[./\-]\d{1,2}[./\-]\d{1,2}', '<DATE>', normalized)
        
        # Entferne Zeitangaben
        normalized = re.sub(r'\d{1,2}:\d{2}(:\d{2})?(\s*(am|pm|uhr))?', '<TIME>', normalized, flags=re.IGNORECASE)
        
        # Entferne Unix-Pfade
        normalized = re.sub(r'/[\w\-_./@]+/', '<PATH>', normalized)
        normalized = re.sub(r'/[\w\-_./@]+$', '<PATH>', normalized)
        
        # Entferne Windows-Pfade
        normalized = re.sub(r'[a-zA-Z]:\\[\w\-_.\\]+', '<PATH>', normalized)
        
        # Entferne UUIDs
        normalized = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '<UUID>', normalized, flags=re.IGNORECASE)
        
        # Entferne lange Hex-IDs (8+ Zeichen)
        normalized = re.sub(r'\b[a-f0-9]{8,}\b', '<ID>', normalized, flags=re.IGNORECASE)
        
        # Entferne numerische IDs (Order #12345, Ticket 98765)
        normalized = re.sub(r'#\d+', '#<ID>', normalized)
        normalized = re.sub(r'\b\d{5,}\b', '<ID>', normalized)  # 5+ Ziffern
        
        # Entferne Zahlen gefolgt von Einheiten/Kontext (149 package, 23 updates, etc.)
        normalized = re.sub(r'\b\d+\s+(package|update|message|item|file|error|warning|new|unread)', '<N> \\1', normalized, flags=re.IGNORECASE)
        
        # Entferne alleinstehende Zahlen 2+ Ziffern (aber nicht einzelne Ziffern wie in "Phase 2")
        normalized = re.sub(r'\b\d{2,}\b', '<N>', normalized)
        
        # Entferne IP-Adressen
        normalized = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '<IP>', normalized)
        
        # Entferne Hostnamen (server.domain.tld Format) - nach IP-Check!
        normalized = re.sub(r'\b[\w\-]+\.[\w\-]+\.(li|ch|de|at|com|net|org|io|local)\b', '<HOST>', normalized, flags=re.IGNORECASE)
        
        # Entferne Email-Adressen
        normalized = re.sub(r'[\w\.\-]+@[\w\.\-]+\.\w+', '<EMAIL>', normalized)
        
        # Normalisiere Whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Kürze auf max 80 Zeichen
        if len(normalized) > 80:
            normalized = normalized[:77] + '...'
        
        return normalized
    
    @staticmethod
    def create_cluster_key(sender_email: str, subject: str) -> str:
        """Erstellt einen Cluster-Key aus Sender-Domain + normalisiertem Subject."""
        domain = TrashAuditService._extract_domain(sender_email)
        normalized_subject = TrashAuditService.normalize_subject_for_clustering(subject)
        return f"{domain}|{normalized_subject}"
    
    @staticmethod
    def build_clusters(emails: List[TrashEmailInfo]) -> List[TrashEmailCluster]:
        """Gruppiert Emails zu Clustern basierend auf Ähnlichkeit.
        
        Returns:
            Liste von TrashEmailCluster, sortiert nach Anzahl (größte zuerst)
        """
        from collections import defaultdict
        
        cluster_map: Dict[str, TrashEmailCluster] = {}
        
        for email in emails:
            # Cluster-Key generieren
            key = TrashAuditService.create_cluster_key(email.sender, email.subject)
            email.cluster_key = key
            
            if key not in cluster_map:
                # Neuen Cluster erstellen
                domain = TrashAuditService._extract_domain(email.sender)
                display_name = TrashAuditService.normalize_subject_for_clustering(email.subject)
                if not display_name:
                    display_name = "(Kein Betreff)"
                
                cluster_map[key] = TrashEmailCluster(
                    cluster_key=key,
                    display_name=display_name,
                    sender_domain=domain,
                    sample_subject=email.subject,
                    sample_sender=email.sender,  # Vollständige Absender-Adresse
                    category=email.category,
                )
            
            cluster = cluster_map[key]
            cluster.count += 1
            cluster.uids.append(email.uid)
            cluster.total_size += email.size
            
            # Kategorie-Zähler inkrementieren
            if email.category == TrashCategory.SAFE:
                cluster.safe_count += 1
            elif email.category == TrashCategory.REVIEW:
                cluster.review_count += 1
            elif email.category == TrashCategory.IMPORTANT:
                cluster.important_count += 1
            elif email.category == TrashCategory.SCAM:
                cluster.scam_count += 1
            
            # Datum-Range tracken
            if email.date:
                if cluster.oldest_date is None or email.date < cluster.oldest_date:
                    cluster.oldest_date = email.date
                if cluster.newest_date is None or email.date > cluster.newest_date:
                    cluster.newest_date = email.date
            
            # Dominante Kategorie: nimm die "wichtigste" (SCAM > IMPORTANT > REVIEW > SAFE)
            if cluster.count == 1:
                cluster.category = email.category
            elif cluster.category != email.category:
                # Priorität: SCAM hat höchste, dann IMPORTANT, dann REVIEW, dann SAFE
                priority = {TrashCategory.SCAM: 4, TrashCategory.IMPORTANT: 3, 
                            TrashCategory.REVIEW: 2, TrashCategory.SAFE: 1}
                if priority.get(email.category, 0) > priority.get(cluster.category, 0):
                    cluster.category = email.category
        
        # Sortiere nach Anzahl (größte zuerst)
        clusters = sorted(cluster_map.values(), key=lambda c: c.count, reverse=True)
        
        return clusters
    
    # =============================================================================
    # Hilfsfunktionen
    # =============================================================================
    
    @staticmethod
    def _extract_domain(email: str) -> str:
        """Extrahiert Domain aus Email-Adresse."""
        if "@" in email:
            return email.split("@")[-1].lower().strip(">").strip()
        return ""
    
    @staticmethod
    def _check_brand_domain_mismatch(sender_name: str, sender_email: str, trusted_domains: Optional[set] = None) -> Optional[str]:
        """Prüft ob Absendername und Domain zueinander passen.
        
        Beispiel: "TWINT" von @nanayojapan.co.jp = SCAM!
        
        WICHTIG: Wird NUR auf Absendernamen angewendet, NICHT auf Betreff!
        (News schreiben ÜBER Brands - das ist kein Scam)
        
        Args:
            sender_name: Display-Name des Absenders
            sender_email: Email-Adresse des Absenders
            trusted_domains: Optional Set von trusted Domains aus DB-Config
        
        Returns:
            Grund-String wenn Mismatch erkannt, sonst None
        """
        if not sender_name or not sender_email:
            return None
        
        sender_name_lower = sender_name.lower()
        domain = TrashAuditService._extract_domain(sender_email)
        
        # Prüfe ob Absender von einer Whitelist-Domain kommt (hardcoded)
        for whitelist_domain in BRAND_CHECK_WHITELIST_DOMAINS:
            if domain == whitelist_domain or domain.endswith('.' + whitelist_domain):
                return None  # Diese Domain darf andere Brands erwähnen
        
        # Prüfe auch User-konfigurierte Trusted Domains aus DB
        if trusted_domains:
            for trusted in trusted_domains:
                if domain == trusted or domain.endswith('.' + trusted):
                    return None
        
        for brand, valid_domains in BRAND_DOMAIN_MAP.items():
            # Word-Boundary Matching: "twint" soll nicht in "twintastic" matchen
            # Aber "TWINT" als eigenständiges Wort im Namen = Match
            if not re.search(rf'\b{re.escape(brand)}\b', sender_name_lower):
                continue  # Brand nicht als ganzes Wort gefunden
            
            # Brand als Wort gefunden - prüfe ob Domain valide ist
            # KORREKTE Subdomain-Prüfung:
            #   - "sbb.ch" → exakter Match → OK
            #   - "mail.sbb.ch" → endet mit ".sbb.ch" → OK (echte Subdomain)
            #   - "sbb-marketing.ch" → SCAM! (enthält nur den Namen, ist keine Subdomain!)
            #   - "twint-secure.com" → SCAM! (Scammer registrieren genau solche Domains)
            domain_valid = False
            for valid_domain in valid_domains:
                # Exakter Match ODER echte Subdomain (mit Punkt davor!)
                if domain == valid_domain or domain.endswith('.' + valid_domain):
                    domain_valid = True
                    break
            
            if not domain_valid:
                return f"⚠️ SCAM: '{brand.upper()}' aber Domain '{domain}'"
        
        return None
    
    @staticmethod
    def _check_scam_patterns(sender_email: str) -> Optional[str]:
        """Prüft auf bekannte Scam-Domain-Patterns.
        
        Returns:
            Grund-String wenn Scam erkannt, sonst None
        """
        if not sender_email:
            return None
        
        sender_lower = sender_email.lower()
        
        # Scam Domain Patterns
        for pattern in SCAM_DOMAIN_PATTERNS:
            if re.search(pattern, sender_lower):
                return "⚠️ Bekannte Spam-Domain"
        
        # Disposable Email Patterns
        for pattern in DISPOSABLE_DOMAIN_PATTERNS:
            if re.search(pattern, sender_lower):
                return "⚠️ Wegwerf-Email"
        
        # Gibberish-Domain Detection (z.B. "sipeviuanw.de")
        domain = TrashAuditService._extract_domain(sender_email)
        if TrashAuditService._is_gibberish_domain(domain):
            return "⚠️ Verdächtige Random-Domain"
        
        return None
    
    @staticmethod
    def _is_gibberish_domain(domain: str) -> bool:
        """Erkennt zufällig generierte Domains (z.B. 'whvbavgmwn.org', 'gihnlihhbf@sipeviuanw.de').
        
        WICHTIG: Viele legitime Domains sehen "komisch" aus aber sind OK:
        - "liebscher-bracht.com" = legitimer deutscher Name
        - "fhschweiz.ch" = FH Schweiz Alumni
        - "newsletter.swiss.com" = Swiss Air Newsletter
        
        Wir erkennen nur ECHTEN Gibberish:
        - Sehr hoher Konsonanten-Anteil (keine aussprechbaren Silben)
        - Komplett zufällige Zeichenfolgen
        """
        if not domain or '.' not in domain:
            return False
        
        # Prüfe ob Domain in Trusted List
        for trusted in TRUSTED_SWISS_DOMAINS:
            if domain == trusted or domain.endswith('.' + trusted):
                return False  # Trusted = nie Gibberish
        
        # Nur den Hauptteil prüfen (ohne TLD), auch ohne Subdomains
        parts = domain.rsplit('.', 1)[0]  # Entferne TLD
        # Wenn es eine Subdomain ist, prüfe den Hauptdomain-Teil
        main_part = parts.split('.')[-1] if '.' in parts else parts
        
        if len(main_part) < 8:
            return False  # Zu kurz für zuverlässige Gibberish-Erkennung
        
        # Entferne Zahlen und Bindestriche - nur Buchstaben zählen
        letters_only = ''.join(c for c in main_part.lower() if c.isalpha())
        if len(letters_only) < 7:
            return False
        
        # Bekannte Wort-Muster die OK sind (deutsche/englische Namen, Marken)
        # Diese sehen "komisch" aus, sind aber legitim
        known_patterns = [
            'newsletter', 'software', 'master', 'service', 'support',
            'schweiz', 'swiss', 'bracht', 'liebscher', 'lastpass',
            'goodsync', 'fastspring', 'worldpay', 'stripe', 'paddle',
            'philips', 'panasonic', 'collabora', 'planzer', 'interdiscount',
            'letsgo', 'shopping', 'trolley', 'merchant',
        ]
        for pattern in known_patterns:
            if pattern in letters_only:
                return False
        
        # Zähle Vokale und Konsonanten
        vowels = sum(1 for c in letters_only if c in 'aeiou')
        consonants = len(letters_only) - vowels
        
        if vowels == 0:
            return True  # Keine Vokale = definitiv Gibberish
        
        ratio = consonants / vowels
        
        # NUR bei extremen Ratios und langen Strings = Gibberish
        # Erhöht von 2.5 auf 3.0 um False Positives zu reduzieren
        if ratio > 3.0 and len(letters_only) > 8:
            return True
        
        # Prüfe auf SEHR ungewöhnliche Trigramme (nur die schlimmsten)
        # Reduziert von vorher - nur echte Gibberish-Muster
        extreme_gibberish = ['qxz', 'xzq', 'vwxyz', 'bcdfg', 'ghjkl', 'mnpqr']
        for pattern in extreme_gibberish:
            if pattern in letters_only:
                return True
        
        return False
    
    @staticmethod
    def _check_sender_name_mismatch(sender_name: str, sender_email: str) -> Optional[str]:
        """Erkennt ECHTE Fake-Namen bei Scam-Emails.
        
        Beispiel SCAM: 'Markus Lanz' aber email='gihnlihhbf@sipeviuanw.de'
        → Berühmter Name + Gibberish-Email = definitiv Scam!
        
        WICHTIG: Firmenname als Display-Name ist NORMAL und KEIN Scam!
        - "Swiss International Air Lines" von news@newsletter.swiss.com → OK!
        - "Liebscher & Bracht" von noreply@liebscher-bracht.com → OK!
        - "Miles & More" von newsletter@mailing.milesandmore.com → OK!
        
        Wir erkennen nur:
        1. Prominenten-Namen (Markus Lanz, Elon Musk) von Gibberish-Domains
        2. Personennamen (Vor- Nachname) von komplett fremden Domains
        
        Returns:
            Grund-String wenn Fake erkannt, sonst None
        """
        if not sender_name or not sender_email:
            return None
        
        if '@' not in sender_email:
            return None
        
        local_part = sender_email.split('@')[0].lower()
        domain = TrashAuditService._extract_domain(sender_email)
        name_lower = sender_name.lower()
        
        # NICHT prüfen wenn Domain in Trusted List
        for trusted in TRUSTED_SWISS_DOMAINS:
            if domain == trusted or domain.endswith('.' + trusted):
                return None  # Trusted Domain = kein Fake-Check nötig
        
        # NICHT prüfen wenn es nach Firma/Service aussieht (das ist normal!)
        company_indicators = [
            'team', 'support', 'info', 'service', 'noreply', 'newsletter',
            'official', 'studio', 'gmbh', 'ag', 'ltd', 'inc', 'llc',
            'shop', 'store', 'club', 'news', 'mail', 'alert', 'update',
            'schweiz', 'swiss', 'suisse', 'svizzera',
            'international', 'airlines', 'air lines',
            'specialists', 'spezialisten', 'experts',
            'angebote', 'benefits', 'offers', 'promo',
            '&',  # Firmen haben oft & im Namen
        ]
        if any(indicator in name_lower for indicator in company_indicators):
            return None  # Firmenname = normal, kein Fake
        
        # NICHT prüfen wenn Local-Part normale Newsletter-Muster hat
        normal_local_patterns = [
            'news', 'newsletter', 'noreply', 'no-reply', 'info', 'mail',
            'support', 'service', 'team', 'hello', 'contact', 'admin',
            'updates', 'notifications', 'alerts', 'marketing', 'promo',
        ]
        if any(pattern in local_part for pattern in normal_local_patterns):
            return None  # Normale Newsletter-Email
        
        # Jetzt prüfen wir auf echte Fakes:
        # Personenname (Vorname Nachname) von Gibberish-Domain
        
        # Hat der Name das Format "Vorname Nachname" oder "Vorname.Nachname"?
        name_parts = re.split(r'[\s.]+', name_lower)
        name_parts = [p for p in name_parts if len(p) > 2 and p.isalpha()]
        
        # Mindestens 2 Teile und beide sehen nach Namen aus (nicht nach Firma)
        looks_like_person_name = (
            len(name_parts) >= 2 and
            all(len(p) > 2 and p[0].isalpha() for p in name_parts[:2])
        )
        
        if not looks_like_person_name:
            return None  # Kein Personenname-Format
        
        # Prüfe ob der Local-Part der Email Gibberish ist
        # (echter Scam: Promi-Name + komplett zufällige Email)
        letters_only = ''.join(c for c in local_part if c.isalpha())
        if len(letters_only) < 6:
            return None  # Zu kurz für Gibberish-Check
        
        vowels = sum(1 for c in letters_only if c in 'aeiou')
        consonants = len(letters_only) - vowels
        
        # Extremes Verhältnis = Gibberish Local-Part
        if vowels > 0 and consonants / vowels > 2.5 and len(letters_only) > 8:
            return f"⚠️ Fake-Absendername ('{sender_name}' + Gibberish-Email)"
        
        # Prüfe auch ob die Domain selbst Gibberish ist
        if TrashAuditService._is_gibberish_domain(domain):
            return f"⚠️ Fake-Absendername ('{sender_name}' + Random-Domain)"
        
        return None
    
    @staticmethod
    def _is_trusted_domain(sender_email: str) -> bool:
        """Prüft ob Email von vertrauenswürdiger Schweizer Domain kommt."""
        if not sender_email:
            return False
        
        domain = TrashAuditService._extract_domain(sender_email)
        
        for trusted in TRUSTED_SWISS_DOMAINS:
            if domain == trusted or domain.endswith("." + trusted):
                return True
        
        return False
    
    # =============================================================================
    # Scam Detection Methods
    # =============================================================================
    
    # Suspicious TLDs - oft für Spam/Scam missbraucht (kostenlose oder billige TLDs)
    # HINWEIS: Einige legitime Firmen nutzen diese TLDs, daher nur in Kombination
    # mit anderen Signalen als verdächtig werten!
    SUSPICIOUS_TLDS = {
        '.xyz', '.top', '.click', '.buzz', '.loan', '.work', 
        '.gq', '.ml', '.cf', '.tk', '.ga',  # Kostenlose TLDs (Freenom)
        '.icu', '.online', '.site', '.website',
        '.pw', '.su', '.bid', '.stream', '.download',
        # ENTFERNT: '.cc' - legitime Firmen wie itead.cc, ewelink.cc nutzen das
        # ENTFERNT: '.club' - manche legitime Shops nutzen das
    }
    
    # Whitelist für TLDs die eigentlich verdächtig sind aber von bekannten Firmen genutzt werden
    SUSPICIOUS_TLD_WHITELIST = {
        'itead.cc',      # SONOFF / ITEAD Smart Home Hardware
        'ewelink.cc',    # eWeLink Smart Home App
    }
    
    @staticmethod
    def _check_reply_to_mismatch(sender_email: str, reply_to: Optional[str]) -> Optional[str]:
        """Erkennt From ≠ Reply-To Mismatch = klassischer Scam-Trick.
        
        Scammer fälschen "From" um seriös auszusehen, brauchen aber echte
        Reply-To Adresse um Antworten zu empfangen.
        
        Returns:
            Grund-String wenn Mismatch erkannt, sonst None
        """
        if not reply_to or not sender_email:
            return None
        
        # Extrahiere Domains
        from_domain = TrashAuditService._extract_domain(sender_email)
        reply_domain = TrashAuditService._extract_domain(reply_to)
        
        if not from_domain or not reply_domain:
            return None
        
        # Gleiche Domain = OK
        if from_domain == reply_domain:
            return None
        
        # Subdomains erlauben (z.B. newsletter.firma.de → firma.de)
        if from_domain.endswith('.' + reply_domain) or reply_domain.endswith('.' + from_domain):
            return None
        
        # Gemeinsame Root-Domain extrahieren und vergleichen
        # z.B. "ch-news.adidas.com" und "link.adidas.com" → beide "adidas.com"
        def get_root_domain(domain: str) -> str:
            parts = domain.split('.')
            if len(parts) >= 2:
                # Für .co.uk, .com.au etc. müssten wir Public Suffix List nutzen
                # Vereinfachung: nehme die letzten 2 Teile
                return '.'.join(parts[-2:])
            return domain
        
        from_root = get_root_domain(from_domain)
        reply_root = get_root_domain(reply_domain)
        
        if from_root == reply_root:
            return None  # Gleiche Root-Domain = OK
        
        # Bekannte Ausnahmen (Mailinglisten, Multi-Domain Firmen)
        # Format: (from_pattern, reply_pattern) - kann partial matches sein
        # NUR allgemein gültige Beziehungen - persönliche gehören in DB-Config!
        KNOWN_DOMAIN_RELATIONSHIPS = [
            # === GROSSE PLATTFORMEN ===
            ('googlegroups.com', 'google.com'),
            ('amazon.de', 'amazon.com'),
            ('amazon.ch', 'amazon.com'),
            
            # === SCHWEIZER MULTI-DOMAIN FIRMEN ===
            # AMAG = offizieller Schweizer Importeur für VW, SEAT, CUPRA, Skoda
            ('volkswagen.ch', 'amag.ch'),
            ('seat.ch', 'amag.ch'),
            ('cupraofficial.ch', 'amag.ch'),
            ('skoda.ch', 'amag.ch'),
            # Interdiscount
            ('info.interdiscount.ch', 'service.interdiscount.ch'),
            # Miles & More (Lufthansa Group)
            ('mailing.milesandmore.com', 'milesandmoremailing.de'),
            
            # === MARKETING-PLATTFORMEN (allgemein) ===
            # Diese senden für ALLE Shops - Wildcard-Match
            ('shopifyemail.com', '*'),
            ('parcelpanel.com', '*'),
            ('ccsend.com', '*'),
            ('shared1.ccsend.com', '*'),
            ('trustpilotmail.com', '*'),
            ('event.eventbrite.com', '*'),
            ('wordpress.com', '*'),
            ('afterbuy.de', '*'),
            ('mailchimp.com', '*'),
            ('sendgrid.net', '*'),
            
            # === SCHWEIZER DIENSTE ===
            ('axa.ch', '*'),
            ('axa-arag.ch', '*'),
            ('chmedia.ch', '*'),
        ]
        
        # Spezial-Check: From oder Reply-To ist eine bekannte Marketing-Plattform
        MARKETING_PLATFORMS = {
            'shopifyemail.com', 'parcelpanel.com', 'ccsend.com', 'shared1.ccsend.com',
            'trustpilotmail.com', 'eventbrite.com', 'event.eventbrite.com',
            'wordpress.com', 'afterbuy.de', 'mailchimp.com', 'sendgrid.net',
            'constantcontact.com', 'hubspot.com', 'mailgun.org', 'sparkpost.com',
            'beacons.email', 'beacons.ai',
        }
        
        # Wenn From ODER Reply-To eine Marketing-Plattform ist → OK
        if any(plat in from_domain for plat in MARKETING_PLATFORMS):
            return None
        if any(plat in reply_domain for plat in MARKETING_PLATFORMS):
            return None
        
        for from_pattern, reply_pattern in KNOWN_DOMAIN_RELATIONSHIPS:
            # Prüfe beide Richtungen
            if (from_pattern in from_domain and reply_pattern in reply_domain) or \
               (reply_pattern in from_domain and from_pattern in reply_domain):
                return None
        
        # Wenn beide Domains in TRUSTED_SWISS_DOMAINS sind, ist es vermutlich OK
        from_trusted = any(from_domain == t or from_domain.endswith('.' + t) for t in TRUSTED_SWISS_DOMAINS)
        reply_trusted = any(reply_domain == t or reply_domain.endswith('.' + t) for t in TRUSTED_SWISS_DOMAINS)
        if from_trusted and reply_trusted:
            return None  # Beide vertrauenswürdig = vermutlich legitimes Setup
        
        return f"🚨 Reply-To Mismatch: From @{from_domain} → Reply-To @{reply_domain}"
    
    @staticmethod
    def _has_suspicious_tld(sender_email: str) -> Optional[str]:
        """Prüft ob Absender-Domain eine verdächtige TLD hat.
        
        Returns:
            Grund-String wenn verdächtig, sonst None
        """
        if not sender_email:
            return None
        
        domain = TrashAuditService._extract_domain(sender_email)
        if not domain:
            return None
        
        # Whitelist-Check - bekannte legitime Domains mit verdächtigen TLDs
        for whitelisted in TrashAuditService.SUSPICIOUS_TLD_WHITELIST:
            if domain == whitelisted or domain.endswith('.' + whitelisted):
                return None  # Whitelisted = nicht verdächtig
        
        for tld in TrashAuditService.SUSPICIOUS_TLDS:
            if domain.endswith(tld):
                return f"⚠️ Verdächtige TLD: {tld}"
        
        return None
    
    @staticmethod
    def _parse_auth_results(auth_results: Optional[str]) -> dict:
        """Parst Authentication-Results Header verschiedener Provider.
        
        Der Mail-Provider hat bereits SPF/DKIM/DMARC geprüft.
        Wir lesen nur sein Ergebnis - keine eigene Prüfung nötig.
        
        Returns:
            {
                'spf': 'pass'|'fail'|'softfail'|'none'|None,
                'dkim': 'pass'|'fail'|None,
                'dmarc': 'pass'|'fail'|None,
                'is_forged': bool,  # True wenn SPF/DKIM/DMARC fail
            }
        """
        result = {
            'spf': None,
            'dkim': None,
            'dmarc': None,
            'is_forged': False,
        }
        
        if not auth_results:
            return result
        
        auth_lower = auth_results.lower()
        
        # SPF: Sender Policy Framework
        if 'spf=pass' in auth_lower:
            result['spf'] = 'pass'
        elif 'spf=fail' in auth_lower:
            result['spf'] = 'fail'
            result['is_forged'] = True
        elif 'spf=softfail' in auth_lower:
            result['spf'] = 'softfail'
            # Softfail ist verdächtig aber nicht definitiv gefälscht
        elif 'spf=none' in auth_lower or 'spf=neutral' in auth_lower:
            result['spf'] = 'none'
        
        # DKIM: DomainKeys Identified Mail
        if 'dkim=pass' in auth_lower:
            result['dkim'] = 'pass'
        elif 'dkim=fail' in auth_lower:
            result['dkim'] = 'fail'
            result['is_forged'] = True
        
        # DMARC: Domain-based Message Authentication
        if 'dmarc=pass' in auth_lower:
            result['dmarc'] = 'pass'
        elif 'dmarc=fail' in auth_lower:
            result['dmarc'] = 'fail'
            result['is_forged'] = True
        
        return result
    
    @staticmethod
    def _calculate_scam_score(info: 'TrashEmailInfo', trusted_domains: Optional[set] = None) -> Tuple[int, List[str]]:
        """Berechnet Scam-Score basierend auf mehreren Signalen.
        
        Args:
            info: TrashEmailInfo mit Email-Metadaten
            trusted_domains: Optional Set von trusted Domains aus DB-Config
        
        Returns:
            (scam_signals: int, reasons: List[str])
        """
        scam_signals = 0
        reasons = []
        
        # Subject für Clickbait-Check extrahieren
        subject_lower = info.subject.lower() if info.subject else ''
        
        # 1. Reply-To Mismatch
        # WICHTIG: Allein KEIN starkes Signal! Viele legitime Firmen nutzen
        # Marketing-Plattformen mit anderem Reply-To.
        # Nur in Kombination mit anderen Signalen relevant.
        reply_to_issue = TrashAuditService._check_reply_to_mismatch(info.sender, info.reply_to)
        if reply_to_issue:
            scam_signals += 1  # Nur 1 Signal (vorher 2) - allein nicht ausreichend für SCAM
            reasons.append(reply_to_issue)
        
        # 2. Auth-Results (SPF/DKIM/DMARC) - strukturiert parsen
        # WICHTIG: DKIM-Fail bei alten Mails ignorieren (Signaturen können nach Jahren ungültig werden)
        auth = TrashAuditService._parse_auth_results(info.auth_results)
        is_old_email = False
        if info.date:
            from datetime import datetime, timezone
            try:
                age_days = (datetime.now(timezone.utc) - info.date).days
                is_old_email = age_days > 365  # Älter als 1 Jahr
            except:
                pass
        
        if auth['is_forged']:
            # Bei alten Mails: DKIM-Fail ignorieren, nur SPF/DMARC zählen
            if auth['spf'] == 'fail':
                scam_signals += 2
                reasons.append("🚨 SPF-Fail: Absender gefälscht")
            if auth['dkim'] == 'fail' and not is_old_email:
                # DKIM-Fail nur bei neueren Mails als Scam-Signal
                scam_signals += 1
                reasons.append("🚨 DKIM-Fail: Signatur ungültig")
            elif auth['dkim'] == 'fail' and is_old_email:
                # Bei alten Mails nur Info, kein Scam-Signal
                pass  # Ignorieren - DKIM-Keys werden oft rotiert
            if auth['dmarc'] == 'fail':
                scam_signals += 2
                reasons.append("🚨 DMARC-Fail: Domain-Policy verletzt")
        elif auth['spf'] == 'softfail':
            scam_signals += 1  # Verdächtig aber nicht definitiv
            reasons.append("⚠️ SPF-Softfail: Absender möglicherweise gefälscht")
        
        # 3. Suspicious TLD
        tld_issue = TrashAuditService._has_suspicious_tld(info.sender)
        if tld_issue:
            scam_signals += 1
            reasons.append(tld_issue)
        
        # 4. Brand-Domain Mismatch - NUR auf Absender-NAME prüfen, NICHT Betreff!
        # (News schreiben ÜBER Brands, das ist kein Scam)
        # Nutzt auch User-konfigurierte trusted_domains aus DB
        brand_issue = TrashAuditService._check_brand_domain_mismatch(info.sender_name, info.sender, trusted_domains)
        if brand_issue:
            scam_signals += 2
            reasons.append(brand_issue)
        
        # 5. Gibberish Domain
        domain = TrashAuditService._extract_domain(info.sender)
        if TrashAuditService._is_gibberish_domain(domain):
            scam_signals += 1
            reasons.append("⚠️ Verdächtige Random-Domain")
        
        # 6. Clickbait/Scam Patterns im Subject
        for pattern in CLICKBAIT_SCAM_PATTERNS:
            if re.search(pattern, subject_lower, re.IGNORECASE):
                scam_signals += 1
                reasons.append(f"⚠️ Scam-Keyword im Betreff")
                break  # Nur einmal zählen
        
        # 7. Fake-Absendername
        name_issue = TrashAuditService._check_sender_name_mismatch(info.sender_name, info.sender)
        if name_issue:
            scam_signals += 1
            reasons.append(name_issue)
        
        # 8. Typosquatting-Detection (Homoglyphen wie HeIsana statt Helsana)
        typosquat = TrashAuditService._check_typosquatting(info.sender, info.sender_name)
        if typosquat:
            scam_signals += 2  # Sehr starkes Signal - bewusste Täuschung
            reasons.append(typosquat)
        
        return scam_signals, reasons
    
    @staticmethod
    def _check_typosquatting(sender_email: str, sender_name: str) -> Optional[str]:
        """Erkennt Typosquatting mit Homoglyphen (z.B. HeIsana statt Helsana).
        
        Prüft ob Domain oder Absendername eine bekannte Marke imitiert
        durch visuelle Tricks wie I statt l, 0 statt O, rn statt m.
        
        Returns:
            Grund-String wenn Typosquatting erkannt, sonst None
        """
        if not sender_email:
            return None
        
        domain = TrashAuditService._extract_domain(sender_email)
        domain_normalized = normalize_homoglyphs(domain)
        name_normalized = normalize_homoglyphs(sender_name) if sender_name else ""
        
        for brand, valid_domains in TYPOSQUATTING_TARGETS.items():
            # Prüfe ob normalisierte Domain die Marke enthält
            if brand in domain_normalized:
                # Aber die echte Domain ist NICHT in valid_domains
                domain_valid = any(
                    domain == vd or domain.endswith('.' + vd) 
                    for vd in valid_domains
                )
                if not domain_valid:
                    # Check ob es wirklich Typosquatting ist (Original != Normalized)
                    if domain.lower() != domain_normalized:
                        return f"🚨 Typosquatting: '{domain}' imitiert '{brand}'"
            
            # Prüfe auch Absendername
            if brand in name_normalized and name_normalized != sender_name.lower():
                # Name enthält Brand nach Normalisierung, aber Original sieht anders aus
                if brand not in sender_name.lower():
                    return f"🚨 Typosquatting im Namen: imitiert '{brand}'"
        
        return None

    @staticmethod
    def analyze_email(
        info: TrashEmailInfo, 
        db_session=None, 
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        account_domain: Optional[str] = None,
        audit_config: Optional[dict] = None
    ) -> TrashEmailInfo:
        """Analysiert eine einzelne Email und setzt Kategorie.
        
        Args:
            info: TrashEmailInfo mit Metadaten
            db_session: Optionale DB-Session für In-Reply-To Lookups
            user_id: User-ID für DB-Lookups
            account_id: Account-ID für User-Trusted-Senders
            account_domain: Domain des Mail-Accounts (für Auth-Results Trust)
            audit_config: Optionale Audit-Config aus DB (via AuditConfigCache)
            
        Returns:
            TrashEmailInfo mit gesetzter Kategorie und Reasons
        """
        known_newsletters = _get_known_newsletters()
        
        # Lade Audit-Config aus DB falls vorhanden
        if audit_config is None and db_session and user_id:
            audit_config = AuditConfigCache.get_config(db_session, user_id, account_id)
        
        # Fallback auf leere Config
        if audit_config is None:
            audit_config = {
                'trusted_domains': set(),
                'important_keywords': set(),
                'safe_subject_patterns': set(),
                'safe_sender_patterns': set(),
                'vip_senders': set(),
                'vip_pattern_types': {},
            }
        
        score = 0.0  # Positiv = safe (löschbar), Negativ = important (behalten)
        reasons = []
        
        # Dekodiere MIME-Header für Subject und Sender
        subject = decode_mime_header(info.subject) if info.subject else ""
        sender_name = decode_mime_header(info.sender_name) if info.sender_name else ""
        subject_lower = subject.lower()
        sender_lower = info.sender.lower() if info.sender else ""
        sender_domain = TrashAuditService._extract_domain(info.sender) if info.sender else ""
        
        # Aktualisiere die dekodierten Werte im Info-Objekt
        info.subject = subject
        info.sender_name = sender_name
        
        # --- VIP SENDER CHECK (from DB) ---
        vip_match = _match_vip_sender(
            info.sender, 
            audit_config.get('vip_senders', set()),
            audit_config.get('vip_pattern_types', {})
        )
        if vip_match:
            score -= 1.0  # Stark wichtig
            reasons.append(f"⭐ VIP-Absender: {vip_match}")
        
        # --- AUTO-DELETE RULES (from DB) ---
        # Prüft konfigurierte Regeln mit Sender+Subject-Kombination
        auto_delete_match = _match_auto_delete_rule(
            info.sender,
            subject,
            info.date,
            audit_config.get('auto_delete_rules', [])
        )
        
        if auto_delete_match:
            disposition = auto_delete_match['disposition']
            age_ok = auto_delete_match['age_ok']
            desc = auto_delete_match.get('description') or ''
            
            if disposition == 'PROTECTED':
                # PROTECTED übersteuert ALLES - sofort als IMPORTANT markieren
                score -= 2.0
                reasons.append(f"🛡️ Geschützt: {desc}" if desc else "🛡️ Geschützt (Regel)")
                # Setze Kategorie direkt und beende früh
                info.category = TrashCategory.IMPORTANT
                info.reasons = reasons
                info.score = score
                return info
                
            elif disposition == 'JUNK':
                # JUNK = sofort löschbar
                score += 2.0
                reasons.append(f"🗑️ Junk: {desc}" if desc else "🗑️ Junk (Regel)")
                
            elif disposition == 'DELETABLE':
                if age_ok:
                    # Alt genug → löschbar
                    max_age = auto_delete_match.get('max_age_days', 0)
                    score += 1.5
                    reasons.append(f"⏰ Löschbar (>{max_age}d): {desc}" if desc else f"⏰ Löschbar (>{max_age} Tage)")
                else:
                    # Noch nicht alt genug → neutral, aber markieren
                    max_age = auto_delete_match.get('max_age_days', 0)
                    reasons.append(f"⏳ Wird löschbar in {max_age}d: {desc}" if desc else f"⏳ Wird löschbar (nach {max_age} Tagen)")
        
        # --- SOFORT-AUSSCHLUSS VON SCAM-ERKENNUNG ---
        # Diese Fälle können NIEMALS Scam sein
        never_scam = False
        
        # 1. Eigene Absender-Adresse (z.B. eigene Mails in Gelöscht)
        if account_domain and sender_domain == account_domain:
            never_scam = True
        
        # 2. Gesendete Ordner - eigene Mails sind nie Scam
        sent_folder_names = {'sent', 'gesendet', 'gesendete', 'envoyé', 'envoyés', 
                            'inviati', 'sent items', 'sent mail', 'drafts', 'entwürfe'}
        if info.folder and info.folder.lower() in sent_folder_names:
            never_scam = True
        
        # 3. System-Mails (Mailer-Daemon, Postmaster)
        system_senders = {'mailer-daemon', 'postmaster', 'noreply', 'no-reply'}
        sender_local = sender_lower.split('@')[0] if '@' in sender_lower else ''
        if sender_local in system_senders:
            # Mailer-Daemon ist kein Scam, aber auch nicht wichtig
            score += 0.3
            reasons.append("📧 System-Mail")
            never_scam = True
        
        # 4. Schweizer/Deutsche Behörden-Domains (nie Scam)
        gov_tlds = ('.admin.ch', '.ag.ch', '.zh.ch', '.be.ch', '.sg.ch', '.gr.ch',
                   '.lu.ch', '.ti.ch', '.vd.ch', '.vs.ch', '.ne.ch', '.ge.ch', '.ju.ch',
                   '.bund.de', '.bayern.de', '.nrw.de', '.gov.it')
        if any(sender_domain.endswith(tld) for tld in gov_tlds):
            never_scam = True
        
        # --- DB LOOKUP (In-Reply-To) ---
        # Wenn wir auf eine Email antworten, die wir bereits als wichtig eingestuft haben
        if db_session and user_id and info.in_reply_to_msgid:
            try:
                models = _get_models()
                # Suche nach der Original-Mail via Message-ID
                # Wir joinen ProcessedEmail um die Wichtigkeit zu prüfen
                parent_data = (
                    db_session.query(models.ProcessedEmail.wichtigkeit, models.ProcessedEmail.kategorie_aktion)
                    .join(models.RawEmail)
                    .filter(
                        models.RawEmail.user_id == user_id,
                        models.RawEmail.message_id == info.in_reply_to_msgid
                    )
                    .first()
                )
                
                if parent_data:
                    # Wenn die Original-Mail wichtig war (wichtigkeit >= 2 oder Kategorie aktion_erforderlich)
                    if (parent_data.wichtigkeit and parent_data.wichtigkeit >= 2) or \
                       (parent_data.kategorie_aktion == "aktion_erforderlich"):
                        score -= 1.0  # Sehr starkes Signal für IMPORTANT
                        reasons.append("🎯 Antwort auf wichtige Mail (DB-Match)")
                    else:
                        score -= 0.5  # Normale Antwort auf bekannte Mail
                        reasons.append("💬 Antwort auf bekannte Mail (DB-Match)")
            except Exception as e:
                logger.debug(f"DB In-Reply-To lookup failed: {e}")

        # --- SCAM DETECTION ---
        # HINWEIS: Die vollständige Scam-Detection passiert in _calculate_scam_score()
        # am Ende von analyze_email(). Dort werden Brand-Mismatch, Gibberish-Domain,
        # Clickbait-Patterns, Sender-Name-Mismatch etc. geprüft.
        # Hier keine doppelte Prüfung mehr!

        # --- Authentication-Results (SPF/DKIM/DMARC) ---
        # Server hat Vorarbeit geleistet - nutzen wir wenn von trusted Provider
        if info.auth_results:
            auth_lower = info.auth_results.lower()
            
            # Prüfe ob der Header von einem vertrauenswürdigen Provider stammt
            provider_trusted = any(
                provider in auth_lower 
                for provider in TRUSTED_AUTH_PROVIDER_DOMAINS
            )
            
            # NEU: Auch der eigene Account-Domain vertrauen
            if not provider_trusted and account_domain:
                if account_domain in auth_lower:
                    provider_trusted = True
            
            if provider_trusted:
                # Nutze strukturierte Auth-Prüfung
                auth = TrashAuditService._parse_auth_results(info.auth_results)
                
                if auth['is_forged']:
                    score += 1.0  # Auth fehlgeschlagen = verdächtig (Scam-Erkennung separat)
                    # Detaillierte Gründe werden in _calculate_scam_score() hinzugefügt
                    if 'SPF-Fail' not in str(reasons) and 'DKIM-Fail' not in str(reasons):
                        reasons.append("⚠️ Auth fehlgeschlagen (verifiziert)")
                elif auth['spf'] == 'softfail':
                    score += 0.5
                    reasons.append("⚠️ SPF-Softfail (verifiziert)")
                # Pass = vertrauenswürdig, aber kein Bonus für Löschbarkeit
            else:
                # Header nicht von trusted Provider - IGNORIEREN (könnte gefälscht sein)
                logger.debug(f"Auth-Results ignoriert (kein trusted Provider): {info.auth_results[:50]}")
        
        # --- SYSTEM MAIL DETECTION ---
        # Erkennt automatisierte Status-Mails (Backup, Cron, etc.)
        is_system_mail = False
        is_success_status = False
        
        # Prüfe auf System-Sender (root@, cron@, etc.)
        for pattern in SYSTEM_SENDER_PATTERNS:
            if re.search(pattern, sender_lower):
                is_system_mail = True
                break
        
        # Prüfe auf Erfolgs-/Status-Meldung im Betreff
        for pattern in SUCCESS_STATUS_PATTERNS:
            if re.search(pattern, subject_lower):
                is_success_status = True
                break
        
        # Kombination: System-Mail + Erfolgsmeldung = sehr sicher löschbar
        if is_system_mail and is_success_status:
            score += 1.5  # Starkes Signal für SAFE
            reasons.append("🖥️ System-Statusmeldung (erfolgreich)")
        elif is_system_mail:
            score += 0.8  # System-Mail allein
            reasons.append("🖥️ System-Mail")
        elif is_success_status:
            # Erfolgs-Status ohne System-Sender: Alter prüfen
            if info.date:
                age_days = (datetime.now(UTC) - info.date).days if info.date.tzinfo else (datetime.now() - info.date).days
                if age_days > 30:
                    score += 1.2  # Alte Erfolgsmeldung = definitiv safe
                    reasons.append(f"✅ Erfolgsmeldung (vor {age_days} Tagen)")
                else:
                    score += 0.5
                    reasons.append("✅ Erfolgsmeldung")
        
        # --- POWER HEADERS (Server-Vorarbeit nutzen!) ---
        
        # 4. List-Unsubscribe Header = Newsletter (99% zuverlässig!)
        if info.has_list_unsubscribe:
            score += 0.8  # Starker Newsletter-Indikator
            reasons.append("📧 Newsletter (List-Unsubscribe)")
        
        # 5. X-Spam-Score vom Server (SpamAssassin etc.)
        # Konservative Interpretation: Nur bei Score >= 5.0 sicher Spam
        if info.spam_score is not None:
            if info.spam_score >= 5.0:
                score += 1.0  # Server sagt: Spam!
                reasons.append(f"🚫 Server-Spam (Score: {info.spam_score:.1f})")
            elif info.spam_score >= 3.0:
                score += 0.5
                reasons.append(f"⚠️ Spam-verdächtig (Score: {info.spam_score:.1f})")
        
        # 6. In-Reply-To = Echte Konversation (wichtig behalten!)
        if info.is_reply:
            score -= 0.4  # Antworten sind oft wichtig
            reasons.append("💬 Teil einer Konversation")
        
        # --- Check if it's clearly marketing (before trusted domain penalty) ---
        is_marketing = info.has_list_unsubscribe  # List-Unsubscribe = definitiv Marketing
        
        # Marketing Subject Patterns
        for pattern in SAFE_SUBJECT_PATTERNS:
            if re.search(pattern, subject_lower):
                is_marketing = True
                score += 0.6  # Erhöht von 0.4 - Marketing Betreff ist starker Indikator
                reasons.append(f"Marketing-Betreff")
                break
        
        # DB Safe Subject Patterns (zusätzlich zu hardcoded)
        for pattern in audit_config.get('safe_subject_patterns', set()):
            if pattern in subject_lower:
                is_marketing = True
                score += 0.6
                reasons.append(f"Safe-Pattern (DB)")
                break
        
        # Marketing Sender Patterns (mailings@, newsletter@, etc.)
        for pattern in SAFE_SENDER_PATTERNS:
            if re.search(pattern, sender_lower):
                is_marketing = True
                score += 0.6  # Erhöht von 0.5
                reasons.append(f"Marketing-Absender")
                break
        
        # DB Safe Sender Patterns (zusätzlich zu hardcoded)
        for pattern in audit_config.get('safe_sender_patterns', set()):
            if pattern in sender_lower:
                is_marketing = True
                score += 0.6
                reasons.append(f"Safe-Absender (DB)")
                break
        
        # --- TRUSTED DOMAIN CHECK ---
        # 1. Prüfe User-definierte Trusted Senders (aus UI gepflegt)
        is_user_trusted = False
        if db_session and user_id:
            try:
                trusted_senders = _get_trusted_senders()
                user_trust_match = trusted_senders.TrustedSenderManager.is_trusted_sender(
                    db_session, user_id, info.sender, account_id
                )
                if user_trust_match:
                    is_user_trusted = True
                    # User-Trusted ist STARKES Signal für WICHTIG (nicht löschen!)
                    if not is_marketing:
                        score -= 0.5
                        reasons.append(f"✅ User-Whitelist: {user_trust_match.get('label', user_trust_match.get('pattern', ''))}")
            except Exception as e:
                logger.debug(f"User trusted sender lookup failed: {e}")
        
        # 2. Prüfe DB Trusted Domains (neu, zusätzlich zu hardcoded)
        db_trusted_domains = audit_config.get('trusted_domains', set())
        is_db_trusted = sender_domain in db_trusted_domains or any(
            sender_domain.endswith('.' + d) for d in db_trusted_domains
        )
        
        # 3. Prüfe globale Trusted Swiss Domains (hardcoded fallback)
        is_trusted = is_user_trusted or is_db_trusted or TrashAuditService._is_trusted_domain(info.sender)
        if is_trusted and score < 1.0:  # Kein Scam erkannt
            # Trusted + Marketing = sicher löschbar (Newsletter)
            if is_marketing:
                # Trusted Marketing ist sicher löschbar, keine Penalty
                pass
            else:
                # Trusted aber kein Marketing = evtl. wichtig
                score -= 0.3
                if is_db_trusted:
                    reasons.append("Vertrauenswürdig (DB)")
                else:
                    reasons.append("Vertrauenswürdiger Absender")
        
        # --- Newsletter-Detection (vorhandene Logik) ---
        newsletter_conf = known_newsletters.classify_newsletter_confidence(
            info.sender, subject, ""
        )
        if newsletter_conf >= 0.5:
            is_marketing = True
            # Newsletter von trusted = sicher löschbar
            if is_trusted:
                score += newsletter_conf * 0.7  # Erhöht von 0.5
            else:
                score += newsletter_conf
            reasons.append(f"Newsletter ({newsletter_conf:.0%})")
        
        # --- Important Subject Patterns (hardcoded) ---
        for pattern in IMPORTANT_SUBJECT_PATTERNS:
            if re.search(pattern, subject_lower):
                # Bei Scam-Erkennung ignorieren wir "wichtige" Betreffzeilen
                if score < 1.0:  # Kein Scam
                    score -= 0.5
                    reasons.append(f"Wichtiger Betreff")
                break
        
        # --- Important Keywords from DB (multilingual: fattura, bolletta, etc.) ---
        db_keywords = audit_config.get('important_keywords', set())
        for keyword in db_keywords:
            if keyword in subject_lower:
                if score < 1.0:  # Kein Scam
                    score -= 0.5
                    reasons.append(f"Wichtig: '{keyword}'")
                break
        
        # --- Important Sender Patterns ---
        for pattern in IMPORTANT_SENDER_PATTERNS:
            if re.search(pattern, sender_lower):
                # Bei Scam-Erkennung ignorieren wir "wichtige" Absender
                if score < 1.0:  # Kein Scam
                    score -= 0.4
                    reasons.append(f"Wichtiger Absender")
                break
        
        # --- Attachments = möglicherweise wichtig ---
        if info.has_attachments:
            # Bei Scam: Attachments sind gefährlich, also noch mehr löschbar!
            if score >= 1.0:
                score += 0.2
                reasons.append("⚠️ Verdächtiger Anhang")
            else:
                score -= 0.2
                reasons.append("Hat Anhänge")
        
        # --- Alter der Email + Zeitliche Relevanz ---
        if info.date:
            age_days = (datetime.now(UTC) - info.date).days
            
            # Zeitlich abgelaufene Relevanz: Bestimmte Mail-Typen werden mit der Zeit irrelevant
            time_expired_patterns = [
                # Versand/Lieferung (nach 60 Tagen sicher angekommen oder verloren)
                (r'(versendet|versandt|shipped|dispatched|unterwegs|on.?the.?way)', 60),
                (r'(geliefert|zugestellt|delivered|angekommen|arrived)', 30),
                (r'(tracking|sendungsverfolgung|paket.*status)', 60),
                # Aktivierung/Registrierung (nach 30 Tagen ignoriert = unwichtig)
                (r'(aktivier|activate|verify.?your|bestätig.*registr)', 30),
                (r'(willkommen|welcome|getting.?started)', 60),
                # Events (nach dem Datum vorbei)
                (r'(reminder|erinnerung|don.?t.?forget)', 14),
                (r'(webinar|conference|event|termin)', 30),
                # Promotions/Sales (zeitlich begrenzt)
                (r'(nur.?heute|last.?chance|endet.?bald|expires)', 7),
                (r'(rabatt|discount|sale|angebot|offer)', 30),
            ]
            
            for pattern, expire_days in time_expired_patterns:
                if re.search(pattern, subject_lower, re.IGNORECASE):
                    if age_days > expire_days:
                        score += 0.5  # Zeitlich abgelaufen = sicher löschbar
                        reasons.append(f"⏰ Zeitlich abgelaufen ({age_days} Tage alt)")
                        break
            
            # Standard Alter-Bonus
            if age_days < 7:
                score -= 0.1
                reasons.append("Kürzlich gelöscht")
            elif age_days > 365:
                score += 0.3  # Erhöht für sehr alte Mails
                reasons.append("Älter als 1 Jahr")
            elif age_days > 180:
                score += 0.1
                reasons.append("Älter als 6 Monate")
        
        # --- Flagged = wichtig ---
        if info.flags and "\\Flagged" in info.flags:
            score -= 0.5
            reasons.append("War als wichtig markiert")
        
        # --- SCAM DETECTION (finale Prüfung mit kombiniertem Score) ---
        # Übergebe trusted_domains aus DB-Config für bessere Whitelist
        trusted_domains = audit_config.get('trusted_domains', set()) if audit_config else set()
        scam_signals, scam_reasons = TrashAuditService._calculate_scam_score(info, trusted_domains)
        
        # Scam-Signale erhöhen auch den Score (für 2-Signal-Fälle wichtig)
        if scam_signals >= 1 and not never_scam:
            score += scam_signals * 0.5  # Jedes Signal = +0.5 Score
        
        # --- Kategorie bestimmen ---
        # SCAM hat höchste Priorität: 3+ Signale = definitiv bösartig
        # ABER: never_scam überschreibt (eigene Mails, Behörden, System-Mails)
        if scam_signals >= 3 and not never_scam:
            info.category = TrashCategory.SCAM
            info.confidence = min(1.0, scam_signals * 0.25)
            # Ersetze Gründe durch Scam-Gründe (für klare Anzeige)
            info.reasons = scam_reasons
            return info
        
        # 2 Signale + zusätzliche Verdachtsmomente = SCAM
        if scam_signals >= 2 and score >= 1.0 and not never_scam:
            info.category = TrashCategory.SCAM
            info.confidence = min(1.0, 0.6 + scam_signals * 0.15)
            info.reasons = scam_reasons + [r for r in reasons if r not in scam_reasons][:2]
            return info
        
        # Normale Kategorisierung
        if score >= 0.6:  # Balanciert: Newsletter (List-Unsubscribe=0.8) → SAFE
            info.category = TrashCategory.SAFE
            info.confidence = min(1.0, score)
        elif score <= -0.3:
            info.category = TrashCategory.IMPORTANT
            info.confidence = min(1.0, abs(score))
        else:
            info.category = TrashCategory.REVIEW
            info.confidence = 0.5
        
        info.reasons = reasons
        return info
    
    @staticmethod
    def fetch_and_analyze_trash(
        fetcher,
        limit: int = 5000,
        db_session=None,
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        folder: Optional[str] = None
    ) -> TrashAuditResult:
        """Holt Emails aus einem Ordner und analysiert sie.
        
        Args:
            fetcher: Verbundener MailFetcher
            limit: Maximale Anzahl Emails
            db_session: Optionale DB-Session
            user_id: Optionale User-ID
            account_id: Optionale Account-ID für User-Trusted-Senders
            folder: Optionaler Ordnername (default: Trash-Folder)
            
        Returns:
            TrashAuditResult mit kategorisierten Emails
        """
        import time
        start_time = time.time()
        result = TrashAuditResult()
        
        # Account-Domain ermitteln für Auth-Results trust
        # Validierung: Nur extrahieren wenn @ vorhanden
        account_domain = None
        if fetcher.username and '@' in fetcher.username:
            account_domain = TrashAuditService._extract_domain(fetcher.username)
        
        try:
            conn = fetcher.connection
            if not conn:
                logger.error("Keine IMAP-Verbindung")
                return result
            
            # Ordner bestimmen: explizit angegeben oder Trash-Folder suchen
            target_folder = folder
            if not target_folder:
                mail_sync = _get_mail_sync()
                sync = mail_sync.MailSynchronizer(conn, logger)
                target_folder = sync.find_trash_folder()
            
            if not target_folder:
                logger.error("Kein Ordner gefunden")
                return result
            
            logger.info(f"📂 Scanning Folder: {target_folder}")
            
            # Folder auswählen
            folder_info = conn.select_folder(target_folder, readonly=True)
            total_messages = folder_info.get(b'EXISTS', 0)
            logger.info(f"📊 {total_messages} Emails im Ordner")
            
            if total_messages == 0:
                return result
            
            # UIDs holen (neueste zuerst)
            uids = conn.search(['ALL'])
            if limit and len(uids) > limit:
                uids = uids[-limit:]  # Neueste
            
            logger.info(f"📥 Fetching {len(uids)} Email-Header...")
            
            # Header fetchen inkl. Power-Header für bessere Analyse
            # BODY.PEEK vermeidet \Seen Flag zu setzen
            power_headers = 'BODY.PEEK[HEADER.FIELDS (LIST-UNSUBSCRIBE IN-REPLY-TO REFERENCES REPLY-TO X-SPAM-STATUS X-SPAM-SCORE AUTHENTICATION-RESULTS)]'
            
            fetch_data = conn.fetch(uids, [
                'UID',
                'FLAGS', 
                'ENVELOPE',
                'RFC822.SIZE',
                'BODYSTRUCTURE',
                power_headers,
            ])
            
            for uid, data in fetch_data.items():
                try:
                    envelope = data.get(b'ENVELOPE')
                    flags = data.get(b'FLAGS', [])
                    size = data.get(b'RFC822.SIZE', 0)
                    bodystructure = data.get(b'BODYSTRUCTURE')
                    
                    # Envelope parsen
                    subject = ""
                    sender = ""
                    sender_name = ""
                    date = None
                    
                    if envelope:
                        # Subject
                        if envelope.subject:
                            try:
                                subject = envelope.subject.decode('utf-8', errors='replace')
                            except:
                                subject = str(envelope.subject)
                        
                        # From
                        if envelope.from_ and len(envelope.from_) > 0:
                            from_addr = envelope.from_[0]
                            if from_addr.mailbox and from_addr.host:
                                try:
                                    mailbox = from_addr.mailbox.decode('utf-8', errors='replace')
                                    host = from_addr.host.decode('utf-8', errors='replace')
                                    sender = f"{mailbox}@{host}"
                                except:
                                    sender = str(from_addr)
                            if from_addr.name:
                                try:
                                    sender_name = from_addr.name.decode('utf-8', errors='replace')
                                except:
                                    sender_name = str(from_addr.name)
                        
                        # Date
                        if envelope.date:
                            date = envelope.date
                            if date.tzinfo is None:
                                date = date.replace(tzinfo=UTC)
                    
                    # Attachments prüfen und Namen extrahieren
                    has_attachments = False
                    attachment_names = []
                    content_summary = ""
                    if bodystructure:
                        has_attachments, attachment_names, content_summary = TrashAuditService._extract_attachment_info(bodystructure)
                    
                    # Power-Header parsen
                    has_list_unsubscribe = False
                    is_reply = False
                    in_reply_to_msgid = None
                    spam_score = None
                    auth_results = None
                    reply_to = None  # NEU: Für Scam-Detection (From ≠ Reply-To)
                    
                    # Header-Daten aus verschiedenen möglichen Keys extrahieren
                    header_data = None
                    for key in data.keys():
                        if isinstance(key, bytes) and b'HEADER.FIELDS' in key:
                            header_data = data[key]
                            break
                    
                    if header_data:
                        try:
                            header_text = header_data.decode('utf-8', errors='replace') if isinstance(header_data, bytes) else str(header_data)
                            header_lower = header_text.lower()
                            
                            # List-Unsubscribe = Newsletter (99% zuverlässig!)
                            has_list_unsubscribe = 'list-unsubscribe:' in header_lower
                            
                            # In-Reply-To oder References = Teil einer Konversation
                            is_reply = 'in-reply-to:' in header_lower or 'references:' in header_lower
                            
                            # Extrahiere In-Reply-To Message-ID für DB-Lookup
                            # Nutze _extract_folded_header um sicherzugehen dass wir die ganze ID erwischen
                            irt_header = TrashAuditService._extract_folded_header(header_text, 'in-reply-to:')
                            if irt_header:
                                # Extrahiere <id@server> aus dem Header
                                msgid_match = re.search(r'<([^>]+)>', irt_header)
                                if msgid_match:
                                    in_reply_to_msgid = msgid_match.group(1)
                            
                            # Fallback zu References wenn kein In-Reply-To
                            if not in_reply_to_msgid:
                                ref_header = TrashAuditService._extract_folded_header(header_text, 'references:')
                                if ref_header:
                                    # Nimm die LETZTE ID aus References (meist der direkte Vorgänger)
                                    msgids = re.findall(r'<([^>]+)>', ref_header)
                                    if msgids:
                                        in_reply_to_msgid = msgids[-1]

                            # X-Spam-Score parsen
                            if 'x-spam-score:' in header_lower:
                                score_match = re.search(r'x-spam-score:\s*([\d.]+)', header_lower)
                                if score_match:
                                    try:
                                        spam_score = float(score_match.group(1))
                                    except ValueError:
                                        pass
                            
                            # X-Spam-Status parsen (SpamAssassin)
                            if 'x-spam-status:' in header_lower:
                                if 'yes' in header_lower.split('x-spam-status:')[1][:20]:
                                    spam_score = spam_score or 5.0  # Default hoher Score wenn "Yes"
                            
                            # Authentication-Results (SPF/DKIM/DMARC)
                            # WICHTIG: Header können über mehrere Zeilen "gefoldet" sein
                            if 'authentication-results:' in header_lower:
                                auth_results = TrashAuditService._extract_folded_header(
                                    header_text, 'authentication-results:'
                                )
                            
                            # Reply-To Header (für Scam-Detection: From ≠ Reply-To)
                            if 'reply-to:' in header_lower:
                                reply_to_header = TrashAuditService._extract_folded_header(
                                    header_text, 'reply-to:'
                                )
                                if reply_to_header:
                                    # Extrahiere Email-Adresse aus Reply-To
                                    email_match = re.search(r'[\w.\-+]+@[\w.\-]+\.\w+', reply_to_header)
                                    if email_match:
                                        reply_to = email_match.group(0)
                                
                        except Exception as e:
                            logger.debug(f"Header parsing error: {e}")
                    
                    # TrashEmailInfo erstellen
                    email_info = TrashEmailInfo(
                        uid=uid,
                        subject=subject,
                        sender=sender,
                        sender_name=sender_name,
                        date=date,
                        has_attachments=has_attachments,
                        attachment_names=attachment_names,
                        content_summary=content_summary,
                        flags=[f.decode() if isinstance(f, bytes) else str(f) for f in flags],
                        size=size,
                        has_list_unsubscribe=has_list_unsubscribe,
                        is_reply=is_reply,
                        in_reply_to_msgid=in_reply_to_msgid,
                        spam_score=spam_score,
                        auth_results=auth_results,
                        reply_to=reply_to,
                        folder=target_folder,
                    )
                    
                    # Analysieren
                    email_info = TrashAuditService.analyze_email(
                        email_info, 
                        db_session=db_session, 
                        user_id=user_id,
                        account_id=account_id,
                        account_domain=account_domain
                    )
                    result.emails.append(email_info)
                    
                except Exception as e:
                    logger.warning(f"Fehler bei UID {uid}: {e}")
                    continue
            
            # Statistiken
            result.total = len(result.emails)
            result.safe_count = sum(1 for e in result.emails if e.category == TrashCategory.SAFE)
            result.review_count = sum(1 for e in result.emails if e.category == TrashCategory.REVIEW)
            result.important_count = sum(1 for e in result.emails if e.category == TrashCategory.IMPORTANT)
            result.scam_count = sum(1 for e in result.emails if e.category == TrashCategory.SCAM)
            
            # Clustering für bessere Übersicht
            result.clusters = TrashAuditService.build_clusters(result.emails)
            
            result.scan_duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"✅ Trash-Audit: {result.total} Emails analysiert in {result.scan_duration_ms}ms "
                f"(🟢 {result.safe_count} safe, 🟡 {result.review_count} review, 🔴 {result.important_count} important, "
                f"🚨 {result.scam_count} scam, 📦 {len(result.clusters)} Cluster)"
            )
            
        except Exception as e:
            logger.error(f"Trash-Audit Fehler: {type(e).__name__}: {e}")
        
        return result
    
    @staticmethod
    def fetch_and_analyze_all_folders(
        fetcher,
        limit_per_folder: int = 200,
        max_total: int = 10000,
        db_session=None,
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        exclude_folders: Optional[List[str]] = None
    ) -> TrashAuditResult:
        """Scannt ALLE Ordner eines Accounts und analysiert Emails.
        
        Args:
            fetcher: Verbundener MailFetcher
            limit_per_folder: Maximale Anzahl Emails pro Ordner (default 200)
            max_total: Maximale Gesamtzahl Emails über alle Ordner (default 10000)
            db_session: Optionale DB-Session
            user_id: Optionale User-ID
            account_id: Optionale Account-ID für User-Trusted-Senders
            exclude_folders: Ordner die übersprungen werden sollen
            
        Returns:
            TrashAuditResult mit kategorisierten Emails aus allen Ordnern
        """
        import time
        start_time = time.time()
        result = TrashAuditResult()
        
        # Standard-Ausschlüsse
        if exclude_folders is None:
            exclude_folders = []
        
        # Immer ausschließen (System-Ordner die wenig Sinn machen)
        always_exclude = {'[Gmail]', '[Google Mail]'}
        exclude_set = set(exclude_folders) | always_exclude
        
        try:
            conn = fetcher.connection
            if not conn:
                logger.error("Keine IMAP-Verbindung")
                return result
            
            # Alle Ordner auflisten
            folders = conn.list_folders()
            folder_names = []
            
            for flags, delimiter, name in folders:
                # Überspringen wenn:
                # - In Exclude-Liste
                # - Noselect-Flag (virtuelle Ordner)
                if name in exclude_set:
                    continue
                if b'\\Noselect' in flags:
                    continue
                folder_names.append(name)
            
            logger.info(f"📂 Scanne {len(folder_names)} Ordner (max {max_total} Emails total)...")
            
            all_emails = []
            folder_stats = {}
            total_scanned = 0
            
            for folder_name in folder_names:
                # Gesamt-Limit erreicht?
                if total_scanned >= max_total:
                    logger.info(f"⏹️ Gesamt-Limit {max_total} erreicht, stoppe Scan")
                    break
                
                # Wie viele noch scannen?
                remaining = max_total - total_scanned
                folder_limit = min(limit_per_folder, remaining)
                
                try:
                    # Einzelnen Ordner scannen (ohne Clustering, das machen wir am Ende)
                    folder_result = TrashAuditService.fetch_and_analyze_trash(
                        fetcher=fetcher,
                        limit=folder_limit,
                        db_session=db_session,
                        user_id=user_id,
                        account_id=account_id,
                        folder=folder_name
                    )
                    
                    if folder_result.total > 0:
                        all_emails.extend(folder_result.emails)
                        folder_stats[folder_name] = folder_result.total
                        total_scanned += folder_result.total
                        logger.debug(f"  📁 {folder_name}: {folder_result.total} Emails (total: {total_scanned})")
                    
                except Exception as e:
                    logger.warning(f"Fehler bei Ordner '{folder_name}': {e}")
                    continue
            
            # Gesamtergebnis zusammenbauen
            result.emails = all_emails
            result.total = len(all_emails)
            result.safe_count = sum(1 for e in all_emails if e.category == TrashCategory.SAFE)
            result.review_count = sum(1 for e in all_emails if e.category == TrashCategory.REVIEW)
            result.important_count = sum(1 for e in all_emails if e.category == TrashCategory.IMPORTANT)
            result.scam_count = sum(1 for e in all_emails if e.category == TrashCategory.SCAM)
            
            # Clustering über ALLE Emails (nicht pro Ordner!)
            result.clusters = TrashAuditService.build_clusters(all_emails)
            
            result.scan_duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"✅ Alle-Ordner-Audit: {result.total} Emails aus {len(folder_stats)} Ordnern "
                f"in {result.scan_duration_ms}ms "
                f"(🟢 {result.safe_count} safe, 🟡 {result.review_count} review, "
                f"🔴 {result.important_count} important, 🚨 {result.scam_count} scam, "
                f"📦 {len(result.clusters)} Cluster)"
            )
            
        except Exception as e:
            logger.error(f"Alle-Ordner-Audit Fehler: {type(e).__name__}: {e}")
        
        return result
    
    @staticmethod
    def _extract_attachment_info(bodystructure) -> tuple:
        """Extrahiert Attachment-Infos aus BODYSTRUCTURE.
        
        Returns:
            Tuple (has_attachments: bool, attachment_names: List[str], content_summary: str)
        """
        attachment_names = []
        inline_images = 0
        has_html = False
        has_text = False
        
        try:
            def extract_filename(params):
                """Extrahiert Dateiname aus Parameter-Liste."""
                if not params or not isinstance(params, (list, tuple)):
                    return None
                # params ist meist: (b'name', b'filename.pdf', ...)
                params_list = list(params)
                for i, p in enumerate(params_list):
                    if isinstance(p, bytes):
                        p = p.decode('utf-8', errors='replace')
                    if isinstance(p, str) and p.lower() in ('name', 'filename'):
                        if i + 1 < len(params_list):
                            name = params_list[i + 1]
                            if isinstance(name, bytes):
                                name = name.decode('utf-8', errors='replace')
                            return str(name) if name else None
                return None
            
            def check(part):
                nonlocal inline_images, has_html, has_text
                
                if isinstance(part, tuple):
                    # Multipart - rekursiv durchgehen
                    if isinstance(part[0], (list, tuple)):
                        for p in part:
                            if isinstance(p, (list, tuple)):
                                check(p)
                        return
                    
                    # Single part - Typ extrahieren
                    mime_type = part[0] if len(part) > 0 else b''
                    mime_subtype = part[1] if len(part) > 1 else b''
                    if isinstance(mime_type, bytes):
                        mime_type = mime_type.decode('utf-8', errors='replace').lower()
                    if isinstance(mime_subtype, bytes):
                        mime_subtype = mime_subtype.decode('utf-8', errors='replace').lower()
                    
                    # Content-Type tracken
                    if mime_type == 'text':
                        if mime_subtype == 'html':
                            has_html = True
                        elif mime_subtype == 'plain':
                            has_text = True
                    
                    # Disposition prüfen
                    if len(part) > 8:
                        disposition = part[8]
                        if disposition and isinstance(disposition, (list, tuple)):
                            disp_type = disposition[0]
                            if isinstance(disp_type, bytes):
                                disp_type = disp_type.decode('utf-8', errors='replace').lower()
                            
                            if disp_type == 'inline' and mime_type == 'image':
                                inline_images += 1
                            
                            if disp_type == 'attachment':
                                # Versuche Dateiname aus disposition params
                                filename = None
                                if len(disposition) > 1 and disposition[1]:
                                    filename = extract_filename(disposition[1])
                                
                                # Fallback: params (Index 2)
                                if not filename:
                                    params = part[2] if len(part) > 2 else None
                                    filename = extract_filename(params)
                                
                                if filename:
                                    attachment_names.append(filename)
                                else:
                                    # Fallback: Typ/Subtyp als Beschreibung
                                    attachment_names.append(f"({mime_type}/{mime_subtype})")
            
            check(bodystructure)
            
        except Exception:
            pass
        
        # Content-Summary erstellen
        summary_parts = []
        if has_html and has_text:
            summary_parts.append("HTML+Text")
        elif has_html:
            summary_parts.append("HTML")
        elif has_text:
            summary_parts.append("Text")
        
        if inline_images > 0:
            summary_parts.append(f"{inline_images} Bild{'er' if inline_images > 1 else ''}")
        
        content_summary = ", ".join(summary_parts) if summary_parts else ""
        
        return (len(attachment_names) > 0, attachment_names, content_summary)
    
    @staticmethod
    def _has_attachments(bodystructure) -> bool:
        """Prüft ob BODYSTRUCTURE Attachments enthält (Legacy-Wrapper)."""
        has_att, _ = TrashAuditService._extract_attachment_info(bodystructure)
        return has_att
    @staticmethod
    def _extract_folded_header(header_text: str, header_name: str) -> Optional[str]:
        """Extrahiert einen Header inkl. "Folding" (Fortsetzungszeilen).
        
        RFC 5322: Zeilen die mit Whitespace beginnen sind Fortsetzungen.
        
        Args:
            header_text: Vollständiger Header-Block
            header_name: Name des Headers (z.B. 'authentication-results:')
            
        Returns:
            Vollständiger Header-Wert oder None
        """
        try:
            header_lower = header_text.lower()
            start = header_lower.find(header_name.lower())
            if start == -1:
                return None
            
            # Finde das Ende des Headers (nächste Zeile die nicht mit Whitespace beginnt)
            lines = header_text[start:].split('\n')
            result_lines = [lines[0]]  # Erste Zeile (Header-Start)
            
            for line in lines[1:]:
                # Fortsetzungszeile beginnt mit Whitespace (Space oder Tab)
                if line and (line[0] == ' ' or line[0] == '\t'):
                    result_lines.append(line.strip())
                else:
                    # Neuer Header beginnt - Ende erreicht
                    break
            
            return ' '.join(result_lines).strip()
            
        except Exception as e:
            logger.debug(f"Folded header extraction error: {e}")
            return None
    
    @staticmethod
    def delete_safe_emails(
        fetcher,
        uids: List[int],
        folder: Optional[str] = None
    ) -> Tuple[int, int]:
        """Löscht Emails permanent aus einem Ordner.
        
        Args:
            fetcher: Verbundener MailFetcher
            uids: Liste der zu löschenden UIDs
            folder: Optionaler Ordnername (default: Trash-Folder)
            
        Returns:
            Tuple (erfolgreiche, fehlgeschlagene)
        """
        try:
            conn = fetcher.connection
            if not conn:
                return (0, len(uids))
            
            # Ordner bestimmen
            target_folder = folder
            if not target_folder:
                mail_sync = _get_mail_sync()
                sync = mail_sync.MailSynchronizer(conn, logger)
                target_folder = sync.find_trash_folder()
            
            if not target_folder:
                return (0, len(uids))
            
            conn.select_folder(target_folder)
            
            # Bulk delete
            conn.set_flags(uids, ['\\Deleted'])
            conn.expunge()
            
            logger.info(f"🗑️ {len(uids)} Emails aus {target_folder} permanent gelöscht")
            return (len(uids), 0)
            
        except Exception as e:
            logger.error(f"Delete Fehler: {e}")
            return (0, len(uids))
