"""
Folder Audit Service - Analysiert Papierkorb-Emails für sichere Löschung

Verwendet Heuristiken zur Kategorisierung:
- 🟢 SAFE: Newsletter, Spam, Marketing, Scam → sicher löschbar
- 🟡 REVIEW: Unbekannte Absender, ältere Mails → manuell prüfen  
- 🔴 IMPORTANT: Bekannte Kontakte, Rechnungen, etc. → nicht löschen

Kein AI-API-Call nötig - rein lokale Analyse.
"""

import logging
import re
import json
import html as html_lib
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum
import importlib
from email.header import decode_header as mime_decode_header, make_header
from email.utils import decode_params, collapse_rfc2231_value

logger = logging.getLogger(__name__)


def _bytes_to_text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        for enc in ("utf-8", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")
    return str(raw)


def preview_body_to_text(raw, max_chars: int = 4000) -> str:
    """IMAP-Body (HTML oder Text) → sichtbarer Text, gekürzt."""
    text = _bytes_to_text(raw)
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n…"
    return text

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
            'own_domains': set(),
            'important_keywords': set(),
            'safe_subject_patterns': set(),
            'safe_sender_patterns': set(),
            'vip_senders': set(),
            'vip_pattern_types': {},  # pattern -> pattern_type
            'auto_delete_rules': [],  # Liste von Regeln
            'cluster_settings_raw': {},
            'cluster_settings': resolve_effective_cluster_settings({}),
        }
        load_ok = False
        
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

            raw_cluster = _load_cluster_settings_raw(db_session, user_id, account_id)
            config['cluster_settings_raw'] = raw_cluster
            config['cluster_settings'] = resolve_effective_cluster_settings(raw_cluster)

            from src.services.brand_domain_policy import (
                effective_brand_map,
                parse_brand_domains_text,
                validate_brand_map,
            )

            brand_row = (
                db_session.query(models.AuditClusterSettings)
                .filter(
                    models.AuditClusterSettings.user_id == user_id,
                    models.AuditClusterSettings.account_id == None,
                    models.AuditClusterSettings.is_active == True,
                )
                .first()
            )
            custom_brand: dict = {}
            if brand_row and brand_row.brand_official_domains_json:
                try:
                    raw_brand = brand_row.brand_official_domains_json.strip()
                    if raw_brand.startswith("{"):
                        custom_brand, _ = validate_brand_map(json.loads(raw_brand))
                    else:
                        custom_brand = parse_brand_domains_text(raw_brand)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "brand_official_domains_json für user %s ungültig: %s",
                        user_id,
                        exc,
                    )
            config["brand_official_domains_custom"] = custom_brand
            config["brand_official_domains_effective"] = effective_brand_map(custom_brand)
            config["brand_source_url"] = (
                brand_row.brand_source_url if brand_row else None
            )

            if account_id:
                try:
                    acc = (
                        db_session.query(models.MailAccount)
                        .filter(
                            models.MailAccount.id == account_id,
                            models.MailAccount.user_id == user_id,
                        )
                        .first()
                    )
                    raw_own = getattr(acc, "audit_own_domains", None) if acc else None
                    if raw_own:
                        import json

                        parsed = json.loads(raw_own)
                        if isinstance(parsed, list):
                            config["own_domains"] = {
                                str(d).lower().strip()
                                for d in parsed
                                if d and str(d).strip()
                            }
                except Exception as exc:
                    logger.debug("own_domains für Audit nicht ladbar: %s", exc)
            
            logger.debug(f"Loaded audit config for user {user_id}: "
                        f"{len(config['trusted_domains'])} domains, "
                        f"{len(config['important_keywords'])} keywords, "
                        f"{len(config['safe_subject_patterns'])} safe subject patterns, "
                        f"{len(config['safe_sender_patterns'])} safe sender patterns, "
                        f"{len(config['vip_senders'])} VIP senders, "
                        f"{len(config['auto_delete_rules'])} auto-delete rules")
            load_ok = True
            
        except Exception as e:
            logger.error(
                "Audit-Config aus DB nicht ladbar (user_id=%s, account_id=%s): %s",
                user_id,
                account_id,
                e,
                exc_info=True,
            )
            return config
        
        if load_ok:
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
            'disposition': 'SAFE'|'IMPORTANT'|'SCAM'|'REVIEW',
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
            
            # Alter prüfen für SAFE (löschbar nach X Tagen)
            age_ok = True
            if disposition == 'SAFE' and max_age_days is not None and email_date:
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
    """Kategorien für Folder-Audit"""
    SAFE = "safe"           # Sicher löschbar (Newsletter, Spam)
    REVIEW = "review"       # Manuell prüfen
    IMPORTANT = "important" # Möglicherweise wichtig
    SUSPICION = "suspicion" # Marken-/Identitäts-Verdacht (kleiner Topf)
    SCAM = "scam"           # Definitiv bösartig/betrügerisch → sofort vernichten


REVIEW_NON_SUBSTANTIVE_REASONS = frozenset(
    {
        "Kürzlich gelöscht",
        "Älter als 1 Jahr",
        "Älter als 6 Monate",
    }
)

REVIEW_DEFAULT_REASON = "Keine Signale, Absender unbekannt"


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
    attachment_state: str = "no"  # yes | no | unknown — Scan setzt explizit; Guards: unknown wie yes
    
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
    x_mailer: Optional[str] = None           # X-Mailer (z.B. V1P3RBOX = Spam-Tool)
    server_spam_flag: bool = False           # X-Spam-Flag: YES (GMX etc.)
    provider_junk_score: Optional[int] = None  # UI-InboundReport junk:N (GMX)
    is_auto_generated: bool = False          # Auto-Submitted: auto-generated
    to_header: Optional[str] = None          # To: (Undisclosed Recipients etc.)
    
    # Analyse-Ergebnisse
    category: TrashCategory = TrashCategory.REVIEW
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    
    # Clustering
    cluster_key: Optional[str] = None  # Normalisierter Key für Gruppierung
    folder: str = ""                   # Ordner aus dem die Email stammt
    llm_budget_skipped: bool = False   # LLM-Kandidat, noch nicht geprüft
    llm_priority: int = 0              # Ranking für «Rest prüfen»
    llm_unusable: bool = False         # KI antwortete, Antwort verworfen
    llm_skip_reason: Optional[str] = None  # budget | quota | error wenn offen

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "subject": self.subject,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "date": self.date.isoformat() if hasattr(self.date, "isoformat") else (str(self.date) if self.date else None),
            "has_attachments": self.has_attachments,
            "attachment_state": self.attachment_state,
            "attachment_names": self.attachment_names,
            "content_summary": self.content_summary,
            "size": self.size,
            "category": self.category.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "is_reply": self.is_reply,
            "cluster_key": self.cluster_key,
            "folder": self.folder.decode("utf-8", "replace") if isinstance(self.folder, bytes) else (self.folder or ""),
            "reply_to": self.reply_to,
            "auth_results": self.auth_results,
            "x_mailer": self.x_mailer,
            "spam_score": self.spam_score,
            "server_spam_flag": self.server_spam_flag,
            "provider_junk_score": self.provider_junk_score,
            "is_auto_generated": self.is_auto_generated,
            "to_header": self.to_header,
            "has_list_unsubscribe": self.has_list_unsubscribe,
            "llm_budget_skipped": self.llm_budget_skipped,
            "llm_priority": self.llm_priority,
            "llm_unusable": self.llm_unusable,
            "llm_skip_reason": self.llm_skip_reason,
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
    # Ordner+UID (IMAP-UIDs sind nur pro Ordner eindeutig)
    members: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cluster_key": self.cluster_key,
            "display_name": self.display_name,
            "sender_domain": self.sender_domain,
            "count": self.count,
            "category": self.category.value,
            "uids": self.uids,
            "members": self.members,
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
class FolderAuditResult:
    """Gesamtergebnis des Folder-Audits"""
    total: int = 0
    safe_count: int = 0
    review_count: int = 0
    important_count: int = 0
    scam_count: int = 0                     # NEU: Anzahl Scam-Emails
    suspicion_count: int = 0              # Marken-/Identitäts-Verdacht
    emails: List[TrashEmailInfo] = field(default_factory=list)
    clusters: List[TrashEmailCluster] = field(default_factory=list)  # NEU: Cluster-Liste
    scan_duration_ms: int = 0
    llm_skipped_candidates: int = 0
    scan_notice: str = ""
    
    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "safe_count": self.safe_count,
            "review_count": self.review_count,
            "important_count": self.important_count,
            "scam_count": self.scam_count,
            "suspicion_count": self.suspicion_count,
            "scan_duration_ms": self.scan_duration_ms,
            "llm_skipped_candidates": self.llm_skipped_candidates,
            "scan_notice": self.scan_notice,
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
    "gmx.net",           # GMX / GMX.ch
    "gmx.ch",
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


from src.services.brand_domain_policy import (
    BUILTIN_BRAND_OFFICIAL_DOMAINS,
    BUILTIN_BRAND_OFFICIAL_DOMAINS as BRAND_DOMAIN_MAP,
    BRAND_CHECK_WHITELIST_DOMAINS,
    find_brand_domain_mismatch,
    registrable_domain_from_host,
)

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
    z.B. "exAmpleuni" → "exampleuni" → erkennt Typo
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
    k: BUILTIN_BRAND_OFFICIAL_DOMAINS[k]
    for k in (
        "helsana",
        "css",
        "swisscom",
        "postfinance",
        "raiffeisen",
        "migros",
        "coop",
        "serafe",
        "billag",
    )
    if k in BUILTIN_BRAND_OFFICIAL_DOMAINS
}

# Bekannte Spam-Mailer-Software (sofortiges Scam-Signal)
KNOWN_SPAM_MAILER_PATTERNS = [
    r"vip3rbox",
    r"mailer-daemon.*bulk",
    r"phpmailer.*(?:spam|bulk)",
]

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

# Domains, bei denen Absender-/Domain-Sammel-Cluster sinnlos sind (Freemail/Shared).
# Subset von TRUSTED_GLOBAL (keine zweite Domain-Liste im Repo — Hook/PII).
def _default_bulk_merge_block_domains() -> frozenset:
    return frozenset(
        d for d in TRUSTED_GLOBAL_DOMAINS
        if d.startswith("gmx.") or d.split(".", 1)[0] in (
            "gmail", "googlemail", "outlook", "hotmail", "protonmail", "proton", "icloud",
        )
    )


DEFAULT_BULK_MERGE_BLOCK_DOMAINS = _default_bulk_merge_block_domains()

# Referenz für «striktes» Custom-Profil (früher = TRUSTED_GLOBAL in Merge-Stufen)
SUGGESTED_STRICT_BULK_MERGE_BLOCK_DOMAINS = frozenset(TRUSTED_GLOBAL_DOMAINS)

SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS = {
    "multi_reply_prefix": True,
    "read_receipt_prefixes": True,
    "currency_amounts": True,
    "noreply_digit_suffix": True,
}

# Modus-Defaults «Aufräumen» / «Pflege» (überschreibbar pro Account in mode_overrides_json)
CLUSTER_MODE_DEFAULTS = {
    "cleanup": {
        "min_count": 3,
        "absorb_max": 10**9,
        "domain_stage": True,
        "plain_bulk_db_safe_patterns": True,
        "same_sender_volume_merge": True,
        "same_sender_min_count": 5,
        "campaign_review_multidomain": False,
        "campaign_review_min_independent_domains": 3,
    },
    "maintenance": {
        "min_count": 2,
        "absorb_max": 1,
        "domain_stage": False,
        "plain_bulk_db_safe_patterns": True,
        "same_sender_volume_merge": False,
        "same_sender_min_count": 5,
        "campaign_review_multidomain": False,
        "campaign_review_min_independent_domains": 3,
    },
}

CLUSTER_MODE_SETTING_KEYS = tuple(CLUSTER_MODE_DEFAULTS["cleanup"].keys())

# Versand-/Newsletter-Infrastruktur zählt nicht als «unabhängige Domain» bei Kampagnen
CAMPAIGN_INFRA_REGISTRABLE_DOMAINS = frozenset({
    "shopifyemail.com", "ccsend.com", "cmail.com", "mandrillapp.com",
    "sendgrid.net", "mailgun.org", "constantcontact.com", "campaign-archive.com",
    "hubspotemail.net", "exacttarget.com", "createsend.com", "mcsv.net",
})


def get_system_cluster_defaults_for_api() -> dict:
    """System-Defaults für Konfigurations-UI (ohne DB)."""
    return {
        "bulk_merge_block_domains": sorted(DEFAULT_BULK_MERGE_BLOCK_DOMAINS),
        "bulk_merge_block_comma_separated": ", ".join(sorted(DEFAULT_BULK_MERGE_BLOCK_DOMAINS)),
        "strict_bulk_merge_block_comma_separated": ", ".join(
            sorted(SUGGESTED_STRICT_BULK_MERGE_BLOCK_DOMAINS)
        ),
        "normalization": dict(SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS),
        "mode_defaults": {
            mode: dict(vals) for mode, vals in CLUSTER_MODE_DEFAULTS.items()
        },
        "mode_descriptions": {
            "cleanup": (
                "Mehr zusammenfassen: Marken-Newsletter über Domain, viele 🟢-Mails vom gleichen Absender (ab 5), "
                "Mindestgrösse einer Sammel-Karte 3."
            ),
            "maintenance": (
                "Vorsichtig: kleine Gruppen (min. 2), keine Domain-Bündelung, "
                "kein Volumen-Absender ohne Newsletter-Kennzeichen."
            ),
        },
    }


def resolve_mode_cluster_config(mode: str, raw: Optional[dict] = None) -> dict:
    """Effektive Modus-Parameter (Code-Default + gespeicherte Overrides für diesen Modus)."""
    raw = raw or {}
    base = dict(CLUSTER_MODE_DEFAULTS.get(mode, CLUSTER_MODE_DEFAULTS["cleanup"]))
    mode_overrides = raw.get("mode_overrides") or {}
    overrides = mode_overrides.get(mode) or {}
    for key in CLUSTER_MODE_SETTING_KEYS:
        if key in overrides and overrides[key] is not None:
            base[key] = overrides[key]
    base["min_count"] = max(2, int(base.get("min_count", 3)))
    base["absorb_max"] = max(1, int(base.get("absorb_max", 10**9)))
    base["same_sender_min_count"] = max(3, int(base.get("same_sender_min_count", 5)))
    base["campaign_review_min_independent_domains"] = max(
        2, int(base.get("campaign_review_min_independent_domains", 3))
    )
    for bool_key in (
        "domain_stage",
        "plain_bulk_db_safe_patterns",
        "same_sender_volume_merge",
        "campaign_review_multidomain",
    ):
        base[bool_key] = bool(base.get(bool_key))
    return base


def resolve_effective_cluster_settings(raw: Optional[dict] = None) -> dict:
    """Merged DB-Rohdaten mit System-Defaults (Config überschreibt pro Feld)."""
    raw = raw or {}
    if raw.get("use_custom_bulk_merge_block"):
        block = {
            d.lower().strip()
            for d in (raw.get("bulk_merge_block_domains") or [])
            if d and str(d).strip()
        }
    else:
        block = set(DEFAULT_BULK_MERGE_BLOCK_DOMAINS)
    norm = dict(SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS)
    overrides = raw.get("normalization") or {}
    for key in SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS:
        if key in overrides and overrides[key] is not None:
            norm[key] = bool(overrides[key])
    return {
        "bulk_merge_block": block,
        "normalization": norm,
        "mode_overrides": raw.get("mode_overrides") or {},
    }


def _load_cluster_settings_raw(db_session, user_id: int, account_id: Optional[int]) -> dict:
    """Lädt gespeicherte Cluster-Settings (account-spezifisch, sonst global)."""
    if db_session is None or user_id is None:
        return {}
    models = _get_models()
    if not hasattr(models, "AuditClusterSettings"):
        return {}
    try:
        if account_id is not None:
            row = db_session.query(models.AuditClusterSettings).filter(
                models.AuditClusterSettings.user_id == user_id,
                models.AuditClusterSettings.account_id == account_id,
                models.AuditClusterSettings.is_active == True,
            ).first()
            if row:
                return _cluster_settings_row_to_raw(row)
        row = db_session.query(models.AuditClusterSettings).filter(
            models.AuditClusterSettings.user_id == user_id,
            models.AuditClusterSettings.account_id == None,
            models.AuditClusterSettings.is_active == True,
        ).first()
        if row:
            return _cluster_settings_row_to_raw(row)
    except Exception as e:
        logger.debug("Cluster-Settings nicht ladbar: %s", e)
    return {}


def _cluster_settings_row_to_raw(row) -> dict:
    import json
    domains = []
    norm = {}
    try:
        if row.bulk_merge_block_domains:
            domains = json.loads(row.bulk_merge_block_domains)
    except (TypeError, json.JSONDecodeError):
        domains = []
    try:
        if row.normalization_json:
            norm = json.loads(row.normalization_json)
    except (TypeError, json.JSONDecodeError):
        norm = {}
    mode_overrides = {}
    try:
        if getattr(row, "mode_overrides_json", None):
            mode_overrides = json.loads(row.mode_overrides_json)
    except (TypeError, json.JSONDecodeError):
        mode_overrides = {}
    return {
        "use_custom_bulk_merge_block": bool(row.use_custom_bulk_merge_block),
        "bulk_merge_block_domains": domains if isinstance(domains, list) else [],
        "normalization": norm if isinstance(norm, dict) else {},
        "mode_overrides": mode_overrides if isinstance(mode_overrides, dict) else {},
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
    r"@online\.pro$",            # Serafe-Phishing-Kampagne
    r"@.*\.online\.pro$",        # Subdomains davon
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


class FolderAuditService:
    """Service für Folder-Audit Analyse"""
    
    # =============================================================================
    # Subject Normalisierung für Clustering
    # =============================================================================
    
    @staticmethod
    def normalize_subject_for_clustering(
        subject: str,
        normalization: Optional[dict] = None,
    ) -> str:
        """Normalisiert Betreff für Clustering.
        
        Entfernt variable Teile wie Datum, Pfade, IDs, um Muster zu erkennen.
        `normalization` kommt aus Audit-Cluster-Settings (System-Defaults wenn leer).
        """
        opts = normalization or SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS
        if not subject:
            return ""
        
        normalized = subject.lower().strip()
        
        # Entferne Re:/Fwd:/AW:/WG: Präfixe (mehrfach)
        if opts.get("multi_reply_prefix", True):
            prefix_re = re.compile(
                r'^(re:|aw:|fwd:|wg:|fw:|antwort:|reply:)\s*',
                flags=re.IGNORECASE,
            )
            while prefix_re.match(normalized):
                normalized = prefix_re.sub('', normalized, count=1).strip()
        else:
            normalized = re.sub(r'^(re:|aw:|fwd:|wg:|fw:)\s*', '', normalized, flags=re.IGNORECASE)
        
        if opts.get("read_receipt_prefixes", True):
            normalized = re.sub(
                r'^(gelesen|read|letto|lettura|lu)\s*[:]\s*',
                '',
                normalized,
                flags=re.IGNORECASE,
            )
        
        if opts.get("currency_amounts", True):
            normalized = re.sub(
                r'(?<![\w.])(chf|eur|usd|gbp|fr\.?|sfr\.?|€|\$)\s*\d+([.,]\d+)?',
                '<AMOUNT>',
                normalized,
                flags=re.IGNORECASE,
            )
            normalized = re.sub(
                r'\d+([.,]\d+)?\s*(chf|eur|usd|gbp|fr\.?|sfr\.?|€|\$)\b',
                '<AMOUNT>',
                normalized,
                flags=re.IGNORECASE,
            )
        
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
        
        # Dezimalzahlen (Jackpot 26.7 Millionen) - vor den Ganzzahl-Regeln
        normalized = re.sub(r'\b\d+[.,]\d+\b', '<N>', normalized)
        
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
        
        # Dezimalzahlen (Jackpot 26.7 Millionen) und Zahl-Adjektive (5-tägiger Streak)
        normalized = re.sub(r'\b\d+-täg\w*', '<N>-tägig', normalized)
        
        # Führende/nachgestellte Emoji/Sonderzeichen entfernen (nur Dekoration)
        normalized = re.sub(r'^[^\w<#]+', '', normalized)
        normalized = re.sub(r'[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\ufe0f\u200d\s]+$', '', normalized)
        
        # Normalisiere Whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Kürze auf max 80 Zeichen
        if len(normalized) > 80:
            normalized = normalized[:77] + '...'
        
        return normalized
    
    @staticmethod
    def normalize_sender_for_clustering(
        sender_email: str,
        normalization: Optional[dict] = None,
    ) -> str:
        """Normalisiert Absender für Cluster-Keys (optional noreply0 → noreply)."""
        opts = normalization or SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS
        sender_normalized = sender_email.lower().strip() if sender_email else "unknown"
        if not opts.get("noreply_digit_suffix", True) or "@" not in sender_normalized:
            return sender_normalized
        local, _, domain = sender_normalized.partition("@")
        local = re.sub(
            r'^(noreply|no-reply|donotreply|do-not-reply)\d+',
            r'\1',
            local,
            flags=re.IGNORECASE,
        )
        return f"{local}@{domain}"

    @staticmethod
    def _subject_cluster_fingerprint(subject: str) -> str:
        """Kurzer Hash, wenn Normalisierung Betreff zu generisch macht (Anti-Wildwuchs-Cluster)."""
        import hashlib
        raw = (subject or "").strip().lower()[:120]
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:10]

    @staticmethod
    def create_cluster_key(
        sender_email: str,
        subject: str,
        normalization: Optional[dict] = None,
    ) -> str:
        """Erstellt einen Cluster-Key aus Absender-Email + normalisiertem Subject.
        
        WICHTIG: Wir nutzen die vollständige Email-Adresse, NICHT nur die Domain!
        Sonst werden verschiedene Absender derselben Domain fälschlich gruppiert.
        """
        # Normalisiere Email (lowercase)
        sender_normalized = FolderAuditService.normalize_sender_for_clustering(
            sender_email, normalization
        )
        normalized_subject = FolderAuditService.normalize_subject_for_clustering(
            subject, normalization
        )
        generic_tokens = ("", "<HOST>", "<PATH>", "<EMAIL>", "<IP>", "(kein betreff)")
        stripped = normalized_subject.replace("<", "").replace(">", "").strip()
        if len(stripped) < 8 or normalized_subject.lower() in generic_tokens:
            fp = FolderAuditService._subject_cluster_fingerprint(subject)
            normalized_subject = f"{normalized_subject}|fp:{fp}"
        return f"{sender_normalized}|{normalized_subject}"
    
    @staticmethod
    def _sort_emails_newest_first(emails: List[TrashEmailInfo]) -> None:
        """In-place: neueste Mail zuerst (None-Datum ans Ende)."""
        emails.sort(
            key=lambda e: e.date or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    @staticmethod
    def _apply_global_limit(
        emails: List[TrashEmailInfo], max_total: Optional[int]
    ) -> List[TrashEmailInfo]:
        """Behält die neuesten max_total Mails (nach Datum, nicht Scan-Reihenfolge)."""
        if not emails:
            return emails
        FolderAuditService._sort_emails_newest_first(emails)
        if max_total and len(emails) > max_total:
            return emails[:max_total]
        return emails

    @staticmethod
    def build_clusters(
        emails: List[TrashEmailInfo],
        mode: str = "cleanup",
        trusted_domains: Optional[set] = None,
        cluster_settings: Optional[dict] = None,
        audit_config: Optional[dict] = None,
    ) -> List[TrashEmailCluster]:
        """Gruppiert Emails zu Clustern basierend auf Ähnlichkeit.
        
        Returns:
            Liste von TrashEmailCluster, sortiert nach Anzahl (größte zuerst)
        """
        from collections import defaultdict
        
        cluster_map: Dict[str, TrashEmailCluster] = {}
        effective = cluster_settings or resolve_effective_cluster_settings({})
        bulk_block = effective.get("bulk_merge_block") or set(DEFAULT_BULK_MERGE_BLOCK_DOMAINS)
        norm_opts = effective.get("normalization") or SYSTEM_CLUSTER_NORMALIZATION_DEFAULTS
        mode_cfg = resolve_mode_cluster_config(mode, effective)
        audit_config = audit_config or {}
        safe_sender_counts = FolderAuditService._safe_sender_volume_counts(
            emails, mode_cfg, audit_config
        )
        
        for email in emails:
            # Cluster-Key generieren
            key = FolderAuditService.create_cluster_key(
                email.sender, email.subject, norm_opts
            )
            email.cluster_key = key
            
            if key not in cluster_map:
                # Neuen Cluster erstellen
                domain = FolderAuditService._extract_domain(email.sender)
                display_name = FolderAuditService.normalize_subject_for_clustering(
                    email.subject, norm_opts
                )
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
            folder_name = email.folder.decode("utf-8", "replace") if isinstance(email.folder, bytes) else (email.folder or "")
            cluster.members.append({"folder": folder_name, "uid": email.uid})
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
            elif email.category == TrashCategory.SUSPICION:
                cluster.review_count += 1
            
            if email.date:
                if cluster.oldest_date is None or email.date < cluster.oldest_date:
                    cluster.oldest_date = email.date
                if cluster.newest_date is None or email.date > cluster.newest_date:
                    cluster.newest_date = email.date
            
            # Dominante Kategorie: SCAM > Verdacht > IMPORTANT > REVIEW > SAFE
            if cluster.count == 1:
                cluster.category = email.category
            elif cluster.category != email.category:
                priority = {
                    TrashCategory.SCAM: 5,
                    TrashCategory.SUSPICION: 4,
                    TrashCategory.IMPORTANT: 3,
                    TrashCategory.REVIEW: 2,
                    TrashCategory.SAFE: 1,
                }
                if priority.get(email.category, 0) > priority.get(cluster.category, 0):
                    cluster.category = email.category
        
        # Stufe 2-4: Sammel-Cluster (Kampagne, Whitelist-Domain, Absender)
        FolderAuditService._add_campaign_clusters(
            emails, cluster_map, norm_opts, mode_cfg
        )
        merge_ctx = {
            "trusted_domains": trusted_domains,
            "bulk_merge_block": bulk_block,
            "audit_config": audit_config,
            "mode_cfg": mode_cfg,
            "safe_sender_counts": safe_sender_counts,
        }

        def domain_key(e, _td):
            return FolderAuditService._domain_group_key(e, **merge_ctx)

        def sender_key(e, _td):
            return FolderAuditService._sender_group_key(e, **merge_ctx)

        if mode_cfg["domain_stage"]:
            FolderAuditService._merge_clusters(
                emails, cluster_map, domain_key,
                min_count=mode_cfg["min_count"],
                absorb_max=mode_cfg["absorb_max"],
                label="domain", trusted_domains=trusted_domains)
        FolderAuditService._merge_clusters(
            emails, cluster_map, sender_key,
            min_count=mode_cfg["min_count"],
            absorb_max=mode_cfg["absorb_max"],
            label="sender")
        
        # Counts/Members aus finalen cluster_keys der Mails (UID pro Ordner → kein Drift)
        return FolderAuditService._rebuild_clusters_from_emails(emails, cluster_map)
    
    # ------------------------------------------------------------------
    # Sammel-Cluster (Stufe 2-4). Grundsatz: lieber zu wenig als zu viel.
    # ------------------------------------------------------------------
    # Modus-Defaults: CLUSTER_MODE_DEFAULTS (+ resolve_mode_cluster_config)
    CLUSTER_MODES = CLUSTER_MODE_DEFAULTS  # Rückwärtskompatibilität
    SENDER_CLUSTER_BLOCK_REASONS = ('wichtig', 'konversation', 'vertrauenswürdig', 'scam')
    DOMAIN_CLUSTER_BLOCK_REASONS = ('wichtig', 'konversation', 'scam')
    VOLUME_MERGE_BLOCK_REASONS = ('wichtig', 'konversation', 'scam')
    _DOMAIN_STAGE_BLOCK_SUBJECT = (
        r'rechnung|invoice|zahlung|payment|mahnung|vertrag|offerte|passwort|password|'
        r'sicherheit|security|code|konto|account|bestell|order|termin|beleg|quittung|'
        r'guthaben|credit|balance|benachrichtigung.*erhalten'
    )
    _SECOND_LEVEL_TLDS = {'co.uk', 'com.br', 'co.jp', 'com.au', 'co.kr', 'com.co', 'co.nz', 'org.uk'}
    
    @staticmethod
    def _trusted_domains_for(db_session, user_id, account_id) -> set:
        """Whitelist-Domains des Users aus der DB (leer, wenn nicht verfügbar)."""
        if db_session is None or user_id is None:
            return set()
        try:
            cfg = AuditConfigCache.get_config(db_session, user_id, account_id)
            return set(cfg.get('trusted_domains', set())) if cfg else set()
        except Exception as e:  # Clustering darf nie am Config-Load scheitern
            logger.debug("trusted_domains für Clustering nicht ladbar: %s", e)
            return set()
    
    @staticmethod
    def _registrable_domain(sender_email: str) -> str:
        """Hauptdomain via Public Suffix List (tldextract)."""
        host = FolderAuditService._extract_domain(sender_email or "")
        return registrable_domain_from_host(host)
    
    @staticmethod
    def _is_transactional_subject(subject: Optional[str]) -> bool:
        if not subject:
            return False
        return bool(re.search(
            FolderAuditService._DOMAIN_STAGE_BLOCK_SUBJECT,
            subject,
            re.IGNORECASE,
        ))

    @staticmethod
    def _matches_db_safe_patterns(email: 'TrashEmailInfo', audit_config: dict) -> bool:
        subj = (email.subject or "").lower()
        sender = (email.sender or "").lower()
        for pattern in audit_config.get("safe_subject_patterns") or ():
            if pattern and pattern in subj:
                return True
        for pattern in audit_config.get("safe_sender_patterns") or ():
            if pattern and pattern in sender:
                return True
        return False

    @staticmethod
    def _has_marketing_signal(email: 'TrashEmailInfo', audit_config: dict, mode_cfg: dict) -> bool:
        reasons = " | ".join(email.reasons or []).lower()
        if email.has_list_unsubscribe:
            return True
        if "newsletter" in reasons or "marketing" in reasons:
            return True
        if "safe-pattern (db)" in reasons or "safe-absender (db)" in reasons:
            return True
        if "marketing-betreff" in reasons or "marketing-absender" in reasons:
            return True
        if mode_cfg.get("plain_bulk_db_safe_patterns") and FolderAuditService._matches_db_safe_patterns(
            email, audit_config
        ):
            return True
        return False

    @staticmethod
    def _is_plain_bulk(
        email: 'TrashEmailInfo',
        audit_config: Optional[dict] = None,
        mode_cfg: Optional[dict] = None,
        for_domain_stage: bool = False,
    ) -> bool:
        """Harmlose Massenmail für Sammel-Cluster (Newsletter/Marketing-Signale)."""
        audit_config = audit_config or {}
        mode_cfg = mode_cfg or CLUSTER_MODE_DEFAULTS["cleanup"]
        if email.category not in (TrashCategory.SAFE, TrashCategory.REVIEW):
            return False
        if FolderAuditService.attachment_blocks_cluster(email) or email.is_reply or not email.sender:
            return False
        reasons = " | ".join(email.reasons or []).lower()
        block = (
            FolderAuditService.DOMAIN_CLUSTER_BLOCK_REASONS
            if for_domain_stage
            else FolderAuditService.SENDER_CLUSTER_BLOCK_REASONS
        )
        if any(b in reasons for b in block):
            return False
        if FolderAuditService._is_transactional_subject(email.subject):
            return False
        return FolderAuditService._has_marketing_signal(email, audit_config, mode_cfg)

    @staticmethod
    def _eligible_for_same_sender_volume_merge(
        email: 'TrashEmailInfo',
        mode_cfg: dict,
        audit_config: Optional[dict] = None,
    ) -> bool:
        """3B: zählt nur Mails, die auch in die Sammelkarte dürfen."""
        audit_config = audit_config or {}
        if not mode_cfg.get("same_sender_volume_merge"):
            return False
        if email.category != TrashCategory.SAFE:
            return False
        if FolderAuditService.attachment_blocks_cluster(email) or email.is_reply or not email.sender:
            return False
        reasons = " | ".join(email.reasons or []).lower()
        if any(b in reasons for b in FolderAuditService.VOLUME_MERGE_BLOCK_REASONS):
            return False
        if FolderAuditService._is_transactional_subject(email.subject):
            return False
        if FolderAuditService._has_marketing_signal(email, audit_config, mode_cfg):
            return False
        return True

    @staticmethod
    def _safe_sender_volume_counts(
        emails: List[TrashEmailInfo],
        mode_cfg: dict,
        audit_config: Optional[dict] = None,
    ) -> dict:
        """Zähler für 3B: gleicher Absender, nur SAFE, nicht transaktional."""
        from collections import Counter
        if not mode_cfg.get("same_sender_volume_merge"):
            return {}
        counts: Counter = Counter()
        for e in emails:
            if not FolderAuditService._eligible_for_same_sender_volume_merge(
                e, mode_cfg, audit_config
            ):
                continue
            counts[e.sender.lower().strip()] += 1
        return dict(counts)
    
    @staticmethod
    def _audit_config_for(db_session, user_id, account_id) -> dict:
        if db_session is None or user_id is None:
            return {}
        try:
            return AuditConfigCache.get_config(db_session, user_id, account_id) or {}
        except Exception as e:
            logger.debug("audit_config für Clustering nicht ladbar: %s", e)
            return {}

    @staticmethod
    def _cluster_settings_for(db_session, user_id, account_id) -> dict:
        """Effektive Cluster-Settings aus DB (System-Defaults wenn nicht gepflegt)."""
        if db_session is None or user_id is None:
            return resolve_effective_cluster_settings({})
        try:
            cfg = AuditConfigCache.get_config(db_session, user_id, account_id)
            if cfg and cfg.get("cluster_settings"):
                return cfg["cluster_settings"]
        except Exception as e:
            logger.debug("cluster_settings für Clustering nicht ladbar: %s", e)
        return resolve_effective_cluster_settings({})

    @staticmethod
    def _sender_group_key(
        email,
        trusted_domains=None,
        bulk_merge_block=None,
        audit_config=None,
        mode_cfg=None,
        safe_sender_counts=None,
    ):
        audit_config = audit_config or {}
        mode_cfg = mode_cfg or CLUSTER_MODE_DEFAULTS["cleanup"]
        safe_sender_counts = safe_sender_counts or {}
        if FolderAuditService._is_plain_bulk(
            email, audit_config, mode_cfg, for_domain_stage=False
        ):
            sender = email.sender.lower().strip()
            block = bulk_merge_block if bulk_merge_block is not None else DEFAULT_BULK_MERGE_BLOCK_DOMAINS
            if FolderAuditService._registrable_domain(sender) in block:
                return None
            return (sender, email.category)
        if FolderAuditService._eligible_for_same_sender_volume_merge(
            email, mode_cfg, audit_config
        ):
            sender = email.sender.lower().strip()
            min_n = int(mode_cfg.get("same_sender_min_count", 5))
            if safe_sender_counts.get(sender, 0) >= min_n:
                block = bulk_merge_block if bulk_merge_block is not None else DEFAULT_BULK_MERGE_BLOCK_DOMAINS
                if FolderAuditService._registrable_domain(sender) in block:
                    return None
                return (sender, email.category)
        return None
    
    @staticmethod
    def _domain_group_key(
        email,
        trusted_domains=None,
        bulk_merge_block=None,
        audit_config=None,
        mode_cfg=None,
        safe_sender_counts=None,
    ):
        """Nur Whitelist-Domains mit bestandener Authentifizierung."""
        audit_config = audit_config or {}
        mode_cfg = mode_cfg or CLUSTER_MODE_DEFAULTS["cleanup"]
        if not FolderAuditService._is_plain_bulk(
            email, audit_config, mode_cfg, for_domain_stage=True
        ):
            return None
        dom = FolderAuditService._registrable_domain(email.sender)
        block = bulk_merge_block if bulk_merge_block is not None else DEFAULT_BULK_MERGE_BLOCK_DOMAINS
        if dom in block:
            return None
        trusted = set(TRUSTED_SWISS_DOMAINS) | set(trusted_domains or ())
        if dom not in trusted:
            return None
        auth = FolderAuditService._parse_auth_results(email.auth_results)
        if auth['is_forged'] or not (auth['spf'] == 'pass' or auth['dkim'] == 'pass' or auth['dmarc'] == 'pass'):
            return None
        return (dom, email.category)
    
    @staticmethod
    def _new_cluster(key, display_name, sample, domain):
        return TrashEmailCluster(
            cluster_key=key, display_name=display_name, sender_domain=domain,
            sample_subject=sample.subject, sample_sender=sample.sender,
            category=sample.category)
    
    @staticmethod
    def _member_folder(email: "TrashEmailInfo") -> str:
        f = email.folder
        if isinstance(f, bytes):
            return f.decode("utf-8", "replace")
        return f or ""

    @staticmethod
    def _member_id(email: "TrashEmailInfo") -> Tuple[str, int]:
        return (FolderAuditService._member_folder(email), email.uid)

    @staticmethod
    def _rebuild_clusters_from_emails(
        emails: List[TrashEmailInfo],
        cluster_map: Dict[str, TrashEmailCluster],
    ) -> List[TrashEmailCluster]:
        """Cluster-Liste aus finalen E-Mail-Zuordnungen (nach Merge/Kampagnen)."""
        from collections import defaultdict

        groups: Dict[str, List[TrashEmailInfo]] = defaultdict(list)
        for e in emails:
            if e.cluster_key:
                groups[e.cluster_key].append(e)

        rebuilt: List[TrashEmailCluster] = []
        for key, group in groups.items():
            if len(group) < 2:
                continue
            hint = cluster_map.get(key)
            first = group[0]
            domain = FolderAuditService._extract_domain(first.sender)
            display = (
                hint.display_name
                if hint
                else (FolderAuditService.normalize_subject_for_clustering(first.subject) or "(Kein Betreff)")
            )
            c = TrashEmailCluster(
                cluster_key=key,
                display_name=display,
                sender_domain=hint.sender_domain if hint else domain,
                sample_subject=hint.sample_subject if hint else first.subject,
                sample_sender=hint.sample_sender if hint else first.sender,
                category=hint.category if hint else first.category,
            )
            for e in group:
                FolderAuditService._add_email_to_cluster(c, e)
            if hint and ("kampagne" in key or "review-kampagne" in key):
                c.category = hint.category
            rebuilt.append(c)

        return sorted(rebuilt, key=lambda c: c.count, reverse=True)

    @staticmethod
    def _add_email_to_cluster(cluster, email):
        cluster.count += 1
        cluster.uids.append(email.uid)
        folder_name = FolderAuditService._member_folder(email)
        cluster.members.append({"folder": folder_name, "uid": email.uid})
        cluster.total_size += email.size
        if email.category == TrashCategory.SAFE:
            cluster.safe_count += 1
        elif email.category == TrashCategory.REVIEW:
            cluster.review_count += 1
        elif email.category == TrashCategory.IMPORTANT:
            cluster.important_count += 1
        elif email.category == TrashCategory.SCAM:
            cluster.scam_count += 1
        elif email.category == TrashCategory.SUSPICION:
            cluster.review_count += 1
        if email.date:
            if cluster.oldest_date is None or email.date < cluster.oldest_date:
                cluster.oldest_date = email.date
            if cluster.newest_date is None or email.date > cluster.newest_date:
                cluster.newest_date = email.date
        priority = {
            TrashCategory.SCAM: 5,
            TrashCategory.SUSPICION: 4,
            TrashCategory.IMPORTANT: 3,
            TrashCategory.REVIEW: 2,
            TrashCategory.SAFE: 1,
        }
        if priority.get(email.category, 0) > priority.get(cluster.category, 0):
            cluster.category = email.category
    
    @staticmethod
    def _merge_clusters(emails, cluster_map, group_key_fn, min_count, absorb_max,
                        label, trusted_domains=None):
        """Fasst bestehende Cluster zu Sammel-Clustern zusammen.
        
        Ein Cluster ist nur zulässig, wenn ALLE seine Mails denselben (nicht-None)
        Gruppen-Key haben und er höchstens absorb_max Mails hat. Pro Gruppe wird
        ab min_count Mails ein Sammel-Cluster gebildet. Kategorien werden nie gemischt.
        """
        from collections import defaultdict
        members: Dict[str, list] = defaultdict(list)
        for e in emails:
            members[e.cluster_key].append(e)
        
        groups: Dict[tuple, list] = defaultdict(list)
        for ckey, cluster in list(cluster_map.items()):
            if cluster.count > absorb_max or cluster.category == TrashCategory.SCAM:
                continue
            keys = {group_key_fn(e, trusted_domains) for e in members[ckey]}
            if len(keys) != 1 or None in keys:
                continue
            groups[keys.pop()].append(ckey)
        
        for gkey, ckeys in groups.items():
            total = sum(cluster_map[k].count for k in ckeys)
            if total < min_count:
                continue
            if len(ckeys) == 1 and cluster_map[ckeys[0]].count >= 2:
                continue  # bereits sauberer Cluster, nichts zu gewinnen
            first = members[ckeys[0]][0]
            if label == "domain":
                key = f"{gkey[0]}|*domain|{gkey[1].value}"
                name = f"(alle Absender von {gkey[0]})"
            else:
                key = f"{gkey[0]}|*alle-betreffs*|{gkey[1].value}"
                name = "(verschiedene Betreffs – Newsletter/Werbung)"
            cluster = FolderAuditService._new_cluster(
                key, name, first, FolderAuditService._registrable_domain(first.sender))
            for ck in ckeys:
                for e in members[ck]:
                    e.cluster_key = key
                    FolderAuditService._add_email_to_cluster(cluster, e)
                cluster_map.pop(ck, None)
            cluster_map[key] = cluster
    
    @staticmethod
    def _has_brand_scam_signal(reasons_lower: str) -> bool:
        return "scam:" in reasons_lower or "⚠️ scam" in reasons_lower

    @staticmethod
    def _is_campaign_candidate(email, mode_cfg=None) -> bool:
        """Scam/Spam oder (optional) REVIEW mit Brand-Mismatch-Signal."""
        mode_cfg = mode_cfg or {}
        if FolderAuditService.attachment_blocks_cluster(email) or email.is_reply or not email.sender:
            return False
        if email.category == TrashCategory.IMPORTANT:
            return False
        reasons = " | ".join(email.reasons or []).lower()
        if any(b in reasons for b in ("wichtig", "konversation", "vertrauenswürdig")):
            return False
        spam_flagged = bool(
            email.server_spam_flag
            or (email.provider_junk_score or 0) >= 10
            or "server-spam" in reasons
        )
        if email.category == TrashCategory.SCAM or spam_flagged:
            return True
        if mode_cfg.get("campaign_review_multidomain") and email.category == TrashCategory.REVIEW:
            return FolderAuditService._has_brand_scam_signal(reasons)
        return False

    @staticmethod
    def _independent_campaign_domains(emails_in_group: list) -> set:
        return {
            FolderAuditService._registrable_domain(e.sender)
            for e in emails_in_group
            if FolderAuditService._registrable_domain(e.sender)
            not in CAMPAIGN_INFRA_REGISTRABLE_DOMAINS
        }

    @staticmethod
    def _add_campaign_clusters(emails, cluster_map, normalization=None, mode_cfg=None):
        """Spam-/Scam-Kampagnen: gleicher Betreff bzw. Markenname von mehreren
        UNABHÄNGIGEN Absender-Domains (Wegwerf-Domains). Echte Newsletter kommen
        von einer Domain und werden hier nie erfasst."""
        from collections import defaultdict
        mode_cfg = mode_cfg or CLUSTER_MODE_DEFAULTS["cleanup"]
        review_min_dom = int(mode_cfg.get("campaign_review_min_independent_domains", 3))

        cands = [e for e in emails if FolderAuditService._is_campaign_candidate(e, mode_cfg)]
        assigned: Set[Tuple[str, int]] = set()

        def build(groups, prefix, title_fn, min_mails, min_indep_domains, cluster_kind):
            for gkey, group in groups.items():
                group = [e for e in group if FolderAuditService._member_id(e) not in assigned]
                indep = FolderAuditService._independent_campaign_domains(group)
                if len(group) < min_mails or len(indep) < min_indep_domains:
                    continue
                key = f"*{cluster_kind}|{prefix}|{gkey}"
                cluster = FolderAuditService._new_cluster(
                    key, title_fn(group[0]), group[0], "(mehrere Domains)")
                for e in group:
                    e.cluster_key = key
                    assigned.add(FolderAuditService._member_id(e))
                    FolderAuditService._add_email_to_cluster(cluster, e)
                cluster.category = TrashCategory.SCAM if cluster.scam_count else TrashCategory.REVIEW
                cluster_map[key] = cluster
        
        by_subject = defaultdict(list)
        by_subject_review = defaultdict(list)
        for e in cands:
            norm = FolderAuditService.normalize_subject_for_clustering(e.subject, normalization)
            if len(norm) < 15:
                continue
            if e.category == TrashCategory.REVIEW:
                by_subject_review[norm].append(e)
            else:
                by_subject[norm].append(e)
        build(
            by_subject,
            "betreff",
            lambda e: f"🚨 Spam-/Scam-Kampagne: {FolderAuditService.normalize_subject_for_clustering(e.subject, normalization)}",
            2,
            2,
            "kampagne",
        )
        build(
            by_subject_review,
            "betreff",
            lambda e: f"⚠️ Verdächtige Kampagne (Prüfen): {FolderAuditService.normalize_subject_for_clustering(e.subject, normalization)}",
            2,
            review_min_dom,
            "review-kampagne",
        )

        by_brand = defaultdict(list)
        by_brand_review = defaultdict(list)
        for e in cands:
            name = (e.sender_name or "").lower().strip()
            if len(name) < 3:
                continue
            if e.category == TrashCategory.REVIEW:
                by_brand_review[name].append(e)
            else:
                by_brand[name].append(e)
        build(
            by_brand,
            "marke",
            lambda e: f"🚨 Spam-/Scam-Kampagne: «{e.sender_name}» von wechselnden Domains",
            3,
            2,
            "kampagne",
        )
        build(
            by_brand_review,
            "marke",
            lambda e: f"⚠️ Verdächtige Kampagne (Prüfen): «{e.sender_name}» von wechselnden Domains",
            3,
            review_min_dom,
            "review-kampagne",
        )
    
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
    def _check_brand_domain_mismatch(
        sender_name: str,
        sender_email: str,
        trusted_domains: Optional[set] = None,
        label: str = "Absender",
        brand_map=None,
    ) -> Optional[str]:
        if brand_map is None:
            brand_map = BRAND_DOMAIN_MAP
        trusted_set = set(trusted_domains) if trusted_domains else None
        hit = find_brand_domain_mismatch(
            sender_name,
            sender_email,
            brand_map,
            trusted_domains=trusted_set,
            label=label,
        )
        return hit.message if hit else None
    
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
        domain = FolderAuditService._extract_domain(sender_email)
        if FolderAuditService._is_gibberish_domain(domain):
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
        domain = FolderAuditService._extract_domain(sender_email)
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
        if FolderAuditService._is_gibberish_domain(domain):
            return f"⚠️ Fake-Absendername ('{sender_name}' + Random-Domain)"
        
        return None
    
    @staticmethod
    def _is_trusted_domain(sender_email: str) -> bool:
        """Prüft ob Email von vertrauenswürdiger Schweizer Domain kommt."""
        if not sender_email:
            return False
        
        domain = FolderAuditService._extract_domain(sender_email)
        
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
        '.pro',  # Oft für Phishing (z.B. online.pro, serafe-ag.pro)
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
        from_domain = FolderAuditService._extract_domain(sender_email)
        reply_domain = FolderAuditService._extract_domain(reply_to)
        
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
        
        domain = FolderAuditService._extract_domain(sender_email)
        if not domain:
            return None
        
        # Whitelist-Check - bekannte legitime Domains mit verdächtigen TLDs
        for whitelisted in FolderAuditService.SUSPICIOUS_TLD_WHITELIST:
            if domain == whitelisted or domain.endswith('.' + whitelisted):
                return None  # Whitelisted = nicht verdächtig
        
        for tld in FolderAuditService.SUSPICIOUS_TLDS:
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
        elif 'dmarc=none' in auth_lower:
            result['dmarc'] = 'none'
        
        if 'dkim=none' in auth_lower:
            result['dkim'] = result['dkim'] or 'none'
        
        return result
    
    @staticmethod
    def _is_gibberish_local_part(local_part: str) -> bool:
        """Erkennt zufällige Local-Parts wie b55x6zkyrsmt3pda26xo."""
        if not local_part or len(local_part) < 10:
            return False
        
        lp = local_part.lower()
        normal_prefixes = (
            'newsletter', 'noreply', 'no-reply', 'info', 'mail', 'support',
            'service', 'team', 'hello', 'contact', 'admin', 'store', 'bounces',
        )
        if any(lp.startswith(p) or p in lp for p in normal_prefixes):
            return False
        
        letters = ''.join(c for c in lp if c.isalpha())
        digits = sum(1 for c in lp if c.isdigit())
        if len(letters) < 8:
            return False
        
        # Lange alphanumerische Mischung ohne erkennbare Wörter
        if digits >= 2 and len(lp) >= 14:
            vowels = sum(1 for c in letters if c in 'aeiou')
            if vowels == 0 or (vowels > 0 and (len(letters) - vowels) / vowels > 2.0):
                return True
        
        return FolderAuditService._is_gibberish_domain(lp)
    
    @staticmethod
    def _check_known_spam_mailer(x_mailer: Optional[str]) -> Optional[str]:
        if not x_mailer:
            return None
        mailer_lower = x_mailer.lower()
        for pattern in KNOWN_SPAM_MAILER_PATTERNS:
            if re.search(pattern, mailer_lower):
                return f"🚨 Bekannter Spam-Mailer: {x_mailer[:40]}"
        return None
    
    @staticmethod
    def _check_brand_in_text_mismatch(
        text: str,
        sender_email: str,
        trusted_domains: Optional[set] = None,
        label: str = "Absender",
    ) -> Optional[str]:
        """Prüft ob ein Text (Name/Betreff) eine Marke behauptet, die zur Domain nicht passt."""
        if not text or not sender_email:
            return None
        return FolderAuditService._check_brand_domain_mismatch(
            text, sender_email, trusted_domains, label=label
        )
    
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
        reply_to_issue = FolderAuditService._check_reply_to_mismatch(info.sender, info.reply_to)
        if reply_to_issue:
            scam_signals += 1  # Nur 1 Signal (vorher 2) - allein nicht ausreichend für SCAM
            reasons.append(reply_to_issue)
        
        # 2. Auth-Results (SPF/DKIM/DMARC) - strukturiert parsen
        # WICHTIG: DKIM-Fail bei alten Mails ignorieren (Signaturen können nach Jahren ungültig werden)
        auth = FolderAuditService._parse_auth_results(info.auth_results)
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
        tld_issue = FolderAuditService._has_suspicious_tld(info.sender)
        if tld_issue:
            scam_signals += 1
            reasons.append(tld_issue)
        
        # 4. Brand-Domain Mismatch - Absender-Name, Betreff und Reply-To prüfen
        brand_issue = FolderAuditService._check_brand_domain_mismatch(
            info.sender_name, info.sender, trusted_domains, label="Absender"
        )
        if brand_issue:
            scam_signals += 1
            reasons.append(brand_issue)
        elif info.subject:
            subject_brand = FolderAuditService._check_brand_in_text_mismatch(
                info.subject, info.sender, trusted_domains, label="Betreff"
            )
            if subject_brand:
                scam_signals += 1
                reasons.append(subject_brand)
        
        if info.reply_to and info.reply_to.lower() != (info.sender or '').lower():
            reply_brand = FolderAuditService._check_brand_in_text_mismatch(
                info.sender_name or info.subject or '', info.reply_to, trusted_domains, label="Reply-To"
            )
            if reply_brand:
                scam_signals += 1
                reasons.append(reply_brand)
        
        # 5. Gibberish Domain
        domain = FolderAuditService._extract_domain(info.sender)
        if FolderAuditService._is_gibberish_domain(domain):
            scam_signals += 1
            reasons.append("⚠️ Verdächtige Random-Domain")
        
        local_part = info.sender.split('@')[0] if info.sender and '@' in info.sender else ''
        if FolderAuditService._is_gibberish_local_part(local_part):
            scam_signals += 1
            reasons.append("⚠️ Verdächtige Random-Absender-Adresse")
        
        # 6. Clickbait/Scam Patterns im Subject
        for pattern in CLICKBAIT_SCAM_PATTERNS:
            if re.search(pattern, subject_lower, re.IGNORECASE):
                scam_signals += 1
                reasons.append(f"⚠️ Scam-Keyword im Betreff")
                break  # Nur einmal zählen
        
        # 7. Fake-Absendername
        name_issue = FolderAuditService._check_sender_name_mismatch(info.sender_name, info.sender)
        if name_issue:
            scam_signals += 1
            reasons.append(name_issue)
        
        # 8. Typosquatting-Detection (Homoglyphen wie HeIsana statt Helsana)
        typosquat = FolderAuditService._check_typosquatting(info.sender, info.sender_name)
        if typosquat:
            scam_signals += 2  # Sehr starkes Signal - bewusste Täuschung
            reasons.append(typosquat)
        
        # 9. Bekannter Spam-Mailer (z.B. V1P3RBOX)
        mailer_issue = FolderAuditService._check_known_spam_mailer(info.x_mailer)
        if mailer_issue:
            scam_signals += 2
            reasons.append(mailer_issue)
        
        # 10. Server-Spam-Flags (GMX X-Spam-Flag, UI-InboundReport junk:N)
        if info.server_spam_flag:
            scam_signals += 2
            reasons.append("🚫 Provider markiert als Spam (X-Spam-Flag)")
        if info.provider_junk_score is not None and info.provider_junk_score >= 5:
            scam_signals += 2
            reasons.append(f"🚫 Provider Junk-Score: {info.provider_junk_score}")
        elif info.provider_junk_score is not None and info.provider_junk_score >= 2:
            scam_signals += 1
            reasons.append(f"⚠️ Provider Junk-Score: {info.provider_junk_score}")
        
        # 11. DKIM/DMARC fehlen bei behaupteter Marke (kein Fail, aber kein Schutz)
        if auth.get('dkim') == 'none' and auth.get('dmarc') == 'none':
            claimed_brand = FolderAuditService._check_brand_domain_mismatch(
                (info.sender_name or '') + ' ' + (info.subject or ''),
                info.sender or '',
                trusted_domains,
            )
            if claimed_brand:
                scam_signals += 1
                reasons.append("⚠️ Keine DKIM/DMARC-Signatur trotz Marken-Behauptung")
        
        if info.is_auto_generated and scam_signals >= 1:
            scam_signals += 1
            reasons.append("⚠️ Auto-generierte Massenmail")
        
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
        
        domain = FolderAuditService._extract_domain(sender_email)
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
    def trash_info_from_audit_payload(d: dict) -> TrashEmailInfo:
        date_val = None
        date_raw = d.get("date")
        if date_raw:
            try:
                date_val = datetime.fromisoformat(
                    str(date_raw).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                date_val = None
        try:
            category = TrashCategory(d.get("category") or "review")
        except ValueError:
            category = TrashCategory.REVIEW
        info = TrashEmailInfo(
            uid=int(d["uid"]),
            subject=d.get("subject") or "",
            sender=d.get("sender") or "",
            sender_name=d.get("sender_name") or "",
            date=date_val,
            has_attachments=bool(d.get("has_attachments")),
            flags=list(d.get("flags") or []),
            size=int(d.get("size") or 0),
            attachment_state=d.get("attachment_state") or "no",
            attachment_names=list(d.get("attachment_names") or []),
            content_summary=d.get("content_summary") or "",
            has_list_unsubscribe=bool(d.get("has_list_unsubscribe")),
            is_reply=bool(d.get("is_reply")),
            auth_results=d.get("auth_results"),
            reply_to=d.get("reply_to"),
            x_mailer=d.get("x_mailer"),
            spam_score=d.get("spam_score"),
            server_spam_flag=bool(d.get("server_spam_flag")),
            provider_junk_score=d.get("provider_junk_score"),
            is_auto_generated=bool(d.get("is_auto_generated")),
            to_header=d.get("to_header"),
            reasons=list(d.get("reasons") or []),
            folder=d.get("folder") or "",
        )
        info.category = category
        info.confidence = float(d.get("confidence") or 0.0)
        info.llm_budget_skipped = bool(d.get("llm_budget_skipped"))
        info.llm_priority = int(d.get("llm_priority") or 0)
        info.llm_unusable = bool(d.get("llm_unusable"))
        info.llm_skip_reason = d.get("llm_skip_reason")
        return info

    @staticmethod
    def run_llm_continue_for_emails(
        emails: List[TrashEmailInfo],
        *,
        user_id: int,
        llm_cfg,
        db_session,
    ) -> dict:
        """LLM für Scan-Restkandidaten — kleines HTTP-Budget + manuelles Tageslimit."""
        from src.services.audit_scam_detection import (
            AUDIT_SCAM_LLM_CONTINUE_MAX_PER_CALL,
            AUDIT_SCAM_LLM_CONTINUE_TIME_BUDGET_SEC,
            AuditScanContext,
            ScamEvaluation,
            check_manual_llm_quota,
            get_manual_llm_quota_used,
            run_deferred_llm_batch,
        )

        allowed, quota_used = check_manual_llm_quota(user_id)
        if not allowed:
            return {
                "error": "quota_exceeded",
                "quota_used": quota_used,
                "processed": 0,
                "still_skipped": 0,
            }

        pending = [
            (
                info,
                ScamEvaluation(
                    llm_deferred=True, llm_priority=info.llm_priority or 0
                ),
            )
            for info in emails
            if info.llm_budget_skipped
        ]
        if not pending:
            return {"processed": 0, "still_skipped": 0}

        ctx = AuditScanContext(
            llm_budget=AUDIT_SCAM_LLM_CONTINUE_MAX_PER_CALL,
            llm_time_budget_sec=float(AUDIT_SCAM_LLM_CONTINUE_TIME_BUDGET_SEC),
        )
        ctx.pending = pending
        brand_map = None
        if db_session:
            cfg = AuditConfigCache.get_config(db_session, user_id, None)
            brand_map = cfg.get("brand_official_domains_effective")
        pairs = run_deferred_llm_batch(
            ctx,
            cfg=llm_cfg,
            db_session=db_session,
            manual_user_id=user_id,
            brand_map=brand_map,
        )
        for info, scam_eval in pairs:
            FolderAuditService._apply_scam_eval_to_trash_info(info, scam_eval)
            if isinstance(info, TrashEmailInfo):
                info.llm_budget_skipped = False
                info.llm_unusable = bool(scam_eval.llm_unusable)
                info.llm_skip_reason = None
        for meta, partial in ctx.pending:
            if isinstance(meta, TrashEmailInfo):
                meta.llm_budget_skipped = True
                meta.llm_unusable = False
                meta.llm_skip_reason = partial.llm_skip_reason or "budget"
        from src.services.audit_scam_detection import format_llm_pending_notice

        notice = format_llm_pending_notice(ctx.pending, ctx)
        return {
            "processed": len(pairs),
            "still_skipped": len(ctx.pending),
            "quota_used": get_manual_llm_quota_used(user_id),
            "scan_notice": notice,
        }

    @staticmethod
    def _apply_scam_eval_to_trash_info(info: TrashEmailInfo, scam_eval) -> None:
        """Nach Layer-2-LLM Kategorie/Gründe auf TrashEmailInfo anwenden."""
        if scam_eval.llm_unusable:
            note = "Identität (KI): keine verwertbare Antwort"
            if note not in info.reasons:
                info.reasons.append(note)
        if scam_eval.is_scam:
            info.category = TrashCategory.SCAM
            info.confidence = scam_eval.confidence
            info.reasons = list(scam_eval.reasons or [])
            return
        if scam_eval.identity_suspicion:
            info.category = TrashCategory.SUSPICION
            info.confidence = max(info.confidence, 0.75)
            for r in scam_eval.layer1_flags or scam_eval.reasons or []:
                if r not in info.reasons:
                    info.reasons.append(r)
            return
        if scam_eval.needs_review_boost:
            if info.category == TrashCategory.SAFE:
                info.category = TrashCategory.REVIEW
            for r in scam_eval.reasons or []:
                if r not in info.reasons:
                    info.reasons.append(r)

    @staticmethod
    def _finalize_scan_llm_batch(
        result: "FolderAuditResult",
        scan_context,
        llm_cfg,
        db_session,
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        progress_callback=None,
    ) -> None:
        from src.services.audit_scam_detection import (
            format_llm_pending_notice,
            run_deferred_llm_batch,
        )

        if not scan_context or not llm_cfg or not llm_cfg.enabled:
            return
        brand_map = None
        if db_session and user_id:
            cfg = AuditConfigCache.get_config(db_session, user_id, account_id)
            brand_map = cfg.get("brand_official_domains_effective")

        def _llm_progress(meta: dict) -> None:
            if not progress_callback:
                return
            from src.services.audit_scam_llm_config import audit_scam_llm_progress_meta

            progress_callback(
                {
                    **meta,
                    **audit_scam_llm_progress_meta(llm_cfg),
                }
            )

        pairs = run_deferred_llm_batch(
            scan_context,
            cfg=llm_cfg,
            db_session=db_session,
            brand_map=brand_map,
            progress_callback=_llm_progress,
        )
        for info, scam_eval in pairs:
            FolderAuditService._apply_scam_eval_to_trash_info(info, scam_eval)
            if isinstance(info, TrashEmailInfo):
                info.llm_budget_skipped = False
                info.llm_unusable = bool(scam_eval.llm_unusable)
                info.llm_skip_reason = None
        for meta, partial in scan_context.pending:
            if isinstance(meta, TrashEmailInfo):
                meta.llm_budget_skipped = True
                meta.llm_unusable = False
                meta.llm_skip_reason = partial.llm_skip_reason or "budget"
        skipped = len(scan_context.pending)
        result.llm_skipped_candidates = skipped
        if skipped > 0:
            result.scan_notice = format_llm_pending_notice(
                scan_context.pending, scan_context
            )
        else:
            result.scan_notice = ""
        FolderAuditService._apply_audit_scam_scan_notices(
            result, db_session, user_id, account_id
        )

    @staticmethod
    def _format_audit_config_scan_notice(cfg: Optional[dict]) -> str:
        cfg = cfg or {}
        custom = cfg.get("brand_official_domains_custom") or {}
        n_brands = len(custom) if isinstance(custom, dict) else 0
        own = cfg.get("own_domains") or set()
        n_own = len(own)
        return (
            f"Marken-Liste: {n_brands} eigene Einträge, eigene Domains: {n_own}."
        )

    @staticmethod
    def _apply_audit_scam_scan_notices(
        result: FolderAuditResult,
        db_session=None,
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> None:
        from src.services.audit_scam_detection import audit_scam_dbl_scan_notice

        parts: List[str] = []
        if db_session and user_id is not None:
            cfg = AuditConfigCache.get_config(db_session, user_id, account_id)
            parts.append(FolderAuditService._format_audit_config_scan_notice(cfg))
        extra = audit_scam_dbl_scan_notice()
        if extra:
            parts.append(extra)
        merged = " ".join(p for p in parts if p).strip()
        if not merged:
            return
        if result.scan_notice:
            result.scan_notice = f"{merged} {result.scan_notice}"
        else:
            result.scan_notice = merged

    @staticmethod
    def _prepare_audit_scan_context(scan_context, db_session, user_id, account_id) -> None:
        if scan_context is None or not db_session or not user_id:
            return
        AuditConfigCache.clear_cache(user_id)
        if not account_id:
            if getattr(scan_context, "firstname_set", None) is None:
                from src.services.audit_firstnames import get_firstname_set

                scan_context.firstname_set = get_firstname_set(db_session)
            return
        if getattr(scan_context, "known_contact_context", None) is None:
            from src.services.audit_known_contacts import load_known_contact_context

            scan_context.known_contact_context = load_known_contact_context(
                db_session, user_id, account_id
            )
        if getattr(scan_context, "firstname_set", None) is None:
            from src.services.audit_firstnames import get_firstname_set

            scan_context.firstname_set = get_firstname_set(db_session)

    @staticmethod
    def _apply_scan_context_to_email_info(info, scan_context, db_session) -> None:
        if not scan_context:
            return
        ctx = getattr(scan_context, "known_contact_context", None)
        if ctx is not None:
            info.audit_known_context = ctx
        fn = getattr(scan_context, "firstname_set", None)
        if fn is not None:
            info._firstname_set = fn
        elif db_session:
            from src.services.audit_firstnames import get_firstname_set

            scan_context.firstname_set = get_firstname_set(db_session)
            info._firstname_set = scan_context.firstname_set
        info._db_session = db_session

    @staticmethod
    def _harmonize_repeat_marketing_senders(emails: List[TrashEmailInfo]) -> None:
        from collections import defaultdict

        from src.services.audit_identity_helpers import is_curated_inbox_context
        from src.services.audit_safe_delete_veto import safe_delete_veto_reason
        from src.services.audit_scam_detection import (
            _detect_mailer_platform,
            extract_domain,
        )
        from src.services.brand_domain_policy import registrable_domain_from_host

        def _bulk_marketing_evidence(item: TrashEmailInfo) -> bool:
            if item.has_list_unsubscribe:
                return True
            dom = extract_domain(item.sender or "")
            plat = _detect_mailer_platform(dom)
            return bool(dom) and plat not in (dom, "unbekannt", "")

        groups: Dict[str, List[TrashEmailInfo]] = defaultdict(list)
        for e in emails:
            if e.is_reply or e.has_attachments:
                continue
            if e.category not in (
                TrashCategory.SAFE,
                TrashCategory.REVIEW,
            ):
                continue
            dom = extract_domain(e.sender or "")
            reg = registrable_domain_from_host(dom) or dom
            reg = (reg or "").strip().lower()
            if not reg:
                continue
            groups[reg].append(e)

        min_group = 5

        for _reg, items in groups.items():
            if len(items) < min_group:
                continue
            bulk_n = sum(1 for x in items if _bulk_marketing_evidence(x))
            if bulk_n <= len(items) // 2:
                continue
            for x in items:
                if x.category != TrashCategory.REVIEW:
                    continue
                if is_curated_inbox_context(x):
                    continue
                if safe_delete_veto_reason(x, is_marketing=True):
                    continue
                only_default = not x.reasons or all(
                    r in REVIEW_NON_SUBSTANTIVE_REASONS or r == REVIEW_DEFAULT_REASON
                    for r in x.reasons
                )
                if not only_default and not x.has_list_unsubscribe:
                    continue
                if not _bulk_marketing_evidence(x):
                    continue
                x.category = TrashCategory.SAFE
                x.reasons = [
                    "Wiederholter Newsletter-Absender (Domain, einheitlich sicher löschbar)"
                ]

    @staticmethod
    def _ensure_review_reasons(info: TrashEmailInfo) -> None:
        if info.category != TrashCategory.REVIEW:
            return
        substantive = [
            r
            for r in (info.reasons or [])
            if r not in REVIEW_NON_SUBSTANTIVE_REASONS
        ]
        if not substantive:
            info.reasons = [REVIEW_DEFAULT_REASON]

    @staticmethod
    def analyze_email(
        info: TrashEmailInfo, 
        db_session=None, 
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        account_domain: Optional[str] = None,
        account_email: Optional[str] = None,
        audit_config: Optional[dict] = None,
        llm_enabled: bool = False,
        audit_llm_config=None,
        llm_calls_remaining: Optional[List[int]] = None,
        scan_context=None,
    ) -> TrashEmailInfo:
        """Analysiert eine einzelne Email und setzt Kategorie.
        
        Args:
            info: TrashEmailInfo mit Metadaten
            db_session: Optionale DB-Session für In-Reply-To Lookups
            user_id: User-ID für DB-Lookups
            account_id: Account-ID für User-Trusted-Senders
            account_domain: Domain des Mail-Accounts (für Auth-Results Trust)
            audit_config: Optionale Audit-Config aus DB (via AuditConfigCache)
            llm_enabled: Layer-2-LLM wenn User-Konfig aktiv; pro Scan begrenzt (AUDIT_SCAM_LLM_MAX_PER_SCAN)
            audit_llm_config: Aufgelöste AuditScamLlmConfig (User/.env)
            llm_calls_remaining: Mutable Budget [n] für LLM-Aufrufe im Scan
            
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
                'own_domains': set(),
                'important_keywords': set(),
                'safe_subject_patterns': set(),
                'safe_sender_patterns': set(),
                'vip_senders': set(),
                'vip_pattern_types': {},
            }
        
        score = 0.0  # Positiv = safe (löschbar), Negativ = important (behalten)
        reasons = []
        is_user_trusted = False
        is_marketing = False
        
        # Dekodiere MIME-Header für Subject und Sender
        subject = decode_mime_header(info.subject) if info.subject else ""
        sender_name = decode_mime_header(info.sender_name) if info.sender_name else ""
        subject_lower = subject.lower()
        sender_lower = info.sender.lower() if info.sender else ""
        sender_domain = FolderAuditService._extract_domain(info.sender) if info.sender else ""
        
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
            
            if disposition == 'IMPORTANT':
                # IMPORTANT übersteuert ALLES - sofort als IMPORTANT markieren
                score -= 2.0
                reasons.append(f"🛡️ Geschützt: {desc}" if desc else "🛡️ Geschützt (Regel)")
                # Setze Kategorie direkt und beende früh
                info.category = TrashCategory.IMPORTANT
                info.reasons = reasons
                info.score = score
                return info
                
            elif disposition == 'SCAM':
                # SCAM = Betrug/Spam, direkt als SCAM kategorisieren
                score += 2.5
                reasons.append(f"⚠️ Scam/Spam: {desc}" if desc else "⚠️ Scam/Spam (Regel)")
                info.category = TrashCategory.SCAM
                info.reasons = reasons
                info.score = score
                return info
                
            elif disposition == 'REVIEW':
                # REVIEW = manuell prüfen
                reasons.append(f"🔍 Prüfen: {desc}" if desc else "🔍 Manuell prüfen (Regel)")
                info.category = TrashCategory.REVIEW
                info.reasons = reasons
                info.score = score
                return info
                
            elif disposition == 'SAFE':
                if age_ok:
                    # Alt genug → sicher löschbar
                    max_age = auto_delete_match.get('max_age_days', 0)
                    score += 1.5
                    reasons.append(f"⏰ Sicher löschbar (>{max_age}d): {desc}" if desc else f"⏰ Sicher löschbar (>{max_age} Tage)")
                else:
                    # Noch nicht alt genug → neutral, aber markieren
                    max_age = auto_delete_match.get('max_age_days', 0)
                    reasons.append(f"⏳ Löschbar in {max_age}d: {desc}" if desc else f"⏳ Löschbar (nach {max_age} Tagen)")
        
        # --- SOFORT-AUSSCHLUSS VON SCAM-ERKENNUNG ---
        from src.services.audit_scam_detection import should_never_scam

        own_domains = audit_config.get('own_domains', set()) if audit_config else set()
        never_scam = should_never_scam(
            info,
            account_email=account_email,
            own_domains=own_domains,
            folder=info.folder,
        )

        sender_local = sender_lower.split('@')[0] if '@' in sender_lower else ''
        if sender_local in {'mailer-daemon', 'postmaster'}:
            score += 0.3
            reasons.append("📧 System-Mail")
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
                auth = FolderAuditService._parse_auth_results(info.auth_results)
                
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
        is_trusted = is_user_trusted or is_db_trusted or FolderAuditService._is_trusted_domain(info.sender)
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
        
        # --- SCAM DETECTION (Layer 1 Header + optional Layer 2 LLM) ---
        from src.services.audit_scam_detection import evaluate_scam_risk

        FolderAuditService._apply_scan_context_to_email_info(
            info, scan_context, db_session
        )

        skip_identity = bool(
            never_scam
            or info.is_reply
            or is_user_trusted
            or (is_trusted and not is_marketing)
        )
        ctx = getattr(info, "audit_known_context", None)
        if ctx is not None:
            from src.services.audit_known_contacts import is_known_contact_email

            if is_known_contact_email(ctx, info.sender or ""):
                skip_identity = True
        info.skip_identity_rules = skip_identity

        trusted_domains = audit_config.get('trusted_domains', set()) if audit_config else set()
        brand_map = (audit_config or {}).get("brand_official_domains_effective")
        scam_eval = evaluate_scam_risk(
            info,
            trusted_domains=trusted_domains,
            brand_map=brand_map,
            never_scam=never_scam,
            llm_enabled=llm_enabled,
            audit_llm_config=audit_llm_config,
            llm_calls_remaining=llm_calls_remaining,
            defer_llm=bool(scan_context and llm_enabled),
            scan_context=scan_context,
            db_session=db_session,
        )

        if scam_eval.is_scam:
            info.category = TrashCategory.SCAM
            info.confidence = scam_eval.confidence
            info.reasons = scam_eval.reasons or scam_eval.layer1_flags
            return info

        if scam_eval.identity_suspicion and not never_scam:
            info.category = TrashCategory.SUSPICION
            info.confidence = max(0.75, scam_eval.confidence or 0.0)
            merged = list(scam_eval.layer1_flags or scam_eval.reasons or [])
            for r in reasons:
                if r not in merged:
                    merged.append(r)
            info.reasons = merged
            return info

        if scam_eval.llm_deferred:
            info.llm_priority = scam_eval.llm_priority
            info.llm_budget_skipped = True

        if scam_eval.needs_review_boost and not never_scam:
            score += 0.8
            for r in (scam_eval.layer1_flags or scam_eval.reasons or []):
                if r not in reasons:
                    reasons.append(r)
        # Schwache Layer-1-Flags (z.B. GMX junk:2) nicht in die UI kippen.
        
        # --- Kategorie bestimmen ---
        if score >= 0.6:  # Balanciert: Newsletter (List-Unsubscribe=0.8) → SAFE
            info.category = TrashCategory.SAFE
            info.confidence = min(1.0, score)
        elif score <= -0.3:
            info.category = TrashCategory.IMPORTANT
            info.confidence = min(1.0, abs(score))
        else:
            info.category = TrashCategory.REVIEW
            info.confidence = 0.5

        from src.services.audit_safe_delete_veto import safe_delete_veto_reason

        if info.category == TrashCategory.SAFE:
            veto = safe_delete_veto_reason(
                info,
                account_email=account_email,
                own_domains=own_domains,
                is_user_trusted=is_user_trusted,
                is_marketing=is_marketing,
            )
            if veto:
                info.category = TrashCategory.REVIEW
                info.confidence = 0.5
                reasons.append(f"🛡️ Löschschutz: {veto}")
        
        info.reasons = reasons
        FolderAuditService._ensure_review_reasons(info)
        return info
    
    @staticmethod
    def fetch_and_analyze_trash(
        fetcher,
        limit: int = 5000,
        db_session=None,
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        folder: Optional[str] = None,
        cluster_mode: str = "cleanup",
        skip_clustering: bool = False,
        scan_context=None,
        clear_scam_caches: bool = True,
        run_llm_batch_at_end: bool = True,
        progress_callback=None,
        only_uid: Optional[int] = None,
    ) -> FolderAuditResult:
        """Holt Emails aus einem Ordner und analysiert sie.
        
        Args:
            fetcher: Verbundener MailFetcher
            limit: Maximale Anzahl Emails
            db_session: Optionale DB-Session
            user_id: Optionale User-ID
            account_id: Optionale Account-ID für User-Trusted-Senders
            folder: Optionaler Ordnername (default: Trash-Folder)
            
        Returns:
            FolderAuditResult mit kategorisierten Emails
        """
        import time
        from src.services.audit_scam_detection import (
            clear_audit_scam_caches,
            new_audit_scan_context,
        )

        if clear_scam_caches:
            clear_audit_scam_caches()
        if scan_context is None:
            scan_context = new_audit_scan_context()
        FolderAuditService._prepare_audit_scan_context(
            scan_context, db_session, user_id, account_id
        )
        start_time = time.time()
        result = FolderAuditResult()

        llm_cfg = None
        scan_llm_enabled = False
        if db_session and user_id:
            models = importlib.import_module(".02_models", "src")
            user = db_session.query(models.User).filter_by(id=user_id).first()
            if user:
                from src.services.audit_scam_llm_config import resolve_audit_scam_llm_config

                llm_cfg = resolve_audit_scam_llm_config(user)
                if llm_cfg.enabled:
                    scan_llm_enabled = True
        
        # Account-Domain ermitteln für Auth-Results trust
        # Validierung: Nur extrahieren wenn @ vorhanden
        account_domain = None
        account_email = None
        if fetcher.username and '@' in fetcher.username:
            account_email = fetcher.username.strip().lower()
            account_domain = FolderAuditService._extract_domain(fetcher.username)
        
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
            if only_uid is not None:
                uids = [only_uid] if only_uid in uids else []
                if not uids:
                    logger.warning("UID %s nicht in Ordner %s", only_uid, target_folder)
                    return result
            elif limit and len(uids) > limit:
                uids = uids[-limit:]  # Neueste
            
            logger.info(f"📥 Fetching {len(uids)} Email-Header...")
            if progress_callback:
                progress_callback(
                    {
                        "phase": "fetch",
                        "message": f"Header laden: {target_folder}",
                        "folder": target_folder,
                        "total": len(uids),
                        "processed": 0,
                    }
                )
            
            # Header fetchen inkl. Power-Header für bessere Analyse
            # BODY.PEEK vermeidet \Seen Flag zu setzen
            power_headers = (
                'BODY.PEEK[HEADER.FIELDS (LIST-UNSUBSCRIBE IN-REPLY-TO REFERENCES REPLY-TO '
                'TO X-SPAM-STATUS X-SPAM-SCORE X-SPAM-FLAG UI-INBOUNDREPORT X-MAILER '
                'AUTO-SUBMITTED AUTHENTICATION-RESULTS)]'
            )
            
            # BATCH-FETCH: Exchange/O365 hat strenges Rate-Limiting
            # Zu viele UIDs auf einmal → "BAD Command Error"
            BATCH_SIZE = 200  # Konservativ für Exchange
            all_fetch_data = {}
            
            for batch_start in range(0, len(uids), BATCH_SIZE):
                batch_uids = uids[batch_start:batch_start + BATCH_SIZE]
                
                # Rate-Limiting: Pause zwischen Batches (außer beim ersten)
                if batch_start > 0:
                    time.sleep(0.1)  # 100ms
                
                batch_data = conn.fetch(batch_uids, [
                    'UID',
                    'FLAGS', 
                    'ENVELOPE',
                    'RFC822.SIZE',
                    'BODYSTRUCTURE',
                    power_headers,
                ])
                all_fetch_data.update(batch_data)
                
                if batch_start > 0 and (batch_start + BATCH_SIZE) % 1000 == 0:
                    logger.debug(f"  ... {batch_start + len(batch_uids)}/{len(uids)} Header geholt")
            
            _analyzed = 0
            _total_fetch = len(all_fetch_data)
            for uid, data in all_fetch_data.items():
                try:
                    envelope = data.get(b'ENVELOPE')
                    flags = data.get(b'FLAGS', [])
                    size = data.get(b'RFC822.SIZE', 0)
                    bodystructure = data.get(b'BODYSTRUCTURE') or data.get('BODYSTRUCTURE')
                    
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
                    attachment_state, attachment_names, content_summary = (
                        FolderAuditService._extract_attachment_info(bodystructure)
                    )
                    has_attachments = attachment_state == "yes"
                    if bodystructure is None:
                        logger.warning(
                            "Folder-audit UID %s: BODYSTRUCTURE fehlt — attachment_state=unknown",
                            uid,
                        )
                    
                    # Power-Header parsen
                    has_list_unsubscribe = False
                    is_reply = False
                    in_reply_to_msgid = None
                    spam_score = None
                    auth_results = None
                    reply_to = None
                    x_mailer = None
                    server_spam_flag = False
                    provider_junk_score = None
                    is_auto_generated = False
                    to_header = None
                    
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
                            irt_header = FolderAuditService._extract_folded_header(header_text, 'in-reply-to:')
                            if irt_header:
                                # Extrahiere <id@server> aus dem Header
                                msgid_match = re.search(r'<([^>]+)>', irt_header)
                                if msgid_match:
                                    in_reply_to_msgid = msgid_match.group(1)
                            
                            # Fallback zu References wenn kein In-Reply-To
                            if not in_reply_to_msgid:
                                ref_header = FolderAuditService._extract_folded_header(header_text, 'references:')
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
                            
                            # GMX: X-Spam-Flag: YES
                            if 'x-spam-flag:' in header_lower:
                                flag_line = header_lower.split('x-spam-flag:')[1][:20]
                                if 'yes' in flag_line:
                                    server_spam_flag = True
                                    spam_score = spam_score or 6.0
                            
                            # GMX: UI-InboundReport junk:N (0=ok, höher = verdächtiger)
                            if 'ui-inboundreport:' in header_lower:
                                junk_match = re.search(
                                    r'ui-inboundreport:\s*(?:unknown|junk):(\d+)',
                                    header_lower,
                                )
                                if junk_match:
                                    try:
                                        provider_junk_score = int(junk_match.group(1))
                                    except ValueError:
                                        pass
                            
                            # X-Mailer (Spam-Tools wie V1P3RBOX)
                            if 'x-mailer:' in header_lower:
                                mailer_line = FolderAuditService._extract_folded_header(
                                    header_text, 'x-mailer:'
                                )
                                if mailer_line:
                                    x_mailer = mailer_line.strip()[:120]
                            
                            # Auto-Submitted: auto-generated (Massen-Spam)
                            if 'auto-submitted:' in header_lower:
                                auto_line = header_lower.split('auto-submitted:')[1][:40]
                                if 'auto-generated' in auto_line or 'auto-replied' in auto_line:
                                    is_auto_generated = True

                            if 'to:' in header_lower:
                                to_header = FolderAuditService._extract_folded_header(
                                    header_text, 'to:'
                                )
                                if to_header:
                                    to_header = to_header.strip()[:200]
                            
                            # Authentication-Results (SPF/DKIM/DMARC)
                            # WICHTIG: Header können über mehrere Zeilen "gefoldet" sein
                            if 'authentication-results:' in header_lower:
                                auth_results = FolderAuditService._extract_folded_header(
                                    header_text, 'authentication-results:'
                                )
                            
                            # Reply-To Header (für Scam-Detection: From ≠ Reply-To)
                            if 'reply-to:' in header_lower:
                                reply_to_header = FolderAuditService._extract_folded_header(
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
                        attachment_state=attachment_state,
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
                        x_mailer=x_mailer,
                        server_spam_flag=server_spam_flag,
                        provider_junk_score=provider_junk_score,
                        is_auto_generated=is_auto_generated,
                        to_header=to_header,
                        folder=target_folder,
                    )
                    
                    # Analysieren
                    email_info = FolderAuditService.analyze_email(
                        email_info, 
                        db_session=db_session, 
                        user_id=user_id,
                        account_id=account_id,
                        account_domain=account_domain,
                        account_email=account_email,
                        audit_config=FolderAuditService._audit_config_for(
                            db_session, user_id, account_id
                        ),
                        llm_enabled=scan_llm_enabled,
                        audit_llm_config=llm_cfg,
                        scan_context=scan_context if scan_llm_enabled else None,
                    )
                    result.emails.append(email_info)
                    _analyzed += 1
                    if progress_callback and (
                        _analyzed % 25 == 0 or _analyzed == _total_fetch
                    ):
                        progress_callback(
                            {
                                "phase": "analyze",
                                "message": f"Analysiere {target_folder}",
                                "folder": target_folder,
                                "processed": _analyzed,
                                "total": _total_fetch,
                            }
                        )
                    
                except Exception as e:
                    logger.warning(f"Fehler bei UID {uid}: {e}")
                    continue
            
            FolderAuditService._sort_emails_newest_first(result.emails)
            FolderAuditService._harmonize_repeat_marketing_senders(result.emails)

            if run_llm_batch_at_end:
                if progress_callback and scan_llm_enabled:
                    pending_n = len(scan_context.pending) if scan_context else 0
                    from src.services.audit_scam_llm_config import audit_scam_llm_progress_meta

                    progress_callback(
                        {
                            "phase": "llm",
                            "message": "Identitäts-KI (Batch)…",
                            "folder": target_folder,
                            "processed": 0,
                            "total": pending_n,
                            **audit_scam_llm_progress_meta(llm_cfg),
                        }
                    )
                FolderAuditService._finalize_scan_llm_batch(
                    result,
                    scan_context,
                    llm_cfg,
                    db_session,
                    user_id,
                    account_id=account_id,
                    progress_callback=progress_callback,
                )

            result.total = len(result.emails)
            result.safe_count = sum(1 for e in result.emails if e.category == TrashCategory.SAFE)
            result.review_count = sum(1 for e in result.emails if e.category == TrashCategory.REVIEW)
            result.important_count = sum(1 for e in result.emails if e.category == TrashCategory.IMPORTANT)
            result.scam_count = sum(1 for e in result.emails if e.category == TrashCategory.SCAM)
            result.suspicion_count = sum(
                1 for e in result.emails if e.category == TrashCategory.SUSPICION
            )
            
            if not skip_clustering:
                result.clusters = FolderAuditService.build_clusters(
                    result.emails, mode=cluster_mode,
                    trusted_domains=FolderAuditService._trusted_domains_for(
                        db_session, user_id, account_id),
                    cluster_settings=FolderAuditService._cluster_settings_for(
                        db_session, user_id, account_id),
                    audit_config=FolderAuditService._audit_config_for(
                        db_session, user_id, account_id))
            
            result.scan_duration_ms = int((time.time() - start_time) * 1000)
            if not run_llm_batch_at_end:
                FolderAuditService._apply_audit_scam_scan_notices(
                    result, db_session, user_id, account_id
                )
            
            logger.info(
                f"✅ Folder-Audit: {result.total} Emails analysiert in {result.scan_duration_ms}ms "
                f"(🟢 {result.safe_count} safe, 🟡 {result.review_count} review, 🔴 {result.important_count} important, "
                f"🚨 {result.scam_count} scam, 📦 {len(result.clusters)} Cluster)"
            )
            
        except Exception as e:
            error_str = str(e).lower()
            # Connection-Fehler und Server-Fehler nach oben propagieren (für All-Folders-Scan)
            # BAD = Server hat Befehl abgelehnt (oft wegen Rate-Limiting)
            if any(fatal in error_str for fatal in [
                'bye', 'connection closed', 'eof', 'socket error', 
                'abort', 'broken pipe', 'connection reset',
                'bad', 'command error'  # Server-Fehler = Connection meist danach tot
            ]):
                logger.error(f"Folder-Audit Verbindungsfehler: {type(e).__name__}: {e}")
                raise  # Nach oben propagieren!
            else:
                logger.error(f"Folder-Audit Fehler: {type(e).__name__}: {e}")
        
        return result
    
    @staticmethod
    def fetch_and_analyze_all_folders(
        fetcher,
        limit_per_folder: int = 200,
        max_total: int = 10000,
        db_session=None,
        user_id: Optional[int] = None,
        account_id: Optional[int] = None,
        exclude_folders: Optional[List[str]] = None,
        cluster_mode: str = "cleanup",
        progress_callback=None,
    ) -> FolderAuditResult:
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
            FolderAuditResult mit kategorisierten Emails aus allen Ordnern
        """
        import time
        from src.services.audit_scam_detection import (
            clear_audit_scam_caches,
            new_audit_scan_context,
        )

        clear_audit_scam_caches()
        scan_context = new_audit_scan_context()
        FolderAuditService._prepare_audit_scan_context(
            scan_context, db_session, user_id, account_id
        )
        start_time = time.time()
        result = FolderAuditResult()
        
        llm_cfg = None
        if db_session and user_id:
            models = importlib.import_module(".02_models", "src")
            user = db_session.query(models.User).filter_by(id=user_id).first()
            if user:
                from src.services.audit_scam_llm_config import resolve_audit_scam_llm_config

                llm_cfg = resolve_audit_scam_llm_config(user)
        if exclude_folders is None:
            exclude_folders = []
        
        # Immer ausschließen (System-Ordner und nicht-Mail-Ordner)
        always_exclude = {
            # Gmail/Google System-Ordner
            '[Gmail]', '[Google Mail]',
            # Exchange/Outlook nicht-Mail-Ordner (enthalten keine Emails)
            'Calendar', 'Kalender', 'Calendrier', 'Calendario',
            'Contacts', 'Kontakte', 'Adressbuch',
            'Tasks', 'Aufgaben', 'Tâches',
            'Notes', 'Notizen',
            'Journal',
            'Sync Issues', 'Synchronisierungsprobleme',
            'Conversation History', 'Unterhaltungsverlauf',
            'RSS Feeds', 'RSS-Feeds',
            'Outbox', 'Postausgang',  # Wird selten gebraucht
        }
        from src.services.audit_safe_delete_veto import is_sent_or_drafts_folder

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
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                # Überspringen wenn:
                # - In Exclude-Liste (exakter Match)
                # - Noselect-Flag (virtuelle Ordner)
                # - Beginnt mit excluded Präfix (z.B. Kalender/...)
                if name in exclude_set:
                    continue
                if is_sent_or_drafts_folder(name):
                    continue
                if b'\\Noselect' in flags:
                    continue
                
                # Präfix-Check für Unterordner von nicht-Mail-Ordnern
                skip_folder = False
                for excluded in always_exclude:
                    if name.startswith(excluded + '/'):
                        skip_folder = True
                        break
                if skip_folder:
                    continue
                
                folder_names.append(name)
            
            logger.info(f"📂 Scanne {len(folder_names)} Ordner (max {max_total} Emails total)...")
            
            all_emails = []
            folder_stats = {}
            
            folders_processed = 0
            for folder_name in folder_names:
                if max_total and len(all_emails) >= max_total:
                    logger.info(
                        "Globales Limit %s erreicht — restliche Ordner übersprungen",
                        max_total,
                    )
                    break
                # Rate-Limiting: Kurze Pause zwischen Ordnern (Exchange/O365 sind streng)
                # Erste 3 Ordner ohne Pause, danach 100ms pro Ordner
                if folders_processed >= 3:
                    time.sleep(0.1)  # 100ms Pause
                folders_processed += 1
                
                if progress_callback:
                    progress_callback(
                        {
                            "phase": "folder",
                            "message": f"Ordner {folder_name}",
                            "folder": folder_name,
                            "folder_index": folders_processed,
                            "folder_count": len(folder_names),
                            "processed": len(all_emails),
                            "total": max_total,
                        }
                    )
                
                remaining = max_total - len(all_emails) if max_total else limit_per_folder
                folder_limit = min(limit_per_folder, remaining) if max_total else limit_per_folder
                if max_total and folder_limit <= 0:
                    break
                
                try:
                    folder_result = FolderAuditService.fetch_and_analyze_trash(
                        fetcher=fetcher,
                        limit=folder_limit,
                        db_session=db_session,
                        user_id=user_id,
                        account_id=account_id,
                        folder=folder_name,
                        skip_clustering=True,
                        scan_context=scan_context,
                        clear_scam_caches=False,
                        run_llm_batch_at_end=False,
                        progress_callback=progress_callback,
                    )
                    
                    if folder_result.total > 0:
                        all_emails.extend(folder_result.emails)
                        folder_stats[folder_name] = folder_result.total
                        logger.debug(
                            f"  📁 {folder_name}: {folder_result.total} Emails "
                            f"(Kandidaten gesamt: {len(all_emails)})"
                        )
                    
                except Exception as e:
                    error_str = str(e).lower()
                    # Fatale Connection-Fehler: Sofort abbrechen!
                    # BAD = Server hat Befehl abgelehnt (Rate-Limiting), Connection danach meist tot
                    if any(fatal in error_str for fatal in [
                        'bye', 'connection closed', 'eof', 'socket error', 
                        'abort', 'broken pipe', 'connection reset',
                        'bad', 'command error'  # Server-Fehler
                    ]):
                        logger.error(f"❌ Verbindung verloren bei '{folder_name}': {e}")
                        logger.warning(f"⏹️ Scan abgebrochen nach {folders_processed} Ordnern (Connection lost)")
                        break  # Schleife verlassen, nicht continue!
                    else:
                        # Nicht-fataler Fehler: Ordner überspringen
                        logger.warning(f"⚠️ Ordner '{folder_name}' übersprungen: {e}")
                        continue
            
            # Neueste max_total über alle Ordner (nicht: erste N Ordner in LIST-Reihenfolge)
            if max_total and len(all_emails) > max_total:
                logger.info(
                    f"📊 {len(all_emails)} Kandidaten → behalte neueste {max_total} nach Datum"
                )
            all_emails = FolderAuditService._apply_global_limit(all_emails, max_total)

            result.emails = all_emails
            if progress_callback:
                pending_n = len(scan_context.pending) if scan_context else 0
                from src.services.audit_scam_llm_config import audit_scam_llm_progress_meta

                progress_callback(
                    {
                        "phase": "llm",
                        "message": "Identitäts-KI (Batch)…",
                        "processed": 0,
                        "total": pending_n,
                        **audit_scam_llm_progress_meta(llm_cfg),
                    }
                )
            FolderAuditService._finalize_scan_llm_batch(
                result,
                scan_context,
                llm_cfg,
                db_session,
                user_id,
                account_id=account_id,
                progress_callback=progress_callback,
            )

            FolderAuditService._harmonize_repeat_marketing_senders(result.emails)

            result.total = len(result.emails)
            result.safe_count = sum(1 for e in result.emails if e.category == TrashCategory.SAFE)
            result.review_count = sum(1 for e in result.emails if e.category == TrashCategory.REVIEW)
            result.important_count = sum(1 for e in result.emails if e.category == TrashCategory.IMPORTANT)
            result.scam_count = sum(1 for e in result.emails if e.category == TrashCategory.SCAM)
            result.suspicion_count = sum(
                1 for e in result.emails if e.category == TrashCategory.SUSPICION
            )
            
            # Clustering über ALLE Emails (nicht pro Ordner!)
            try:
                result.clusters = FolderAuditService.build_clusters(
                    all_emails, mode=cluster_mode,
                    trusted_domains=FolderAuditService._trusted_domains_for(
                        db_session, user_id, account_id),
                    cluster_settings=FolderAuditService._cluster_settings_for(
                        db_session, user_id, account_id),
                    audit_config=FolderAuditService._audit_config_for(
                        db_session, user_id, account_id))
            except Exception:
                logger.exception("build_clusters fehlgeschlagen (Alle-Ordner-Audit)")
                result.clusters = []
            
            result.scan_duration_ms = int((time.time() - start_time) * 1000)
            
            multi_clusters = sum(1 for c in result.clusters if c.count >= 2)
            logger.info(
                f"✅ Alle-Ordner-Audit: {result.total} Emails aus {len(folder_stats)} Ordnern "
                f"in {result.scan_duration_ms}ms "
                f"(🟢 {result.safe_count} safe, 🟡 {result.review_count} review, "
                f"🔴 {result.important_count} important, 🚨 {result.scam_count} scam, "
                f"📦 {len(result.clusters)} Cluster-Karten, {multi_clusters} mit 2+ Mails)"
            )
            
        except Exception as e:
            logger.error(f"Alle-Ordner-Audit Fehler: {type(e).__name__}: {e}")
        
        return result
    
    _MULTIPART_SUBTYPES = frozenset({
        'alternative', 'mixed', 'related', 'report', 'signed', 'encrypted', 'parallel',
        'digest', 'byteranges', 'form-data', 'x-mixed-replace',
    })
    _SIGNATURE_MIME_SUBTYPES = frozenset({
        'pkcs7-signature', 'pgp-signature', 'pgp-keys', 'x-pkcs7-signature',
    })

    @staticmethod
    def attachment_blocks_cluster(info) -> bool:
        """Cluster-Guards: echte Anhänge und unbekannte Struktur konservativ ausschliessen."""
        state = getattr(info, 'attachment_state', None)
        if state in ('yes', 'unknown'):
            return True
        if state == 'no':
            return False
        return bool(getattr(info, 'has_attachments', False))

    @staticmethod
    def _decode_imap_atom(value) -> str:
        if value is None:
            return ''
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='replace')
        return str(value)

    @staticmethod
    def _display_filename(raw) -> str:
        text = FolderAuditService._decode_imap_atom(raw).strip()
        if not text:
            return ''
        try:
            parts = mime_decode_header(text)
            return str(make_header(parts)).strip()
        except Exception:
            return text

    @staticmethod
    def _imap_param_pairs(params) -> List[Tuple[str, str]]:
        if not params or not isinstance(params, (list, tuple)):
            return []
        flat: List = []
        for item in params:
            if isinstance(item, (list, tuple)) and len(item) >= 2 and not isinstance(item[0], (list, tuple)):
                flat.extend(item)
            elif isinstance(item, (list, tuple)):
                flat.extend(item)
            else:
                flat.append(item)
        pairs: List[Tuple[str, str]] = []
        i = 0
        while i + 1 < len(flat):
            key = FolderAuditService._decode_imap_atom(flat[i])
            val = flat[i + 1]
            if isinstance(val, bytes):
                val_str = val.decode('latin-1', errors='replace')
            else:
                val_str = str(val)
            pairs.append((key, val_str))
            i += 2
        return pairs

    @staticmethod
    def _decode_rfc2231_filename_value(val) -> str:
        if val is None:
            return ''
        if isinstance(val, bytes):
            text = val.decode('latin-1', errors='replace')
        else:
            text = str(val).strip()
        if not text:
            return ''
        if "''" not in text:
            return text
        from urllib.parse import unquote
        charset, _, payload = text.partition("''")
        enc = (charset or 'utf-8').strip().lower() or 'utf-8'
        if enc in ('ascii', 'us-ascii'):
            enc = 'utf-8'
        try:
            return unquote(payload, encoding=enc, errors='replace')
        except LookupError:
            return unquote(payload, encoding='utf-8', errors='replace')

    @staticmethod
    def _filename_from_imap_params(params) -> Optional[str]:
        pairs = FolderAuditService._imap_param_pairs(params)
        if not pairs:
            return None
        star_parts: List[str] = []
        for key, val in pairs:
            kl = FolderAuditService._decode_imap_atom(key).lower()
            if kl.endswith('*'):
                star_parts.append(val)
        try:
            decoded = decode_params(pairs)
        except Exception:
            decoded = pairs
        chosen = None
        for key, val in decoded:
            kl = key.lower()
            if kl.endswith('*'):
                continue
            if kl in ('name', 'filename') and val and not chosen:
                chosen = val
        if star_parts:
            merged = star_parts[0] if len(star_parts) == 1 else ''.join(star_parts)
            chosen = merged
        if chosen:
            chosen = FolderAuditService._decode_rfc2231_filename_value(chosen)
            return FolderAuditService._display_filename(chosen)
        return None

    @staticmethod
    def _find_imap_disposition(part) -> Tuple[Optional[str], Optional[tuple]]:
        if not isinstance(part, (list, tuple)):
            return None, None
        for idx in range(2, len(part)):
            disp = part[idx]
            if not isinstance(disp, (list, tuple)) or not disp:
                continue
            label = FolderAuditService._decode_imap_atom(disp[0]).lower()
            if label in ('attachment', 'inline'):
                return label, disp
        return None, None

    @staticmethod
    def _content_id_from_part(part) -> str:
        if not isinstance(part, (list, tuple)) or len(part) < 4:
            return ''
        cid = FolderAuditService._decode_imap_atom(part[3]).strip()
        return cid.strip('<>').strip()

    @staticmethod
    def _parse_multipart_node(node) -> Optional[Tuple[str, List]]:
        """IMAPClient: ([parts…], subtype, …) — RFC-String-Parser: (part…) subtype am Ende."""
        if not isinstance(node, (list, tuple)) or len(node) < 2:
            return None

        if isinstance(node[0], (list, tuple)) and len(node[0]) > 0:
            bucket = node[0]
            if isinstance(bucket[0], (list, tuple)):
                subtype = FolderAuditService._decode_imap_atom(node[1]).lower()
                if subtype in FolderAuditService._MULTIPART_SUBTYPES or (
                    subtype and len(subtype) < 40 and '/' not in subtype
                ):
                    return subtype, list(bucket)

        if isinstance(node[0], (list, tuple)) and isinstance(node[0][0], (bytes, str)):
            subtype = FolderAuditService._decode_imap_atom(node[-1]).lower()
            if subtype in FolderAuditService._MULTIPART_SUBTYPES or (
                subtype and len(subtype) < 40 and '/' not in subtype
            ):
                children = [node[i] for i in range(len(node) - 1)]
                return subtype, children

        return None

    @staticmethod
    def _multipart_subtype(node) -> str:
        parsed = FolderAuditService._parse_multipart_node(node)
        return parsed[0] if parsed else ''

    @staticmethod
    def _bodystructure_is_multipart(node) -> bool:
        return FolderAuditService._parse_multipart_node(node) is not None

    @staticmethod
    def _is_signature_part(mime_type: str, mime_subtype: str) -> bool:
        if mime_type == 'application' and mime_subtype in FolderAuditService._SIGNATURE_MIME_SUBTYPES:
            return True
        if mime_type == 'application' and 'pkcs7' in mime_subtype:
            return True
        return False

    @staticmethod
    def _extract_attachment_info(bodystructure) -> tuple:
        """Attachment-Erkennung aus IMAP BODYSTRUCTURE.

        Returns:
            (attachment_state, attachment_names, content_summary)
            attachment_state: yes | no | unknown
        """
        if bodystructure is None:
            return ('unknown', [], '')

        attachment_names: List[str] = []
        inline_images = 0
        has_html = False
        has_text = False

        def analyze_leaf(part, in_related: bool):
            nonlocal inline_images, has_html, has_text
            if not isinstance(part, (list, tuple)) or len(part) < 2:
                return
            mime_type = FolderAuditService._decode_imap_atom(part[0]).lower()
            mime_subtype = FolderAuditService._decode_imap_atom(part[1]).lower()
            if not mime_type:
                return

            if FolderAuditService._is_signature_part(mime_type, mime_subtype):
                return

            type_filename = FolderAuditService._filename_from_imap_params(
                part[2] if len(part) > 2 else None
            )
            disp_type, disposition = FolderAuditService._find_imap_disposition(part)
            disp_filename = None
            if disposition and len(disposition) > 1:
                disp_filename = FolderAuditService._filename_from_imap_params(disposition[1])
            filename = disp_filename or type_filename
            content_id = FolderAuditService._content_id_from_part(part)

            if mime_type == 'message' and mime_subtype == 'rfc822':
                attachment_names.append(filename or '(Weitergeleitete Nachricht)')
                return

            if mime_type == 'text':
                if mime_subtype == 'html':
                    has_html = True
                elif mime_subtype == 'plain':
                    has_text = True

            is_text_body = (
                mime_type == 'text'
                and mime_subtype in ('plain', 'html', 'calendar')
                and not filename
                and disp_type != 'attachment'
            )
            if is_text_body:
                return

            if disp_type == 'inline' and in_related and mime_type == 'image':
                inline_images += 1
                return

            if disp_type == 'inline' and content_id and in_related:
                inline_images += 1
                return

            attachment_names.append(
                filename if filename else f"({mime_type}/{mime_subtype})"
            )

        def walk(node, in_related: bool = False):
            if node is None:
                return
            parsed = FolderAuditService._parse_multipart_node(node)
            if parsed:
                subtype, children = parsed
                child_related = in_related or subtype == 'related'
                for child in children:
                    if isinstance(child, (list, tuple)):
                        walk(child, child_related)
                return
            if isinstance(node, (list, tuple)) and len(node) >= 2:
                first = node[0]
                if isinstance(first, (bytes, str)):
                    analyze_leaf(node, in_related)
                    return
            if isinstance(node, (list, tuple)):
                for item in node:
                    walk(item, in_related)

        try:
            walk(bodystructure, False)
            state = 'yes' if attachment_names else 'no'
        except Exception as e:
            logger.warning(
                "BODYSTRUCTURE attachment parse failed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            state = 'unknown'

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
        return (state, attachment_names, content_summary)

    @staticmethod
    def _apply_attachment_heuristics(
        subject: str,
        has_attachments: bool,
        attachment_names: List[str],
    ) -> Tuple[bool, List[str]]:
        """Legacy-Hook — Betreff setzt has_attachments nicht."""
        return has_attachments, attachment_names

    @staticmethod
    def _has_attachments(bodystructure) -> bool:
        state, _, _ = FolderAuditService._extract_attachment_info(bodystructure)
        return state == 'yes'
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
    def delete_emails_by_folder(
        fetcher,
        items: List[Dict],
    ) -> Tuple[int, int]:
        """Löscht Mails anhand (Ordner, UID)-Paaren — UID allein reicht bei Multi-Ordner-Scan nicht."""
        from collections import defaultdict

        by_folder: Dict[str, List[int]] = defaultdict(list)
        skipped = 0
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            folder = item.get("folder")
            uid = item.get("uid")
            if uid is None:
                skipped += 1
                continue
            if isinstance(folder, bytes):
                folder = folder.decode("utf-8", "replace")
            folder = str(folder).strip() if folder is not None else ""
            if not folder:
                skipped += 1
                continue
            try:
                by_folder[folder].append(int(uid))
            except (TypeError, ValueError):
                skipped += 1
                continue

        success = 0
        failed = skipped
        for folder, uids in by_folder.items():
            s, f = FolderAuditService.delete_safe_emails(fetcher, uids, folder)
            success += s
            failed += f
        return success, failed

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
            
            all_in_folder = set(conn.search(["ALL"]))
            valid_uids = [u for u in uids if u in all_in_folder]
            missing = len(uids) - len(valid_uids)
            if not valid_uids:
                logger.warning(
                    f"Delete: keine der {len(uids)} UIDs in Ordner '{target_folder}' gefunden"
                )
                return (0, len(uids))
            
            # Bulk delete (Batches — GMX/Exchange limitieren grosse STORE-Befehle)
            batch_size = 50
            for i in range(0, len(valid_uids), batch_size):
                batch = valid_uids[i : i + batch_size]
                conn.set_flags(batch, ["\\Deleted"])
            conn.expunge()
            
            logger.info(
                f"🗑️ {len(valid_uids)} Emails aus {target_folder} permanent gelöscht"
                + (f" ({missing} UID(s) nicht im Ordner)" if missing else "")
            )
            return (len(valid_uids), len(uids) - len(valid_uids))
            
        except Exception as e:
            logger.error(f"Delete Fehler: {e}")
            return (0, len(uids))

    @staticmethod
    def peek_audit_meta(fetcher, folder: str, uid: int) -> TrashEmailInfo:
        """Layer-1-Metadaten für eine UID (gleiche Parser wie Scan, ohne LLM-Batch)."""
        result = FolderAuditService.fetch_and_analyze_trash(
            fetcher,
            limit=1,
            folder=folder,
            skip_clustering=True,
            clear_scam_caches=False,
            run_llm_batch_at_end=False,
            only_uid=int(uid),
            db_session=None,
            user_id=None,
        )
        if not result.emails:
            raise ValueError(f"UID {uid} nicht in Ordner {folder}")
        return result.emails[0]

    @staticmethod
    def peek_text(fetcher, folder: str, uid: int, max_chars: int = 4000) -> str:
        """Lädt nur den Textanfang einer Mail (BODY.PEEK, kein \\Seen)."""
        conn = fetcher.connection
        if not conn:
            raise RuntimeError("Keine IMAP-Verbindung")
        if not folder or folder == "__ALL__":
            raise ValueError("Ordner fehlt")

        conn.select_folder(folder, readonly=True)
        raw = None
        for spec in ("BODY.PEEK[TEXT]<0.12000>", "BODY.PEEK[TEXT]", "BODY.PEEK[1]<0.12000>"):
            try:
                data = conn.fetch([uid], [spec])
            except Exception as exc:
                logger.debug("peek_text %s fehlgeschlagen: %s", spec, type(exc).__name__)
                continue
            msg = data.get(uid) or {}
            for key, val in msg.items():
                key_s = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
                if "BODY" in key_s.upper() and val:
                    raw = val
                    break
            if raw:
                break

        if not raw:
            return ""
        return preview_body_to_text(raw, max_chars=max_chars)
