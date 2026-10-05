"""
Zwei-Layer Scam-Erkennung für Ordner-Audit.

Layer 1: deterministische Signale (Identität / Transport / Auth getrennt)
Layer 2: LLM Identitäts-Kohärenz (nur Grauzone, nie allein Auto-Löschen)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, List, Optional, Protocol, Set, Tuple

import requests

from src.ollama_timeouts import (
    ollama_chat_request_options,
)
from src.services.audit_scam_llm_config import (
    AUDIT_SCAM_PROMPT_VERSION,
    AuditScamLlmConfig,
    resolve_audit_scam_llm_config,
)
from src.services.brand_domain_policy import (
    AMBIGUOUS_SHORT_BRANDS,
    display_brand_authorized_sender,
    effective_brand_map,
    find_brand_domain_mismatch,
    find_brand_token_in_unofficial_host,
    find_shared_infra_brand_local_mismatch,
)

logger = logging.getLogger(__name__)

# --- Schwellwerte (env überschreibbar) ---


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


LAYER1_AUTO_SCAM = _int_env("AUDIT_SCAM_LAYER1_AUTO", 80)
LAYER1_LLM_GATE_MIN = _int_env("AUDIT_SCAM_LAYER1_LLM_MIN", 40)
LLM_MISMATCH_CONFIDENCE = _int_env("AUDIT_SCAM_LLM_MISMATCH_CONF", 75)
LLM_REVIEW_CONFIDENCE = _int_env("AUDIT_SCAM_LLM_REVIEW_CONF", 40)
LLM_ENABLED_DEFAULT = _bool_env("AUDIT_SCAM_LLM_ENABLED", True)
LLM_TIMEOUT = _int_env("AUDIT_SCAM_LLM_TIMEOUT", 90)
TRANSPORT_SCORE_CAP = _int_env("AUDIT_SCAM_TRANSPORT_CAP", 28)
AUDIT_SCAM_LLM_MAX_PER_SCAN = _int_env("AUDIT_SCAM_LLM_MAX_PER_SCAN", 150)
AUDIT_SCAM_LLM_TIME_BUDGET_SEC = _int_env("AUDIT_SCAM_LLM_TIME_BUDGET_SEC", 600)
AUDIT_SCAM_LLM_CONTINUE_MAX_PER_CALL = _int_env(
    "AUDIT_SCAM_LLM_CONTINUE_MAX_PER_CALL", 40
)
AUDIT_SCAM_LLM_CONTINUE_TIME_BUDGET_SEC = _int_env(
    "AUDIT_SCAM_LLM_CONTINUE_TIME_BUDGET_SEC", 90
)
AUDIT_SCAM_LLM_MANUAL_MAX_PER_DAY = _int_env("AUDIT_SCAM_LLM_MANUAL_MAX_PER_DAY", 50)

from src.services.shared_mail_infrastructure import FREEMAIL_REGISTRABLE

FREEMAIL_DOMAINS = FREEMAIL_REGISTRABLE

SENT_FOLDER_NAMES = frozenset(
    {
        "sent",
        "gesendet",
        "gesendete",
        "envoyé",
        "envoyés",
        "inviati",
        "sent items",
        "sent mail",
        "drafts",
        "entwürfe",
    }
)

SYSTEM_LOCAL_PARTS = frozenset({"mailer-daemon", "postmaster"})

SCAM_MAILER_RE = re.compile(r"v1p3r|darkmailer|sendblaster|spam\s*mailer", re.I)
RANDOM_FROM_RE = re.compile(r"<[a-z0-9]{16,}@", re.I)
PERSON_NAME_RE = re.compile(
    r"^[A-ZÄÖÜ][\w.'\-]+(?:\s+[A-ZÄÖÜ][\w.'\-]+)*,\s*[A-ZÄÖÜ][\w.'\-]+"
    r"|^[A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+"
    r"|^[a-zäöü]{2,}\s+[a-zäöü]{2,}$",
)
PERSON_LOCAL_RE = re.compile(r"^[a-z]{2,}[._-][a-z]{3,}\d{1,3}$", re.I)
E3_PRIVATE_LOCAL_RE = re.compile(
    r"^[a-z]{1,2}[._-][a-z]{3,}\d{0,3}$|^[a-z]{2,}[._-][a-z]{2,}\d{0,3}$",
    re.I,
)
E3_SHORT_LOCAL_RE = re.compile(r"^[a-z]{1,5}$", re.I)
E3_ORG_CODE_LOCAL_RE = re.compile(r"^[a-z]{1,4}\d{1,4}$", re.I)
E4_SHORT_RANDOM_RE = re.compile(r"^[A-Z0-9]{5,10}$")
E4_LONG_DIGITS_RE = re.compile(r"^\d{8,}$")

# Hide-My-Email / Relay — Local-Parts sehen zufällig aus, sind aber kein Scam-Signal (E4)
RELAY_SENDER_DOMAINS = frozenset(
    {
        "privaterelay.appleid.com",
        "relay.firefox.com",
        "mozmail.com",
        "simplelogin.com",
        "simplelogin.co",
        "slmail.me",
        "duck.com",
        "anonaddy.com",
        "anonaddy.me",
    }
)

MARKETING_PLATFORMS = (
    "shopifyemail.com",
    "mailchimp.com",
    "sendgrid.net",
    "constantcontact.com",
    "hubspot.com",
    "sparkpost.com",
    "mailgun.org",
    "ccsend.com",
)

ORG_DISPLAY_HINTS = re.compile(
    r"\b(ag|gmbh|gmbh\s*&\s*co|sa|srl|inc|ltd|llc|"
    r"rückerstattung|rueckerstattung|behörde|behoerde|"
    r"bank|versicherung|telekom|teleboy|swisspass|swissid|"
    r"group|holding|university|universität|universitaet)\b",
    re.I,
)

DISPLAY_STOPWORDS = {
    "team", "service", "support", "newsletter", "info", "noreply", "official",
    "customer", "the", "der", "die", "das", "und", "fur", "für", "von", "via",
    "ag", "gmbh", "inc", "ltd", "llc", "sa", "srl",
}

E3_LOCAL_STOP = DISPLAY_STOPWORDS | {
    "mail", "email", "www", "http", "smtp", "imap", "pop", "test",
    "send", "root", "hello", "hi", "sales", "contact", "news", "admin",
    "billing", "store", "shop", "help", "office", "post", "mailer",
}

CC_TLDS = {"ch", "de", "at", "it", "fr", "nl", "be", "li", "uk", "us", "eu", "es"}

LLM_PLACEHOLDER_RE = re.compile(
    r"ein satz auf deutsch|org-name oder null|eine aussage in deutsch|"
    r"ist nicht zu finden|ein beispiel ist:|"
    r"es wird wahrscheinlich eine typosquatting",
    re.I,
)

IDENTITY_PROMPT = """Du prüfst NUR diese eine E-Mail auf Identitäts-Betrug.
Erfinde nichts. Nenne keine Marken, die in den Feldern unten nicht vorkommen.

Absendername:  {display_name}
From-Adresse:  {from_address}
Reply-To:      {replyto_domain}
Betreff:       {subject}
Provider-Spam: {provider_spam}
Auth:          {auth_summary}
List-Unsubscribe: {list_unsub}

mismatch=true nur bei klarem Identitätsbetrug (Marke/Behörde passt nicht zur From-Domain).
JSON, sonst nichts:
{{
  "mismatch": false,
  "confidence": 0,
  "reason": null,
  "impersonated": null
}}"""

IDENTITY_PROMPT_V2 = """Du bewertest NUR die sichtbare Identität dieser E-Mail.
Nutze ausschließlich Anzeigename, From-Adresse und Betreff. Keine Annahmen zu Provider, Auth oder Newsletter.

Absendername:  {display_name}
From-Adresse:  {from_address}
Betreff:       {subject}

verdict: S = Identitätsbetrug/Phishing, O = plausibel in Ordnung, U = unklar
Antwort nur als JSON:
{{
  "verdict": "O",
  "reason": null
}}"""

# Betreffmuster für Hybrid-Zweitbeleg (zusätzlich zu Layer-1-Regeln / Provider)
PHISHING_SUBJECT_RE = re.compile(
    r"rückerstattung|rueckerstattung|zahlung|identit|sicherheitshinweis|"
    r"abonnement|verstoss|gesperrt|bestätigen|bestaetigen|phishing|konto",
    re.I,
)


class EmailMeta(Protocol):
    subject: str
    sender: str
    sender_name: str
    auth_results: Optional[str]
    reply_to: Optional[str]
    x_mailer: Optional[str]
    server_spam_flag: bool
    provider_junk_score: Optional[int]
    is_auto_generated: bool
    to_header: Optional[str]
    list_unsubscribe: Optional[str]


@dataclass
class ScamEvaluation:
    is_scam: bool = False
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    layer1_score: int = 0
    layer1_flags: List[str] = field(default_factory=list)
    identity_score: int = 0
    transport_score: int = 0
    identity_rules: List[str] = field(default_factory=list)
    llm_used: bool = False
    llm_result: Optional[dict] = None
    needs_review_boost: bool = False
    identity_suspicion: bool = False
    llm_deferred: bool = False
    llm_priority: int = 0
    llm_unusable: bool = False
    llm_skip_reason: Optional[str] = None  # budget | quota | error (nur offen)


_DEDUPE_UNUSABLE = object()


@dataclass
class AuditScanContext:
    """Gemeinsames LLM-Budget pro Scan (Alle-Ordner: ein Kontext, kein Reset pro Ordner)."""

    llm_budget: int
    llm_time_budget_sec: float
    start_monotonic: float = field(default_factory=time.monotonic)
    llm_calls_used: int = 0
    skipped_candidates: int = 0
    pending: List[Tuple[Any, "ScamEvaluation"]] = field(default_factory=list)
    known_contact_context: Any = None
    firstname_set: Optional[Set[str]] = None

    def can_call_llm(self, *, apply_time_budget: bool = True) -> bool:
        if self.llm_calls_used >= self.llm_budget:
            return False
        if apply_time_budget and (
            (time.monotonic() - self.start_monotonic) >= self.llm_time_budget_sec
        ):
            return False
        return True

    def record_llm_call(self) -> None:
        self.llm_calls_used += 1


_dbl_cache: dict[str, tuple[bool, str]] = {}
_identity_llm_cache: dict[str, dict] = {}
_dbl_lookups_this_scan = 0
_dbl_timeouts_this_scan = 0
_dbl_circuit_open = False
DBL_MAX_PER_SCAN = _int_env("AUDIT_SCAM_DBL_MAX", 50)
GRAY_DNS_MAX_PER_SCAN = _int_env("AUDIT_SCAM_GRAY_DNS_MAX", 40)
GRAY_RDAP_MAX_PER_SCAN = _int_env("AUDIT_SCAM_GRAY_RDAP_MAX", 20)
_gray_dns_lookups_this_scan = 0
_gray_rdap_lookups_this_scan = 0


def extract_domain(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].lower().strip(">").strip()


def extract_local_part(sender: str) -> str:
    if not sender or "@" not in sender:
        return ""
    local = sender.split("@")[0]
    local = re.sub(r"^.*<", "", local).strip("<>").strip()
    return local


def is_relay_sender_domain(sender: str) -> bool:
    """True für Apple Private Relay, Firefox Relay, SimpleLogin, Duck.com usw."""
    dom = extract_domain(sender)
    if not dom:
        return False
    if dom in RELAY_SENDER_DOMAINS:
        return True
    return any(dom.endswith("." + relay) for relay in RELAY_SENDER_DOMAINS)


def normalize_sender_email(sender: str) -> str:
    s = (sender or "").strip().lower()
    if "<" in s and ">" in s:
        m = re.search(r"<([^>]+)>", s)
        if m:
            return m.group(1).strip()
    return s


def should_never_scam(
    meta: EmailMeta,
    *,
    account_email: Optional[str] = None,
    own_domains: Optional[Set[str]] = None,
    folder: Optional[str] = None,
) -> bool:
    """Nur eigene Adresse, eigene Domains (Meine Domains), Sent/Drafts, echte System-Absender."""
    own = own_domains or set()
    from src.services.audit_safe_delete_veto import is_sent_or_drafts_folder

    if is_sent_or_drafts_folder(folder):
        return True

    folder_key = (folder or "").strip().lower()
    if folder_key in SENT_FOLDER_NAMES:
        return True

    sender_norm = normalize_sender_email(meta.sender or "")
    if account_email and sender_norm == account_email.strip().lower():
        return True

    dom = extract_domain(sender_norm or meta.sender or "")
    if dom:
        for od in own:
            od = od.lower().strip()
            if not od:
                continue
            if dom == od or dom.endswith("." + od):
                return True

    local = extract_local_part(meta.sender or "").lower()
    if local in SYSTEM_LOCAL_PARTS:
        return True
    return False


def _looks_like_person_name(display_name: str) -> bool:
    name = (display_name or "").strip()
    if not name:
        return False
    return bool(PERSON_NAME_RE.match(name))


def _significant_display_tokens(display_name: str) -> List[str]:
    return _display_tokens_min_len(display_name, min_len=4)


def _display_tokens_min_len(display_name: str, *, min_len: int = 3) -> List[str]:
    from src.services.audit_identity_helpers import (
        fold_identity_ascii,
        normalize_display_name_for_identity,
    )

    raw = fold_identity_ascii(normalize_display_name_for_identity(display_name))
    parts = re.split(r"[^a-z0-9]+", raw)
    tokens: List[str] = []
    for part in parts:
        if len(part) < min_len or part in DISPLAY_STOPWORDS:
            continue
        tokens.append(part)
    return tokens


def _any_display_token_in_domain(name: str, sender: str) -> bool:
    """True wenn ein Anzeigenamen-Token zur Absender-Domain passt (Label oder langer Bezug)."""
    host = extract_domain(sender).lower()
    if not host:
        return False
    labels = [p for p in re.split(r"[.-]", host) if p]
    dd = host.replace(".", "").replace("-", "")
    for tok in _display_tokens_min_len(name, min_len=3):
        if tok in labels:
            return True
        if len(tok) >= 6 and tok in dd:
            return True
    return False


def _looks_like_organization_display(display_name: str) -> bool:
    if not display_name or len(display_name.strip()) < 4:
        return False
    org_role_words = (
        "kundenservice", "kundenbetreuung", "support", "service", "team",
        "newsletter", "hotline", "mitarbeiter", "kundendienst", "kundensupport",
    )
    parts = re.split(r"\s+", display_name.strip())
    if any(p.lower() in org_role_words for p in parts):
        return True
    if ORG_DISPLAY_HINTS.search(display_name):
        return True
    if _looks_like_person_name(display_name):
        return False
    return len(_significant_display_tokens(display_name)) >= 2


def _identity_person_blocks_e3e6(name: str, sender: str = "", meta=None) -> bool:
    from src.services.audit_firstnames import get_firstname_set
    from src.services.audit_identity_helpers import (
        fold_identity_ascii,
        is_functional_role_local,
        local_reflects_person_name,
        normalize_display_name_for_identity,
        person_display_with_firstnames,
        _firstname_in_set,
    )

    if is_functional_role_local(sender or ""):
        return True
    if _looks_like_organization_display(name):
        return False
    name_norm = normalize_display_name_for_identity(name or "")
    fn = None
    if meta is not None:
        fn = getattr(meta, "_firstname_set", None)
        if fn is None and getattr(meta, "_db_session", None):
            fn = get_firstname_set(getattr(meta, "_db_session", None))
    if "," in name_norm and person_display_with_firstnames(name_norm, fn):
        return True
    if person_display_with_firstnames(name_norm, fn) and local_reflects_person_name(
        name_norm, sender or ""
    ):
        return True
    if person_display_with_firstnames(name_norm, fn):
        lp = extract_local_part(sender or "").lower()
        if PERSON_LOCAL_RE.match(lp) or E3_PRIVATE_LOCAL_RE.match(lp):
            return True
        if lp and re.match(r"^[a-z]+[._-][a-z]{2,}", lp):
            return True
        lp_f = fold_identity_ascii(lp.split("+")[0])
        if lp_f and len(lp_f) >= 4:
            for w in re.split(r"\s+", name_norm):
                if fold_identity_ascii(w) == lp_f:
                    return True
    fn_set = fn or set()
    if fn_set and local_reflects_person_name(name_norm, sender or ""):
        if any(_firstname_in_set(w, fn_set) for w in name_norm.split()):
            return True
    return False


def _meta_has_list_unsubscribe(meta: EmailMeta) -> bool:
    if getattr(meta, "list_unsubscribe", None):
        return True
    return bool(getattr(meta, "has_list_unsubscribe", False))


def _e3e6_reputation_exempt(meta: EmailMeta, brand_map=None) -> bool:
    """Tranco Top-N + List-Unsubscribe (Bulk) — für E3/E6/E8/E9, nicht B1/B2."""
    from src.services.brand_domain_policy import (
        find_brand_domain_mismatch,
        registrable_domain_from_host,
    )
    from src.services.shared_mail_infrastructure import shared_infrastructure_registrable
    from src.services.tranco_popularity import get_tranco_store, tranco_top_n_threshold

    if brand_map is None:
        brand_map = effective_brand_map(None)
    if find_brand_domain_mismatch(
        meta.sender_name or "",
        meta.sender or "",
        brand_map,
    ):
        return False

    reg = registrable_domain_from_host(extract_domain(meta.sender or ""))
    if not reg or shared_infrastructure_registrable(reg):
        return False
    store = get_tranco_store()
    if store is None or not store.is_in_top_n(reg, tranco_top_n_threshold()):
        return False
    if _meta_has_list_unsubscribe(meta):
        return True
    return False


def _is_person_display(display_name: str) -> bool:
    from src.services.audit_identity_helpers import normalize_display_name_for_identity

    n = normalize_display_name_for_identity(display_name)
    n = re.sub(r"\(.*?\)", "", n).strip()
    if "," in n:
        parts = n.split(",")
        if len(parts) == 2 and all(1 <= len(x.split()) <= 2 for x in parts):
            return True
    words = n.split()
    org_words = (
        "team", "support", "service", "kundenservice", "kundenbetreuung",
        "hotline", "ag", "gmbh", "bank", "versicherung", "noreply",
    )
    if any(w.lower() in org_words for w in words):
        return False
    if ORG_DISPLAY_HINTS.search(n):
        return False
    if 2 <= len(words) <= 3 and all(re.fullmatch(r"[\w.'’\-]+", w) for w in words):
        if all(re.match(r"^[A-ZÄÖÜ]", w) for w in words) or all(
            w.islower() for w in words
        ):
            return True
    return False


def identity_rule_e1(_name: str, sender: str) -> bool:
    return "/" in extract_local_part(sender)


def _e3_private_mailbox_local(lp: str, sender: str = "") -> bool:
    from src.services.audit_identity_helpers import is_functional_role_local

    if sender and is_functional_role_local(sender):
        return False
    if PERSON_LOCAL_RE.match(lp) or E3_PRIVATE_LOCAL_RE.match(lp):
        return True
    if E3_ORG_CODE_LOCAL_RE.match(lp):
        return True
    if E3_SHORT_LOCAL_RE.match(lp) and lp not in E3_LOCAL_STOP:
        return True
    return False


GENERIC_ORG_CLAIM_RE = re.compile(
    r"\b(support|team|noreply|no-reply|service)\b",
    re.I,
)


def identity_rule_e3(name: str, sender: str, meta=None, brand_map=None) -> bool:
    from src.services.audit_identity_helpers import (
        is_functional_role_local,
        normalize_display_name_for_identity,
    )
    from src.services.brand_domain_policy import sender_on_official_brand_domain

    name = normalize_display_name_for_identity(name)
    lp = extract_local_part(sender).lower()
    if is_functional_role_local(sender):
        return False
    if brand_map and sender_on_official_brand_domain(sender, brand_map):
        return False
    dom = extract_domain(sender)
    if not _e3_private_mailbox_local(lp, sender):
        return False
    if E3_SHORT_LOCAL_RE.match(lp) and lp not in E3_LOCAL_STOP:
        if not _looks_like_organization_display(name):
            return False
    if _identity_person_blocks_e3e6(name, sender, meta=meta):
        return False
    if dom in FREEMAIL_DOMAINS:
        return False
    if _any_display_token_in_domain(name, sender):
        return False
    tokens = _display_tokens_min_len(name, min_len=3)
    if not tokens:
        return False
    return True


def identity_rule_e7(name: str, sender: str, meta=None) -> bool:
    """Generische Organisations-Behauptung + Privatpostfach-Local-Part (vorname.nachname)."""
    from src.services.audit_identity_helpers import (
        is_functional_role_local,
        normalize_display_name_for_identity,
    )

    name = normalize_display_name_for_identity(name)
    if is_functional_role_local(sender):
        return False
    if not GENERIC_ORG_CLAIM_RE.search(name or ""):
        return False
    lp = extract_local_part(sender).lower()
    if not (PERSON_LOCAL_RE.match(lp) or E3_PRIVATE_LOCAL_RE.match(lp)):
        return False
    if _identity_person_blocks_e3e6(name, sender, meta=meta):
        return False
    return True


NOREPLY_CODE_LOCAL_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*\d[a-z0-9._-]*$|^[a-z0-9]{2,8}_[a-z0-9]{2,12}$",
    re.I,
)


def identity_rule_e8(name: str, sender: str) -> bool:
    """«Noreply»/Code-Local-Part (Ziffern/Kürzel) — typisch Fake-Newsletter."""
    from src.services.audit_identity_helpers import (
        is_functional_role_local,
        normalize_display_name_for_identity,
    )

    name = normalize_display_name_for_identity(name)
    if is_functional_role_local(sender):
        return False
    name_l = name.lower()
    if not re.search(r"\bno[- ]?reply\b", name_l, re.I):
        return False
    lp = extract_local_part(sender).lower()
    if not lp or not re.search(r"\d", lp):
        return False
    return bool(NOREPLY_CODE_LOCAL_RE.match(lp))


def identity_rule_e9(name: str, sender: str, meta: EmailMeta) -> bool:
    """Personenname + Rollen-Local-Part + Rechnung/Anhang (Malware-Muster)."""
    from src.services.audit_firstnames import get_firstname_set
    from src.services.audit_identity_helpers import (
        INVOICE_SUBJECT_RE,
        is_functional_role_local,
        normalize_display_name_for_identity,
        person_display_with_firstnames,
    )

    name = normalize_display_name_for_identity(name)
    if not is_functional_role_local(sender):
        return False
    fn = getattr(meta, "_firstname_set", None)
    if fn is None and getattr(meta, "_db_session", None):
        fn = get_firstname_set(getattr(meta, "_db_session", None))
    person = person_display_with_firstnames(name, fn)
    if not person:
        return False
    subj = getattr(meta, "subject", "") or ""
    if INVOICE_SUBJECT_RE.search(subj):
        return True
    if getattr(meta, "has_attachments", False):
        return True
    return False


# Local-Parts typischer CMS/Infrastruktur auf Kundendomains — kein Marken-Phishing (E6)
E6_OWN_PRODUCT_LOCALS = frozenset(
    {
        "wordpress", "woocommerce", "joomla", "drupal", "prestashop",
        "unifi", "monitor", "billing", "newsletter", "notifications",
    }
)
E6_FUNCTIONAL_LOCALS = frozenset(
    {
        "sekretariat", "secretariat", "info", "kontakt", "contact", "office",
        "mail", "admin", "service", "support", "help", "team",
    }
)


def _e6_functional_org_exempt(name: str, sender: str) -> bool:
    lp = extract_local_part(sender).lower()
    if lp not in E6_FUNCTIONAL_LOCALS:
        return False
    return _any_display_token_in_domain(name, sender)


def identity_rule_e6(name: str, sender: str, meta=None, brand_map=None) -> bool:
    """Local-Part spiegelt Anzeigenamen, Domain ohne diesen Bezug."""
    from src.services.audit_identity_helpers import (
        is_functional_role_local,
        local_reflects_person_name,
        normalize_display_name_for_identity,
    )
    from src.services.brand_domain_policy import sender_on_official_brand_domain

    name = normalize_display_name_for_identity(name)
    lp = extract_local_part(sender).lower()
    if not lp:
        return False
    if is_functional_role_local(sender):
        return False
    if brand_map and sender_on_official_brand_domain(sender, brand_map):
        return False
    dom = extract_domain(sender)
    if dom in FREEMAIL_DOMAINS:
        return False
    if _identity_person_blocks_e3e6(name, sender, meta=meta):
        return False
    from src.services.audit_firstnames import get_firstname_set
    from src.services.audit_identity_helpers import person_display_with_firstnames

    fn = None
    if meta is not None:
        fn = getattr(meta, "_firstname_set", None)
        if fn is None and getattr(meta, "_db_session", None):
            fn = get_firstname_set(getattr(meta, "_db_session", None))
    if local_reflects_person_name(name, sender) and (
        person_display_with_firstnames(name, fn) or _is_person_display(name)
    ):
        return False
    if _e6_functional_org_exempt(name, sender):
        return False
    if _any_display_token_in_domain(name, sender):
        return False
    dom = extract_domain(sender).lower().replace(".", "").replace("-", "")
    tokens = _display_tokens_min_len(name, min_len=3)
    if not tokens:
        return False
    compact_lp = lp.replace("-", "").replace("_", "").replace(".", "")
    base_lp = compact_lp.split("+")[0]
    if base_lp in E6_OWN_PRODUCT_LOCALS and base_lp in tokens:
        return False
    if len(tokens) == 1 and tokens[0] in E6_OWN_PRODUCT_LOCALS and tokens[0] in base_lp:
        return False
    for tok in tokens:
        if tok in compact_lp and tok not in dom:
            return True
    return False


def identity_rule_e4(_name: str, sender: str) -> bool:
    if is_relay_sender_domain(sender):
        return False
    lp = extract_local_part(sender)
    if E4_LONG_DIGITS_RE.fullmatch(lp):
        return True
    if E4_SHORT_RANDOM_RE.fullmatch(lp):
        return any(c.isdigit() for c in lp) and any(c.isalpha() for c in lp)
    return _is_random_local_part(sender)


def identity_rule_e5(name: str, _sender: str) -> bool:
    if not name:
        return False
    scripts = set()
    for ch in name:
        if ch.isalpha():
            nm = unicodedata.name(ch, "")
            scripts.add("LATIN" if nm.startswith("LATIN") else nm.split()[0])
    if "LATIN" in scripts and len(scripts) > 1:
        return True
    return any(re.search(r"[A-Z]{2,}l[A-Z]{2,}", w) for w in re.findall(r"[A-Za-z]{4,}", name))


def assess_identity_rules(
    meta: EmailMeta,
    brand_map=None,
) -> Tuple[List[str], List[str], int]:
    """Returns (rule_ids, human messages, identity_score)."""
    from src.services.audit_identity_helpers import normalize_display_name_for_identity

    name = normalize_display_name_for_identity(meta.sender_name or "")
    sender = meta.sender or ""
    hits: List[str] = []
    messages: List[str] = []
    score = 0

    checks = (
        ("E1", lambda n, s: identity_rule_e1(n, s), "Pfad oder Slash im Absender-Local-Part", 85),
        ("E3", lambda n, s: identity_rule_e3(n, s, meta, brand_map=brand_map), "Organisationsname, Absender wirkt wie Privatpostfach", 55),
        ("E6", lambda n, s: identity_rule_e6(n, s, meta, brand_map=brand_map), "Local-Part spiegelt Anzeigenamen, fremde Domain", 55),
        ("E7", lambda n, s: identity_rule_e7(n, s, meta), "Generische Behauptung (Support/Team/Service), Privatpostfach", 55),
        ("E8", lambda n, s: identity_rule_e8(n, s), "Noreply-Anzeige mit Code-Local-Part (Ziffern)", 50),
        ("E9", lambda n, s: identity_rule_e9(n, s, meta), "Personenname mit Rollen-Absender und Rechnung/Anhang", 60),
        ("E4", lambda n, s: identity_rule_e4(n, s), "Zufalls- oder Kurzcode-Absenderadresse", 55),
        ("E5", lambda n, s: identity_rule_e5(n, s), "Verdächtige Zeichen im Anzeigenamen (Homoglyphen)", 70),
    )
    for rule_id, fn, msg, pts in checks:
        if not fn(name, sender):
            continue
        if rule_id in ("E3", "E6", "E8", "E9") and _e3e6_reputation_exempt(meta, brand_map=brand_map):
            continue
        hits.append(rule_id)
        messages.append(msg)
        score += pts

    _rt = getattr(meta, "reply_to", None)
    reply_domain = extract_domain(_rt or "") if _rt else ""
    from_domain = extract_domain(sender)
    squat = _glued_cctld_squat(name, from_domain, reply_domain)
    if squat:
        hits.append("E5b")
        messages.append(squat)
        score += 80

    x_mailer = getattr(meta, "x_mailer", None) or ""
    if SCAM_MAILER_RE.search(x_mailer):
        hits.append("X1")
        messages.append(f"Bekannte Scam-Software ({x_mailer[:40]})")
        score += 80

    if not is_relay_sender_domain(sender) and RANDOM_FROM_RE.search(sender):
        hits.append("E4b")
        messages.append("Langrandom in From-Header")
        score += 40

    return hits, messages, score


def _glued_cctld_squat(display_name: str, *domains: str) -> Optional[str]:
    tokens = _significant_display_tokens(display_name)
    if not tokens:
        return None
    for domain in domains:
        if not domain or "." not in domain:
            continue
        labels = domain.lower().strip(".").split(".")
        if len(labels) < 2:
            continue
        sld, tld = labels[-2], labels[-1]
        if tld not in ("com", "net", "org", "info"):
            continue
        for tok in tokens:
            if tok not in sld or sld == tok:
                continue
            remainder = sld.replace(tok, "", 1)
            if remainder in CC_TLDS:
                return f"Lookalike-Domain: {domain}"
    return None


def _auth_summary(auth: str) -> Tuple[bool, bool, List[str], int]:
    """Returns weak_none, forged_fail, messages, auth_score (can force scam)."""
    a = (auth or "").lower()
    messages: List[str] = []
    score = 0
    weak_none = "dkim=none" in a and "dmarc=none" in a
    if "spf=fail" in a:
        score += 80
        messages.append("SPF fail")
    if "dmarc=fail" in a:
        score += 80
        messages.append("DMARC fail")
    if "dkim=fail" in a:
        score += 55
        messages.append("DKIM fail")
    elif weak_none:
        messages.append("Kein DKIM/DMARC")
    return weak_none, score >= 80, messages, score


def assess_transport(meta: EmailMeta) -> Tuple[int, str]:
    """Single capped transport/provider score and one summary line."""
    raw = 0
    parts: List[str] = []
    if meta.server_spam_flag:
        raw += 18
        parts.append("Spam-Flag")
    junk = meta.provider_junk_score
    if junk is not None:
        if junk >= 10:
            raw += 22
            parts.append(f"Junk {junk}")
        elif junk >= 5:
            raw += 14
            parts.append(f"Junk {junk}")
        elif junk >= 2:
            raw += 6
            parts.append(f"Junk {junk}")
    capped = min(TRANSPORT_SCORE_CAP, raw)
    if not parts:
        return 0, ""
    return capped, "Provider-Verdikt (" + ", ".join(parts) + ")"


def format_reason_lines(
    identity_msgs: List[str],
    transport_line: str,
    auth_msgs: List[str],
    extra: Optional[List[str]] = None,
) -> List[str]:
    lines: List[str] = []
    if identity_msgs:
        lines.append("Identität: " + "; ".join(identity_msgs))
    if transport_line:
        lines.append("Transport: " + transport_line)
    if auth_msgs:
        lines.append("Auth: " + "; ".join(auth_msgs))
    if extra:
        lines.extend(extra)
    return lines


def check_dbl(domain: str, db_session=None) -> Tuple[bool, str]:
    global _dbl_lookups_this_scan, _dbl_timeouts_this_scan, _dbl_circuit_open

    if not domain or _dbl_circuit_open:
        return False, ""

    domain = domain.lower().strip(".")
    if domain in _dbl_cache:
        return _dbl_cache[domain]

    from src.services.domain_reputation import lookup_spamhaus_dbl, read_spamhaus_dbl_cache

    cached = read_spamhaus_dbl_cache(domain, db_session)
    if cached is not None:
        out = (cached.listed, cached.detail)
        _dbl_cache[domain] = out
        return out

    if _dbl_lookups_this_scan >= DBL_MAX_PER_SCAN:
        return False, ""

    _dbl_lookups_this_scan += 1
    result = lookup_spamhaus_dbl(domain, db_session)
    listed, reason = result.listed, result.detail
    if result.unavailable:
        _dbl_timeouts_this_scan += 1
        if _dbl_timeouts_this_scan >= 3:
            _dbl_circuit_open = True
            logger.warning(
                "Spamhaus DBL circuit open after %s unavailable responses",
                _dbl_timeouts_this_scan,
            )
        elif reason:
            logger.warning("DBL check skipped (unavailable) for %s: %s", domain, reason)

    _dbl_cache[domain] = (listed, reason)
    return listed, reason


def audit_scam_dbl_scan_notice() -> str:
    """Kurzer Hinweis für FolderAuditResult.scan_notice nach dem Scan."""
    if _dbl_circuit_open:
        return (
            "Spamhaus DBL für diesen Scan ausgesetzt "
            "(mehrfach nicht verfügbar — Resolver laut docs/audit/spamhaus-dbl.md prüfen)."
        )
    return ""


def clear_audit_scam_caches() -> None:
    global _dbl_lookups_this_scan, _dbl_timeouts_this_scan, _dbl_circuit_open
    global _gray_dns_lookups_this_scan, _gray_rdap_lookups_this_scan
    _dbl_cache.clear()
    _identity_llm_cache.clear()
    _dbl_lookups_this_scan = 0
    _dbl_timeouts_this_scan = 0
    _dbl_circuit_open = False
    _gray_dns_lookups_this_scan = 0
    _gray_rdap_lookups_this_scan = 0


def new_audit_scan_context() -> AuditScanContext:
    return AuditScanContext(
        llm_budget=AUDIT_SCAM_LLM_MAX_PER_SCAN,
        llm_time_budget_sec=float(AUDIT_SCAM_LLM_TIME_BUDGET_SEC),
    )


def llm_dedupe_key(meta: EmailMeta) -> str:
    """Gleicher Anzeigename + Absender-Domain → ein LLM-Aufruf pro Scan-Batch."""
    display = (meta.sender_name or "").strip().lower()[:80]
    dom = extract_domain(meta.sender or "")
    return f"{display}|{dom}"


def identity_llm_cache_key(cfg: AuditScamLlmConfig, meta: EmailMeta) -> str:
    from_address = normalize_sender_email(meta.sender or "") or "(leer)"
    display = (meta.sender_name or "").strip() or "(leer)"
    subject = (meta.subject or "").strip()[:200]
    raw = f"{cfg.provider}|{cfg.model}|{cfg.prompt_version}|{display}|{from_address}|{subject}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _load_identity_llm_db(db_session, cache_key: str) -> Optional[dict]:
    try:
        import importlib

        from src.helpers.database import get_db_session

        models = importlib.import_module(".02_models", "src")

        def _read(session):
            row = (
                session.query(models.AuditIdentityLlmCache)
                .filter_by(cache_key=cache_key)
                .first()
            )
            if row and row.result_json:
                return json.loads(row.result_json)
            return None

        if db_session is not None:
            return _read(db_session)
        with get_db_session() as session:
            return _read(session)
    except Exception as exc:
        logger.debug("Audit LLM DB cache read: %s", exc)
    return None


def _store_identity_llm_db(db_session, cache_key: str, result: dict) -> None:
    """Eigene kurze DB-Session — kein commit() auf der Scan-Session."""
    try:
        import importlib

        from src.helpers.database import get_db_session

        models = importlib.import_module(".02_models", "src")
        payload = json.dumps(result, ensure_ascii=False)
        with get_db_session() as session:
            row = (
                session.query(models.AuditIdentityLlmCache)
                .filter_by(cache_key=cache_key)
                .first()
            )
            if row:
                row.result_json = payload
            else:
                session.add(
                    models.AuditIdentityLlmCache(
                        cache_key=cache_key,
                        result_json=payload,
                    )
                )
            session.commit()
    except Exception as exc:
        logger.debug("Audit LLM DB cache write: %s", exc)


def get_manual_llm_quota_used(user_id: int) -> int:
    limit = AUDIT_SCAM_LLM_MANUAL_MAX_PER_DAY
    if limit <= 0:
        return 0
    try:
        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        key = f"audit_manual_llm:{user_id}:{date.today().isoformat()}"
        raw = r.get(key)
        return int(raw) if raw else 0
    except Exception:
        return 0


def reserve_manual_llm_quota(user_id: int) -> Tuple[bool, int]:
    """Zählt nur echte LLM-Aufrufe (nach Cache-Miss), atomar per INCR."""
    limit = AUDIT_SCAM_LLM_MANUAL_MAX_PER_DAY
    if limit <= 0:
        return True, 0
    try:
        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        key = f"audit_manual_llm:{user_id}:{date.today().isoformat()}"
        new_count = r.incr(key)
        if new_count == 1:
            r.expire(key, 172800)
        if new_count > limit:
            r.decr(key)
            return False, limit
        return True, new_count
    except Exception as exc:
        logger.warning("Manual LLM quota: Redis unavailable (%s), allow", exc)
        return True, 0


def check_manual_llm_quota(user_id: int) -> Tuple[bool, int]:
    """Nur Lesen: Limit schon erreicht? (ohne Zähler zu erhöhen)"""
    limit = AUDIT_SCAM_LLM_MANUAL_MAX_PER_DAY
    if limit <= 0:
        return True, 0
    used = get_manual_llm_quota_used(user_id)
    if used >= limit:
        return False, used
    return True, used


def _is_random_local_part(sender: str) -> bool:
    if "@" not in sender:
        return False
    local = extract_local_part(sender).lower()
    if len(local) < 14:
        return False
    letters = sum(1 for c in local if c.isalpha())
    digits = sum(1 for c in local if c.isdigit())
    if digits < 2 or letters < 8:
        return False
    vowels = sum(1 for c in local if c in "aeiou")
    if vowels == 0:
        return True
    consonants = letters - vowels
    return consonants / max(vowels, 1) > 2.0


def quick_header_flags(meta: EmailMeta, *, skip_dbl: bool = False) -> Tuple[int, List[str], bool]:
    """
    Layer-1-Kompatibilität: kombinierter Score + flache Flags für Tests.
    """
    id_rules, id_msgs, id_score = assess_identity_rules(meta)
    transport_score, transport_line = assess_transport(meta)
    auth = meta.auth_results or ""
    weak_none, _forged, auth_msgs, auth_score = _auth_summary(auth)

    combined = id_score + transport_score + (auth_score if auth_score >= 55 else 0)
    flags = format_reason_lines(id_msgs, transport_line, auth_msgs if auth_score >= 55 else auth_msgs[:1])

    suggest_llm = False
    if id_rules and transport_score > 0:
        suggest_llm = True
    if weak_none and _looks_like_organization_display(meta.sender_name or ""):
        suggest_llm = True
    if LAYER1_LLM_GATE_MIN <= combined < LAYER1_AUTO_SCAM:
        suggest_llm = True

    if not skip_dbl:
        from_domain = extract_domain(meta.sender or "")
        _rt = getattr(meta, "reply_to", None)
        reply_domain = extract_domain(_rt or "") if _rt else ""
        for dom in {from_domain, reply_domain} - {""}:
            listed, dbl_reason = check_dbl(dom)
            if listed:
                combined += 60
                flags.append(f"Struktur: Domain in {dbl_reason}")
                break

    return combined, flags, suggest_llm


def _ollama_chat_json(
    prompt: str,
    cfg: Optional[AuditScamLlmConfig] = None,
) -> Optional[dict]:
    cfg = cfg or resolve_audit_scam_llm_config(None)
    if not cfg.model:
        return None

    from src.services.ollama_think_capability import (
        effective_ollama_think,
        ollama_chat_think_extras,
    )

    think_on = (
        effective_ollama_think(
            cfg.model,
            bool(cfg.think),
            base_url=cfg.base_url,
        )
        if cfg.provider == "ollama"
        else False
    )
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": ollama_chat_request_options(think_active=think_on),
        **ollama_chat_think_extras(
            cfg.model, think_on, base_url=cfg.base_url
        ),
    }
    try:
        resp = requests.post(
            f"{cfg.base_url}/api/chat",
            json=payload,
            timeout=cfg.timeout,
        )
        if resp.status_code != 200:
            logger.warning("Audit identity LLM HTTP %s", resp.status_code)
            return None
        logger.info(
            "Audit identity LLM model=%s think=%s",
            cfg.model,
            think_on,
        )
        content = (resp.json().get("message") or {}).get("content", "")
        if not content:
            return None
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("Audit identity LLM failed: %s", type(exc).__name__)
        return None


def _cloud_chat_json(prompt: str, cfg: AuditScamLlmConfig) -> Optional[dict]:
    """Cloud-KI (OpenAI/Anthropic/Mistral) — nur Identitäts-Prompt, JSON-Antwort."""
    try:
        import importlib

        get_ai_client = importlib.import_module("src.03_ai_client").get_ai_client
        client = get_ai_client(cfg.provider, model=cfg.model)
        messages = [{"role": "user", "content": prompt}]
        if hasattr(client, "_post_chat_json"):
            result = client._post_chat_json(messages)
            return result if isinstance(result, dict) else None
    except Exception as exc:
        logger.warning("Audit identity cloud LLM failed: %s", type(exc).__name__)
    return None


def _audit_identity_llm_json(
    prompt: str,
    cfg: Optional[AuditScamLlmConfig] = None,
) -> Optional[dict]:
    cfg = cfg or resolve_audit_scam_llm_config(None)
    prov = (cfg.provider or "ollama").lower()
    if prov == "ollama":
        return _ollama_chat_json(prompt, cfg=cfg)
    return _cloud_chat_json(prompt, cfg)


def _llm_result_usable(llm: dict, meta: EmailMeta) -> Optional[dict]:
    if not isinstance(llm, dict):
        return None

    reason = str(llm.get("reason") or "").strip()
    impersonated = llm.get("impersonated")
    if impersonated is not None:
        impersonated = str(impersonated).strip()
        if not impersonated or impersonated.lower() in ("null", "none", "org-name oder null"):
            impersonated = None
            llm = {**llm, "impersonated": None}

    if reason and LLM_PLACEHOLDER_RE.search(reason):
        return None
    if impersonated and LLM_PLACEHOLDER_RE.search(impersonated):
        return None

    hay = " ".join(
        filter(
            None,
            [meta.sender_name, meta.sender, meta.reply_to, meta.subject],
        )
    ).lower()

    leak_needles = ("serafech", "serafe.ch", "v1p3rbox")
    blob = f"{reason} {impersonated or ''}".lower()
    for needle in leak_needles:
        if needle in blob and needle not in hay:
            return None

    return llm


def _llm_identity_verdict(llm: dict) -> Optional[str]:
    """S/O/U aus Prompt v2; Legacy-Fallback: mismatch + confidence."""
    raw = llm.get("verdict")
    if raw is not None:
        v = str(raw).strip().upper()
        if v in ("S", "O", "U"):
            return v

    mismatch_raw = llm.get("mismatch")
    if isinstance(mismatch_raw, str):
        mismatch = mismatch_raw.strip().lower() in ("true", "1", "yes")
    else:
        mismatch = bool(mismatch_raw)
    if not mismatch:
        return "O"
    try:
        conf = int(llm.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0
    if conf >= LLM_MISMATCH_CONFIDENCE:
        return "S"
    if conf >= LLM_REVIEW_CONFIDENCE:
        return "U"
    return "O"


def hybrid_second_evidence(out: ScamEvaluation, meta: EmailMeta) -> bool:
    """Zweitbeleg für SCAM (KI allein reicht nicht; KI-Begründung zählt nie)."""
    has_identity = bool(out.identity_rules) or out.identity_score >= 55
    if not has_identity:
        return False
    if "E1" in out.identity_rules:
        return True
    if _strong_transport_evidence(meta, out.transport_score):
        return True
    auth = (meta.auth_results or "").lower()
    if "spf=fail" in auth or "dmarc=fail" in auth or "dkim=fail" in auth:
        return True
    if out.transport_score >= 12:
        return True
    return False


def _merge_hybrid_llm_identity(
    out: ScamEvaluation,
    meta: EmailMeta,
    llm: dict,
    brand_map=None,
) -> None:
    llm = calibrate_llm_identity_result(meta, llm, brand_map=brand_map)
    verdict = _llm_identity_verdict(llm)
    if not verdict:
        return

    reason = str(llm.get("reason") or "").strip()
    impersonated = llm.get("impersonated")
    if impersonated is not None:
        impersonated = str(impersonated).strip()
        if not impersonated or impersonated.lower() in ("null", "none"):
            impersonated = None

    if verdict == "O":
        return

    if verdict == "U":
        from src.services.audit_identity_helpers import is_curated_inbox_context

        if is_curated_inbox_context(meta):
            return
        out.needs_review_boost = True
        if reason:
            out.reasons = out.reasons + [f"Identität (KI): {reason}"]
        return

    if verdict != "S":
        return

    if hybrid_second_evidence(out, meta):
        out.is_scam = True
        out.confidence = max(out.confidence, 0.75)
        extra: List[str] = []
        if impersonated:
            extra.append(f"Identität (KI): behauptet {impersonated}")
        if reason:
            extra.append(f"Identität (KI): {reason}")
        out.reasons = out.reasons + extra
        return

    out.identity_suspicion = True
    out.needs_review_boost = False
    if reason:
        out.reasons = out.reasons + [f"Identität (KI): {reason}"]
    return


def _auth_strong_pass(meta: EmailMeta) -> bool:
    """SPF, DKIM und DMARC pass — typisch für legitime Versand-Infrastruktur."""
    a = (meta.auth_results or "").lower()
    if not a:
        return False
    return (
        "dmarc=pass" in a
        and "spf=pass" in a
        and "dkim=pass" in a
    )


def _display_brand_matches_registrable_domain(
    meta: EmailMeta,
    brand_map=None,
) -> bool:
    """Marke in Anzeigename nur ok, wenn Absender zu offizieller Marken-Domain passt."""
    sender = normalize_sender_email(meta.sender or "") or (meta.sender or "")
    if brand_map is None:
        brand_map = effective_brand_map(None)
    return display_brand_authorized_sender(
        meta.sender_name or "",
        sender,
        significant_tokens=_significant_display_tokens(meta.sender_name or ""),
        brand_map=brand_map,
    )


def _layer1_blocks_llm_calibration(meta: EmailMeta, brand_map=None) -> bool:
    id_rules, _msgs, _score = assess_identity_rules(meta)
    if bool({"E1", "E3", "E6", "E7", "E8", "E5", "E5b"} & set(id_rules)):
        return True
    if brand_map is None:
        brand_map = effective_brand_map(None)
    if find_brand_domain_mismatch(
        meta.sender_name or "",
        meta.sender or "",
        brand_map,
    ) is not None:
        return True
    return find_brand_token_in_unofficial_host(
        meta.sender or "",
        brand_map,
    ) is not None


def calibrate_llm_identity_result(
    meta: EmailMeta,
    llm: dict,
    brand_map=None,
) -> dict:
    """Korrigiert KI-Falsch-Positive nur bei starker Auth + offizieller Marken-Domain."""
    if not isinstance(llm, dict):
        return llm
    if _llm_identity_verdict(llm) != "S":
        return llm
    if _layer1_blocks_llm_calibration(meta):
        return llm
    if brand_map is None:
        brand_map = effective_brand_map(None)
    if find_brand_domain_mismatch(
        meta.sender_name or "",
        meta.sender or "",
        brand_map,
    ):
        return llm
    if not _auth_strong_pass(meta):
        return llm
    if not _display_brand_matches_registrable_domain(meta, brand_map=brand_map):
        return llm
    return {
        **llm,
        "verdict": "O",
        "reason": None,
        "mismatch": False,
        "confidence": 0,
        "impersonated": None,
    }


def _detect_mailer_platform(from_domain: str) -> str:
    if not from_domain:
        return "unbekannt"
    for plat in MARKETING_PLATFORMS:
        if plat in from_domain:
            return plat
    return from_domain


def identity_llm_check(
    meta: EmailMeta,
    *,
    cfg: Optional[AuditScamLlmConfig] = None,
    db_session=None,
    manual_user_id: Optional[int] = None,
) -> Optional[dict]:
    cfg = cfg or resolve_audit_scam_llm_config(None)
    if not cfg.enabled:
        return None

    cache_key = identity_llm_cache_key(cfg, meta)
    if cache_key in _identity_llm_cache:
        return _identity_llm_cache[cache_key]

    db_hit = _load_identity_llm_db(db_session, cache_key)
    if db_hit is not None:
        _identity_llm_cache[cache_key] = db_hit
        return db_hit

    if manual_user_id is not None:
        allowed, _used = reserve_manual_llm_quota(manual_user_id)
        if not allowed:
            return None

    from_address = normalize_sender_email(meta.sender or "") or "(leer)"
    display = (meta.sender_name or "").strip() or "(leer)"
    subject = (meta.subject or "").strip()[:200]

    if cfg.prompt_version >= 2:
        prompt = IDENTITY_PROMPT_V2.format(
            display_name=display,
            from_address=from_address,
            subject=subject or "(leer)",
        )
    else:
        _rt = getattr(meta, "reply_to", None)
        reply_domain = extract_domain(_rt or "") if _rt else "(keine)"
        provider_spam = "ja" if meta.server_spam_flag else "nein"
        if meta.provider_junk_score is not None:
            provider_spam += f" (Junk {meta.provider_junk_score})"
        auth = (meta.auth_results or "")[:300] or "(leer)"
        list_unsub = "ja" if getattr(meta, "list_unsubscribe", None) else "nein"
        prompt = IDENTITY_PROMPT.format(
            display_name=display,
            from_address=from_address,
            replyto_domain=reply_domain,
            subject=subject or "(leer)",
            provider_spam=provider_spam,
            auth_summary=auth,
            list_unsub=list_unsub,
        )
    result = _audit_identity_llm_json(prompt, cfg=cfg)
    if result is not None:
        _identity_llm_cache[cache_key] = result
        _store_identity_llm_db(db_session, cache_key, result)
    return result


def _apply_gray_zone_sender_reputation(
    out: ScamEvaluation,
    meta: EmailMeta,
    *,
    brand_map,
    trusted_domains: Optional[Set[str]],
    db_session=None,
) -> None:
    """DNS/RDAP nur für Grauzonen-Kandidaten (LLM-Gate), mit Scan-Budget."""
    global _gray_dns_lookups_this_scan, _gray_rdap_lookups_this_scan
    from src.services.brand_domain_policy import (
        host_matches_official_domain,
        registrable_domain_from_host,
    )
    from src.services.domain_reputation import (
        audit_scam_rdap_sender_enabled,
        lookup_dns_reachable,
        lookup_rdap_registration_date,
    )

    trusted_set = set(trusted_domains) if trusted_domains else set()
    extra: List[str] = []

    def _on_trusted_or_official(host: str) -> bool:
        if not host:
            return True
        if host in trusted_set or any(host.endswith("." + t) for t in trusted_set):
            return True
        for officials in (brand_map or {}).values():
            if host_matches_official_domain(host, officials):
                return True
        return False

    from_domain = extract_domain(meta.sender or "")
    _rt = getattr(meta, "reply_to", None)
    reply_domain = extract_domain(_rt or "") if _rt else ""
    for dom in {from_domain, reply_domain} - {""}:
        if _on_trusted_or_official(dom):
            continue
        reg = registrable_domain_from_host(dom) or dom
        if _gray_dns_lookups_this_scan < GRAY_DNS_MAX_PER_SCAN:
            _gray_dns_lookups_this_scan += 1
            dns_st, _ = lookup_dns_reachable(reg, db_session)
            if dns_st == "nxdomain":
                out.transport_score = min(
                    TRANSPORT_SCORE_CAP, out.transport_score + 15
                )
                extra.append(f"Transport: Absender-Domain {reg} NXDOMAIN")
        if audit_scam_rdap_sender_enabled() and _gray_rdap_lookups_this_scan < GRAY_RDAP_MAX_PER_SCAN:
            _gray_rdap_lookups_this_scan += 1
            reg_dt, _ = lookup_rdap_registration_date(reg)
            if reg_dt:
                age = (datetime.now(timezone.utc) - reg_dt).days
                if age < 30:
                    out.transport_score = min(
                        TRANSPORT_SCORE_CAP, out.transport_score + 12
                    )
                    extra.append(f"Transport: Domain-Alter {age} Tage")
    if extra:
        out.reasons = list(out.reasons or []) + extra


def _strong_transport_evidence(meta: EmailMeta, transport_score: int) -> bool:
    if meta.server_spam_flag:
        return True
    junk = meta.provider_junk_score
    return junk is not None and junk >= 5


def _spam_empty_sender_identity(meta: EmailMeta) -> bool:
    """Server-Spam/Junk ohne Anzeigename und ohne Betreff — Verdacht ohne KI."""
    if not meta.server_spam_flag:
        junk = meta.provider_junk_score
        if junk is None or junk < 5:
            return False
    name = (meta.sender_name or "").strip()
    if name and name.lower() not in ("(leer)", "(empty)"):
        return False
    subj = (meta.subject or "").strip().lower()
    if subj and subj not in (
        "",
        "(kein betreff)",
        "(no subject)",
        "(kein subject)",
    ):
        return False
    return True


def _weak_provider_transport_hint(meta: EmailMeta, transport_score: int) -> bool:
    junk = meta.provider_junk_score
    if junk is not None and 2 <= junk < 5:
        return True
    return transport_score > 0 and not _strong_transport_evidence(meta, transport_score)


def _transport_evidence(transport_score: int, weak_none: bool) -> bool:
    return transport_score > 0 or weak_none


def _suspect_extra_reputation(
    meta: EmailMeta,
    *,
    brand_map,
    trusted_domains: Optional[Set[str]],
    db_session,
    skip_dbl: bool,
) -> Tuple[bool, List[str]]:
    """
    Zweite Evidenzklasse nur für Verdacht-Kandidaten (≥2 Identitätsregeln):
    junge Domain (RDAP) oder DBL — ohne Transport.
    """
    if skip_dbl:
        return False, []
    from src.services.brand_domain_policy import (
        host_matches_official_domain,
        registrable_domain_from_host,
    )
    from src.services.domain_reputation import lookup_rdap_registration_date

    trusted_set = set(trusted_domains) if trusted_domains else set()
    msgs: List[str] = []

    def _on_trusted_or_official(host: str) -> bool:
        if not host:
            return True
        if host in trusted_set or any(host.endswith("." + t) for t in trusted_set):
            return True
        for officials in (brand_map or {}).values():
            if host_matches_official_domain(host, officials):
                return True
        return False

    from_domain = extract_domain(meta.sender or "")
    _rt = getattr(meta, "reply_to", None)
    reply_domain = extract_domain(_rt or "") if _rt else ""
    for dom in {from_domain, reply_domain} - {""}:
        if _on_trusted_or_official(dom):
            continue
        reg = registrable_domain_from_host(dom) or dom
        listed, dbl_reason = check_dbl(reg, db_session)
        if listed:
            msgs.append(f"Domain-Blockliste ({dbl_reason})")
            return True, msgs
        reg_dt, _ = lookup_rdap_registration_date(reg)
        if reg_dt:
            age = (datetime.now(timezone.utc) - reg_dt).days
            if age < 30:
                msgs.append(f"Domain-Alter {age} Tage")
                return True, msgs
    return False, msgs


def _layer1_decision(
    meta: EmailMeta,
    *,
    skip_dbl: bool,
    brand_map=None,
    trusted_domains: Optional[Set[str]] = None,
    db_session=None,
) -> Tuple[bool, bool, bool, int, ScamEvaluation]:
    """Returns is_scam, needs_review_boost, suggest_llm, combined_score, partial eval."""
    out = ScamEvaluation()
    if brand_map is None:
        brand_map = effective_brand_map(None)
    skip_identity = bool(getattr(meta, "skip_identity_rules", False))
    ctx = getattr(meta, "audit_known_context", None)
    if not skip_identity and ctx is not None:
        from src.services.audit_known_contacts import is_known_contact_email

        if is_known_contact_email(ctx, meta.sender or ""):
            skip_identity = True
    brand_hit = None
    b2_hit = None
    i1_hit = None
    if skip_identity:
        id_rules: List[str] = []
        id_msgs: List[str] = []
        id_score = 0
    else:
        id_rules, id_msgs, id_score = assess_identity_rules(meta, brand_map=brand_map)
        if ctx is not None:
            from src.services.audit_known_contacts import find_name_impersonation

            n1_msg = find_name_impersonation(
                ctx,
                meta.sender_name or "",
                meta.sender or "",
                meta=meta,
                firstnames=getattr(meta, "_firstname_set", None),
            )
            if n1_msg:
                id_rules.append("N1")
                id_msgs.append(n1_msg)
                id_score += 55
    transport_score, transport_line = assess_transport(meta)
    weak_none, auth_forces, auth_msgs, auth_score = _auth_summary(meta.auth_results or "")

    trusted_set = set(trusted_domains) if trusted_domains else None
    if not skip_identity:
        brand_hit = find_brand_domain_mismatch(
            meta.sender_name or "",
            meta.sender or "",
            brand_map,
            trusted_domains=trusted_set,
            label="Absender",
        )
        if brand_hit:
            id_rules.append("B1")
            id_msgs.append(brand_hit.message)
            id_score += 55
            if "E3" not in id_rules:
                lp = extract_local_part(meta.sender or "").lower()
                short_ok = True
                if E3_SHORT_LOCAL_RE.match(lp) and lp not in E3_LOCAL_STOP:
                    short_ok = _looks_like_organization_display(meta.sender_name or "")
                if (
                    short_ok
                    and _e3_private_mailbox_local(lp)
                    and not _identity_person_blocks_e3e6(
                        meta.sender_name or "", meta.sender or "", meta=meta
                    )
                ):
                    id_rules.append("E3")
                    id_msgs.append(
                        "Organisationsname, Absender wirkt wie Privatpostfach"
                    )
                    id_score += 55
        else:
            b2_hit = find_brand_token_in_unofficial_host(
                meta.sender or "",
                brand_map,
                trusted_domains=trusted_set,
            )
            if b2_hit:
                id_rules.append("B2")
                id_msgs.append(b2_hit.message)
                id_score += 55

        i1_hit = find_shared_infra_brand_local_mismatch(
            meta.sender_name or "",
            meta.sender or "",
            brand_map,
            trusted_domains=trusted_set,
        )
        if i1_hit:
            id_rules.append("I1")
            id_msgs.append(i1_hit.message)
            id_score += 55

    if _auth_strong_pass(meta) and brand_hit:
        id_msgs.append(
            "Auth bestanden, aber Domain gehört nicht zur genannten Marke"
        )

    out.identity_rules = list(id_rules)
    out.identity_score = id_score
    extra: List[str] = []

    suspect_candidate = len(set(id_rules)) >= 2
    reputation_second = False
    if suspect_candidate:
        reputation_second, rep_msgs = _suspect_extra_reputation(
            meta,
            brand_map=brand_map,
            trusted_domains=trusted_domains,
            db_session=db_session,
            skip_dbl=skip_dbl,
        )
        if rep_msgs:
            id_msgs.extend(rep_msgs)
            id_score += 40

    out.transport_score = transport_score
    has_identity = bool(id_rules)
    strong_t = _strong_transport_evidence(meta, transport_score)
    second_evidence = strong_t or auth_forces or reputation_second
    non_brand_rules = [r for r in id_rules if r not in ("B1", "B2", "I1")]
    identity_for_scam = len(set(id_rules)) >= 2 or (
        bool(brand_hit) and bool(non_brand_rules)
    )

    if _weak_provider_transport_hint(meta, transport_score):
        extra.append("Provider: niedriger Junk-Score (nur Prüfhinweis)")

    combined = id_score + transport_score + (auth_score if auth_forces else 0)
    out.layer1_score = combined
    out.layer1_flags = format_reason_lines(
        id_msgs,
        transport_line,
        auth_msgs if auth_forces else ([auth_msgs[0]] if weak_none and auth_msgs else []),
        extra=extra,
    )
    out.reasons = list(out.layer1_flags)

    def _mark_verdacht() -> Tuple[bool, bool, bool, int, ScamEvaluation]:
        out.identity_suspicion = True
        return False, False, True, combined, out

    if "E1" in id_rules:
        out.is_scam = True
        out.confidence = min(1.0, max(id_score, auth_score, 80) / 100.0)
        return True, False, False, combined, out

    if "X1" in id_rules:
        out.is_scam = True
        out.confidence = min(1.0, max(id_score, 80) / 100.0)
        return True, False, False, combined, out

    if auth_forces and has_identity:
        out.is_scam = True
        out.confidence = min(1.0, auth_score / 100.0)
        return True, False, False, combined, out

    if has_identity and second_evidence and identity_for_scam:
        out.is_scam = True
        out.confidence = min(1.0, (id_score + transport_score) / 100.0)
        return True, False, False, combined, out

    if "E5" in id_rules and strong_t:
        out.is_scam = True
        out.confidence = min(1.0, max(id_score, 75) / 100.0)
        return True, False, False, combined, out

    if strong_t and _spam_empty_sender_identity(meta):
        out.reasons = format_reason_lines(
            [],
            transport_line,
            auth_msgs[:1] if weak_none else [],
            extra=["Spam/Junk ohne Absendername und Betreff"],
        )
        return _mark_verdacht()

    if brand_hit or b2_hit or i1_hit:
        return _mark_verdacht()

    from src.services.audit_identity_helpers import (
        identity_rules_warrant_suspicion,
        is_curated_inbox_context,
    )

    force_verdacht = {"E9", "E8"} & set(id_rules)
    if force_verdacht:
        return _mark_verdacht()

    if identity_rules_warrant_suspicion(id_rules, strong_transport=strong_t):
        if is_curated_inbox_context(meta) and not strong_t:
            pass
        else:
            return _mark_verdacht()

    if id_score >= LAYER1_AUTO_SCAM and not second_evidence:
        if not (is_curated_inbox_context(meta) and not strong_t):
            return _mark_verdacht()

    transport_only = _transport_evidence(transport_score, weak_none) and not has_identity
    if transport_only and not has_identity:
        prior_review = out.needs_review_boost
        out.needs_review_boost = prior_review or (
            transport_score >= 10 or weak_none
        )
        out.confidence = transport_score / 100.0 if transport_score else 0.3
        out.reasons = format_reason_lines(
            [], transport_line, auth_msgs[:1] if weak_none else []
        )
        suggest = out.needs_review_boost or (
            weak_none and _looks_like_organization_display(meta.sender_name or "")
        )
        return False, out.needs_review_boost, suggest, combined, out

    if combined >= LAYER1_LLM_GATE_MIN:
        out.needs_review_boost = True
    suggest = bool(id_rules) or out.needs_review_boost or (
        weak_none and _looks_like_organization_display(meta.sender_name or "")
    )
    return False, out.needs_review_boost, suggest, combined, out


def evaluate_scam_risk(
    meta: EmailMeta,
    *,
    trusted_domains: Optional[Set[str]] = None,
    brand_map=None,
    never_scam: bool = False,
    llm_enabled: Optional[bool] = None,
    audit_llm_config: Optional[AuditScamLlmConfig] = None,
    llm_calls_remaining: Optional[List[int]] = None,
    defer_llm: bool = False,
    scan_context: Optional[AuditScanContext] = None,
    db_session=None,
) -> ScamEvaluation:
    out = ScamEvaluation()
    if never_scam:
        return out

    from_domain = extract_domain(meta.sender or "")
    if trusted_domains and from_domain:
        if from_domain in trusted_domains or any(
            from_domain.endswith("." + d) for d in trusted_domains
        ):
            return out

    skip_dbl = llm_enabled is False
    is_scam, _review, suggest_llm, combined, partial = _layer1_decision(
        meta,
        skip_dbl=skip_dbl,
        brand_map=brand_map,
        trusted_domains=trusted_domains,
        db_session=db_session,
    )
    out = partial
    if is_scam:
        return out

    if suggest_llm and not skip_dbl:
        _apply_gray_zone_sender_reputation(
            out,
            meta,
            brand_map=brand_map,
            trusted_domains=trusted_domains,
            db_session=db_session,
        )
        combined = out.identity_score + out.transport_score
        out.layer1_score = combined

    llm_cfg = audit_llm_config or resolve_audit_scam_llm_config(None)
    if llm_enabled is False:
        use_llm = False
    elif llm_enabled is True:
        use_llm = llm_cfg.enabled
    else:
        use_llm = llm_cfg.enabled

    run_llm = use_llm and suggest_llm and (
        combined >= LAYER1_LLM_GATE_MIN
        or (out.needs_review_boost and out.transport_score > 0)
    )
    budget_ok = True
    if scan_context is not None:
        if defer_llm:
            # Zeitbudget startet erst in run_deferred_llm_batch; Kandidaten während Scan sammeln
            budget_ok = True
        else:
            budget_ok = scan_context.can_call_llm()
    elif llm_calls_remaining is not None and llm_calls_remaining[0] <= 0:
        budget_ok = False

    if run_llm and not budget_ok and not defer_llm:
        run_llm = False
        if scan_context is not None:
            scan_context.skipped_candidates += 1

    if run_llm and defer_llm and scan_context is not None:
        out.llm_deferred = True
        out.llm_priority = combined
        scan_context.pending.append((meta, out))
        return out

    if run_llm:
        raw = identity_llm_check(meta, cfg=llm_cfg, db_session=db_session)
        if raw is None:
            out.llm_skip_reason = "error"
        else:
            out.llm_used = True
            usable = _llm_result_usable(raw, meta)
            if usable is None:
                out.llm_unusable = True
            else:
                out.llm_result = usable
                _merge_hybrid_llm_identity(out, meta, usable, brand_map=brand_map)
            if scan_context is not None:
                scan_context.record_llm_call()
            elif llm_calls_remaining is not None:
                llm_calls_remaining[0] = max(0, llm_calls_remaining[0] - 1)

    if not out.reasons and out.layer1_flags:
        out.reasons = list(out.layer1_flags)

    if out.identity_suspicion and not out.is_scam:
        return out

    if out.needs_review_boost and out.reasons:
        return out

    if combined >= LAYER1_LLM_GATE_MIN and not out.is_scam:
        out.needs_review_boost = True
        if not out.reasons and out.layer1_flags:
            out.reasons = list(out.layer1_flags)

    return out


def format_llm_pending_notice(
    pending: List[Tuple[Any, ScamEvaluation]],
    scan_context: AuditScanContext,
) -> str:
    """Meldung für noch offene LLM-Kandidaten (getrennt nach Grund)."""
    counts = {"budget": 0, "quota": 0, "error": 0}
    for _meta, partial in pending:
        key = partial.llm_skip_reason or "budget"
        if key not in counts:
            key = "error"
        counts[key] += 1
    parts: List[str] = []
    if counts["budget"]:
        parts.append(
            f"{counts['budget']} wegen Scan-Budget "
            f"(max. {scan_context.llm_budget} Aufrufe / "
            f"{int(scan_context.llm_time_budget_sec)}s)"
        )
    if counts["quota"]:
        parts.append(f"{counts['quota']} wegen Tageslimit")
    if counts["error"]:
        parts.append(
            f"{counts['error']} wegen LLM-Fehler (Server erreichbar?)"
        )
    if not parts:
        return ""
    total = sum(counts.values())
    return f"{total} LLM-Kandidaten nicht geprüft: " + ", ".join(parts)


def run_deferred_llm_batch(
    scan_context: AuditScanContext,
    *,
    cfg: AuditScamLlmConfig,
    db_session=None,
    manual_user_id: Optional[int] = None,
    brand_map=None,
    progress_callback=None,
) -> List[Tuple[Any, ScamEvaluation]]:
    """Sortiert Kandidaten nach Score, dedupliziert, wendet Zeit-/Zähler-Budget an."""
    updated: List[Tuple[Any, ScamEvaluation]] = []
    if not scan_context.pending:
        return updated
    scan_context.start_monotonic = time.monotonic()
    dedupe_results: dict[str, Optional[dict]] = {}
    still_pending: List[Tuple[Any, ScamEvaluation]] = []
    ordered = sorted(scan_context.pending, key=lambda item: -item[1].llm_priority)
    total = len(ordered)
    processed = 0
    manual_quota_exhausted = False

    def _emit_progress(message: str) -> None:
        if not progress_callback:
            return
        progress_callback(
            {
                "phase": "llm",
                "message": message,
                "processed": processed,
                "total": total,
                "llm_budget": scan_context.llm_budget,
                "llm_time_budget_sec": int(scan_context.llm_time_budget_sec),
            }
        )

    _emit_progress("Identitäts-KI (Batch)…")

    for meta, partial in ordered:
        if manual_quota_exhausted:
            partial.llm_skip_reason = "quota"
            still_pending.append((meta, partial))
            continue
        dk = llm_dedupe_key(meta)
        llm: Optional[dict] = None

        if dk in dedupe_results:
            entry = dedupe_results[dk]
            if entry is _DEDUPE_UNUSABLE:
                partial.llm_used = True
                partial.llm_unusable = True
                updated.append((meta, partial))
                continue
            llm = entry
        else:
            if not scan_context.can_call_llm():
                scan_context.skipped_candidates += 1
                partial.llm_skip_reason = "budget"
                still_pending.append((meta, partial))
                continue
            raw = identity_llm_check(
                meta,
                cfg=cfg,
                db_session=db_session,
                manual_user_id=manual_user_id,
            )
            if raw is None:
                partial.llm_skip_reason = "quota" if manual_user_id else "error"
                still_pending.append((meta, partial))
                if manual_user_id is not None:
                    manual_quota_exhausted = True
                continue
            scan_context.record_llm_call()
            llm = _llm_result_usable(raw, meta)
            if llm is None:
                dedupe_results[dk] = _DEDUPE_UNUSABLE
                partial.llm_used = True
                partial.llm_unusable = True
                updated.append((meta, partial))
                continue
            dedupe_results[dk] = llm

        partial.llm_used = True
        partial.llm_result = llm
        _merge_hybrid_llm_identity(partial, meta, llm, brand_map=brand_map)
        updated.append((meta, partial))
        processed += 1
        _emit_progress("Identitäts-KI (Batch)…")
    scan_context.pending = still_pending
    return updated


def run_manual_identity_check(
    meta: EmailMeta,
    *,
    user_id: int,
    audit_llm_config: AuditScamLlmConfig,
    db_session=None,
    trusted_domains: Optional[Set[str]] = None,
    brand_map=None,
) -> dict:
    """Manueller Identitäts-Check (verbraucht kein Scan-Budget, eigenes Tageslimit)."""
    layer1 = evaluate_scam_risk(
        meta,
        trusted_domains=trusted_domains,
        brand_map=brand_map,
        llm_enabled=False,
        db_session=db_session,
    )
    payload: dict = {
        "layer1_score": layer1.layer1_score,
        "layer1_flags": layer1.layer1_flags,
        "identity_rules": layer1.identity_rules,
        "is_scam_layer1": layer1.is_scam,
        "needs_review": layer1.needs_review_boost,
        "identity_suspicion": layer1.identity_suspicion,
        "quota_used": get_manual_llm_quota_used(user_id),
    }
    if layer1.identity_suspicion and not layer1.is_scam:
        payload["verdict"] = "suspicion"
        payload["reasons"] = layer1.layer1_flags or layer1.reasons
        return payload
    if layer1.is_scam:
        payload["verdict"] = "scam"
        payload["reasons"] = layer1.reasons
        payload["confidence"] = layer1.confidence
        return payload

    llm_raw = None
    if audit_llm_config.enabled:
        cache_key = identity_llm_cache_key(audit_llm_config, meta)
        cached = cache_key in _identity_llm_cache or _load_identity_llm_db(
            db_session, cache_key
        ) is not None
        if not cached:
            allowed, quota_used = check_manual_llm_quota(user_id)
            if not allowed:
                return {
                    "error": "Tageslimit für manuelle Identitäts-Checks erreicht",
                    "quota_used": quota_used,
                    "quota_limit": AUDIT_SCAM_LLM_MANUAL_MAX_PER_DAY,
                }
        llm_raw = identity_llm_check(
            meta,
            cfg=audit_llm_config,
            db_session=db_session,
            manual_user_id=user_id if not cached else None,
        )
        payload["quota_used"] = get_manual_llm_quota_used(user_id)
    llm = _llm_result_usable(llm_raw, meta) if llm_raw else None
    if llm:
        llm = calibrate_llm_identity_result(meta, llm, brand_map=brand_map)
    payload["llm"] = llm
    if llm:
        hybrid = ScamEvaluation()
        hybrid.layer1_flags = layer1.layer1_flags
        hybrid.needs_review_boost = layer1.needs_review_boost
        hybrid.identity_suspicion = layer1.identity_suspicion
        _merge_hybrid_llm_identity(hybrid, meta, llm, brand_map=brand_map)
        payload["verdict"] = "scam" if hybrid.is_scam else (
            "suspicion" if hybrid.identity_suspicion or layer1.identity_suspicion
            else ("review" if hybrid.needs_review_boost else "ok")
        )
        payload["reasons"] = hybrid.reasons
        payload["confidence"] = hybrid.confidence
    else:
        payload["verdict"] = "review" if layer1.needs_review_boost else "ok"
        payload["reasons"] = layer1.layer1_flags
    return payload
