"""
Zwei-Layer Scam-Erkennung für Ordner-Audit.

Layer 1: deterministische Header-/Reputation-Signale (schnell, kein LLM)
Layer 2: LLM Identitäts-Kohärenz (nur bei Verdacht / Grauzone)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Set, Tuple

import requests

from src.ollama_timeouts import ollama_chat_request_options

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
# junk:2 von GMX ist Rauschen — Gate bewusst über diesem Wert.
LAYER1_LLM_GATE_MIN = _int_env("AUDIT_SCAM_LAYER1_LLM_MIN", 40)
LLM_MISMATCH_CONFIDENCE = _int_env("AUDIT_SCAM_LLM_MISMATCH_CONF", 75)
LLM_REVIEW_CONFIDENCE = _int_env("AUDIT_SCAM_LLM_REVIEW_CONF", 40)
LLM_ENABLED_DEFAULT = _bool_env("AUDIT_SCAM_LLM_ENABLED", True)
LLM_TIMEOUT = _int_env("AUDIT_SCAM_LLM_TIMEOUT", 90)

# Minimale Regex-Liste: objektiv bösartige Mailer-Software (keine Brand-Liste)
SCAM_MAILER_RE = re.compile(r"v1p3r|darkmailer|sendblaster|spam\s*mailer", re.I)
RANDOM_FROM_RE = re.compile(r"<[a-z0-9]{16,}@", re.I)
PERSON_NAME_RE = re.compile(
    r"^[A-ZÄÖÜ][\w.'\-]+(?:\s+[A-ZÄÖÜ][\w.'\-]+)*,\s*[A-ZÄÖÜ][\w.'\-]+"
    r"|^[A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+$",
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

# Keine Marken, keine generischen Wörter wie team/support (sonst pCloud Team → LLM).
ORG_DISPLAY_HINTS = re.compile(
    r"\b(ag|gmbh|gmbh\s*&\s*co|sa|srl|inc|ltd|llc|"
    r"rückerstattung|rueckerstattung|behörde|behoerde|"
    r"bank|versicherung)\b",
    re.I,
)

DISPLAY_STOPWORDS = {
    "team", "service", "support", "newsletter", "info", "noreply", "official",
    "customer", "the", "der", "die", "das", "und", "fur", "für", "von", "via",
    "ag", "gmbh", "inc", "ltd", "llc", "sa", "srl",
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
Kopiere keine Beispieltexte.

Absendername:  {display_name}
From-Domain:   {from_domain}
Reply-To:      {replyto_domain}
Betreff:       {subject}
Versand über:  {mailer_platform}

mismatch=true nur wenn DIESE From- oder Reply-To-Domain nicht zu DIESEM Absendernamen passt
(fremde Domain, zusammengeklebte Country-TLD wie name+ch als .com, Reply-To woandershin).
mismatch=false bei normalen Firmenmails, Newslettern, Login-Hinweisen, privater Post.

JSON, sonst nichts:
{{
  "mismatch": false,
  "confidence": 0,
  "reason": null,
  "impersonated": null
}}"""


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


@dataclass
class ScamEvaluation:
    is_scam: bool = False
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    layer1_score: int = 0
    layer1_flags: List[str] = field(default_factory=list)
    llm_used: bool = False
    llm_result: Optional[dict] = None
    needs_review_boost: bool = False


# --- Spamhaus DBL (DNS, gecacht) ---

_dbl_cache: dict[str, tuple[bool, str]] = {}
_identity_llm_cache: dict[str, dict] = {}


def extract_domain(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].lower().strip(">").strip()


def check_dbl(domain: str) -> Tuple[bool, str]:
    """Spamhaus DBL via DNS. Returns (listed, reason)."""
    if not domain:
        return False, ""

    domain = domain.lower().strip(".")
    if domain in _dbl_cache:
        return _dbl_cache[domain]

    listed, reason = False, ""
    try:
        import dns.resolver

        query = f"{domain}.dbl.spamhaus.org"
        answers = dns.resolver.resolve(query, "A")
        for rdata in answers:
            code = str(rdata)
            if code in ("127.0.0.2", "127.0.0.3", "127.0.0.9"):
                listed, reason = True, f"Spamhaus DBL (Spam, {code})"
                break
            if code == "127.0.0.4":
                listed, reason = True, f"Spamhaus DBL (Phishing, {code})"
                break
            if code.startswith("127.0.0."):
                listed, reason = True, f"Spamhaus DBL ({code})"
                break
    except ImportError:
        logger.debug("dnspython nicht installiert – DBL-Check übersprungen")
    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name not in ("NXDOMAIN", "NoAnswer", "NoNameservers", "LifetimeTimeout"):
            logger.debug("DBL lookup %s: %s", domain, exc)

    _dbl_cache[domain] = (listed, reason)
    return listed, reason


def clear_audit_scam_caches() -> None:
    """Für Tests oder nach Config-Änderungen."""
    _dbl_cache.clear()
    _identity_llm_cache.clear()


def _looks_like_person_name(display_name: str) -> bool:
    name = (display_name or "").strip()
    if not name:
        return False
    return bool(PERSON_NAME_RE.match(name))


def _significant_display_tokens(display_name: str) -> List[str]:
    raw = (display_name or "").lower()
    parts = re.split(r"[^a-z0-9äöü]+", raw)
    tokens: List[str] = []
    for part in parts:
        if len(part) < 4 or part in DISPLAY_STOPWORDS:
            continue
        tokens.append(part)
    return tokens


def _glued_cctld_squat(display_name: str, *domains: str) -> Optional[str]:
    """name+Ländercode als SLD unter .com/.net — z.B. serafe+ch → serafech.com."""
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
                return f"Typosquatting: {domain} klebt '{tok}'+'{remainder}' an .{tld}"
    return None


def _looks_like_organization_display(display_name: str) -> bool:
    if not display_name or len(display_name.strip()) < 4:
        return False
    if _looks_like_person_name(display_name):
        return False
    if ORG_DISPLAY_HINTS.search(display_name):
        return True
    return len(_significant_display_tokens(display_name)) >= 2


def _detect_mailer_platform(from_domain: str) -> str:
    if not from_domain:
        return "unbekannt"
    for plat in MARKETING_PLATFORMS:
        if plat in from_domain:
            return plat
    return from_domain


def quick_header_flags(meta: EmailMeta) -> Tuple[int, List[str], bool]:
    """
    Layer 1: deterministische Signale.

    Returns:
        (score 0–100+, flags, suggest_identity_llm)
    """
    score = 0
    flags: List[str] = []
    suggest_llm = False

    auth = (meta.auth_results or "").lower()
    from_domain = extract_domain(meta.sender or "")
    reply_domain = extract_domain(meta.reply_to or "") if meta.reply_to else ""

    # --- Auth (Kombinationen, nicht dkim=none allein) ---
    if "dkim=fail" in auth:
        score += 55
        flags.append("DKIM-Signatur ungültig")
    elif "dkim=none" in auth and "dmarc=none" in auth:
        if _looks_like_organization_display(meta.sender_name or ""):
            score += 25
            flags.append("Kein DKIM + kein DMARC (Org-Anzeigename)")
            suggest_llm = True
        else:
            score += 10
            flags.append("Kein DKIM + kein DMARC")

    if "dmarc=fail" in auth:
        score += 50
        flags.append("DMARC fail")

    if "spf=fail" in auth:
        score += 45
        flags.append("SPF fail")

    # --- Scam-Software / Struktur ---
    x_mailer = meta.x_mailer or ""
    if SCAM_MAILER_RE.search(x_mailer):
        score += 80
        flags.append(f"Bekannte Scam-Software ({x_mailer[:40]})")

    from_raw = meta.sender or ""
    if RANDOM_FROM_RE.search(from_raw) or _is_random_local_part(from_raw):
        score += 40
        flags.append("Zufalls-Absenderadresse")

    to_hdr = (meta.to_header or "").lower()
    if "undisclosed" in to_hdr:
        score += 20
        flags.append("Undisclosed Recipients")

    if meta.server_spam_flag:
        score += 30
        flags.append("Provider Spam-Flag (X-Spam-Flag)")

    # GMX junk:2 ist Alltag, kein Scam-Signal. Erst ab 5 ernst nehmen.
    if meta.provider_junk_score is not None and meta.provider_junk_score >= 5:
        score += 40
        flags.append(f"Provider Junk-Score: {meta.provider_junk_score}")

    if meta.is_auto_generated and score >= 20:
        score += 15
        flags.append("Auto-generierte Massenmail")

    squat = _glued_cctld_squat(meta.sender_name or "", from_domain, reply_domain)
    if squat:
        score += 80
        flags.append(squat)

    # --- Spamhaus DBL ---
    for dom in {from_domain, reply_domain} - {""}:
        listed, dbl_reason = check_dbl(dom)
        if listed:
            score += 60
            flags.append(f"Domain {dom} in {dbl_reason}")
            break

    # Grauzone → LLM vorschlagen
    if LAYER1_LLM_GATE_MIN <= score < LAYER1_AUTO_SCAM:
        suggest_llm = True
    if suggest_llm and _looks_like_organization_display(meta.sender_name or ""):
        suggest_llm = True

    return score, flags, suggest_llm


def _is_random_local_part(sender: str) -> bool:
    if "@" not in sender:
        return False
    local = sender.split("@")[0].lower()
    local = re.sub(r"^.*<", "", local).strip("<>")
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


def _ollama_chat_json(prompt: str) -> Optional[dict]:
    base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_API_URL") or "http://127.0.0.1:11434"
    model = os.getenv("AUDIT_SCAM_LLM_MODEL") or os.getenv("OLLAMA_CHAT_MODEL")
    if not model:
        try:
            discovery = __import__(
                "src.04_model_discovery",
                fromlist=["get_default_model"],
            )
            model = discovery.get_default_model("ollama", "chat")
        except Exception:
            model = "qwen3:8b"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": ollama_chat_request_options(),
    }
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=LLM_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Audit identity LLM HTTP %s", resp.status_code)
            return None
        content = (resp.json().get("message") or {}).get("content", "")
        if not content:
            return None
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("Audit identity LLM failed: %s", type(exc).__name__)
        return None


def _llm_result_usable(llm: dict, meta: EmailMeta) -> Optional[dict]:
    """Verwirft Prompt-Leaks und halluzinierte Beispiel-Marken."""
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
        logger.info("Audit LLM: Platzhalter-Reason verworfen")
        return None
    if impersonated and LLM_PLACEHOLDER_RE.search(impersonated):
        logger.info("Audit LLM: Platzhalter-Impersonation verworfen")
        return None

    hay = " ".join(
        filter(
            None,
            [
                meta.sender_name,
                meta.sender,
                meta.reply_to,
                meta.subject,
            ],
        )
    ).lower()

    leak_needles = ("serafech", "serafe.ch", "v1p3rbox")
    blob = f"{reason} {impersonated or ''}".lower()
    for needle in leak_needles:
        if needle in blob and needle not in hay:
            logger.info("Audit LLM: Beispiel-Brand '%s' nicht in der Mail – verworfen", needle)
            return None

    return llm


def identity_llm_check(meta: EmailMeta) -> Optional[dict]:
    """Layer 2: Identitäts-Kohärenz per lokalem LLM."""
    from_domain = extract_domain(meta.sender or "")
    reply_domain = extract_domain(meta.reply_to or "") if meta.reply_to else "(keine)"
    display = (meta.sender_name or "").strip() or "(leer)"
    subject = (meta.subject or "").strip()[:200]
    platform = _detect_mailer_platform(from_domain)

    cache_key = hashlib.sha256(
        f"{display}|{from_domain}|{reply_domain}|{subject}|{platform}".encode()
    ).hexdigest()
    if cache_key in _identity_llm_cache:
        return _identity_llm_cache[cache_key]

    prompt = IDENTITY_PROMPT.format(
        display_name=display,
        from_domain=from_domain or "(leer)",
        replyto_domain=reply_domain,
        subject=subject or "(leer)",
        mailer_platform=platform,
    )
    result = _ollama_chat_json(prompt)
    if result is not None:
        _identity_llm_cache[cache_key] = result
    return result


def evaluate_scam_risk(
    meta: EmailMeta,
    *,
    trusted_domains: Optional[Set[str]] = None,
    never_scam: bool = False,
    llm_enabled: Optional[bool] = None,
) -> ScamEvaluation:
    """
    Kombiniert Layer 1 + optional Layer 2.

    trusted_domains: User-DB-Whitelist — unterdrückt SCAM wenn From-Domain trusted.
    """
    out = ScamEvaluation()
    if never_scam:
        return out

    from_domain = extract_domain(meta.sender or "")
    if trusted_domains and from_domain:
        if from_domain in trusted_domains or any(
            from_domain.endswith("." + d) for d in trusted_domains
        ):
            return out

    layer1_score, layer1_flags, suggest_llm = quick_header_flags(meta)
    out.layer1_score = layer1_score
    out.layer1_flags = list(layer1_flags)

    if layer1_score >= LAYER1_AUTO_SCAM:
        out.is_scam = True
        out.confidence = min(1.0, layer1_score / 100.0)
        out.reasons = [f"🚨 Layer-1 ({layer1_score}): {f}" for f in layer1_flags]
        return out

    use_llm = llm_enabled if llm_enabled is not None else LLM_ENABLED_DEFAULT
    run_llm = use_llm and suggest_llm and layer1_score >= LAYER1_LLM_GATE_MIN

    if run_llm:
        llm = identity_llm_check(meta)
        out.llm_used = True
        llm = _llm_result_usable(llm, meta) if llm else None
        out.llm_result = llm
        if llm:
            mismatch_raw = llm.get("mismatch")
            if isinstance(mismatch_raw, str):
                mismatch = mismatch_raw.strip().lower() in ("true", "1", "yes")
            else:
                mismatch = bool(mismatch_raw)
            try:
                conf = int(llm.get("confidence", 0))
            except (TypeError, ValueError):
                conf = 0
            reason = str(llm.get("reason") or "").strip()
            impersonated = llm.get("impersonated")

            if mismatch and conf >= LLM_MISMATCH_CONFIDENCE:
                out.is_scam = True
                out.confidence = min(1.0, conf / 100.0)
                parts = layer1_flags[:2] + ([reason] if reason else [])
                if impersonated:
                    parts.insert(0, f"🎭 Behauptet: {impersonated}")
                out.reasons = [f"🚨 {p}" for p in parts if p]
                return out

            if mismatch and conf >= LLM_REVIEW_CONFIDENCE:
                out.needs_review_boost = True
                out.confidence = conf / 100.0
                out.reasons = layer1_flags + ([f"⚠️ LLM: {reason}"] if reason else [])
                return out

    # Layer 1 mittelstark ohne LLM-Ergebnis
    if layer1_score >= LAYER1_LLM_GATE_MIN:
        out.needs_review_boost = True
        out.confidence = layer1_score / 100.0
        out.reasons = [f"⚠️ Verdacht ({layer1_score}): {f}" for f in layer1_flags]
    elif layer1_flags:
        out.reasons = layer1_flags

    return out
