"""Generische Qualitätsregeln für Ordner-Audit.

Kontospezifische Werte (Ordnermuster, Alter in Tagen, VIP, Marken, Domains)
kommen aus der DB/UI. Hier nur sprachliche Datentabellen und reine Entscheidungen.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

DEFAULT_SUCCESS_SAFE_AFTER_DAYS = 30
DEFAULT_TRANSACTION_SAFE_AFTER_DAYS = 30

# Betriebs-/Alarmmeldungen — nie «sicher löschbar» (auch nicht über Wiederholt-Absender).
OPERATIONAL_ALARM_TOKENS: tuple[str, ...] = (
    "offline",
    "alert",
    "warning",
    "failed",
    "failure",
    "error",
    "errors",
    "expired",
    "down",
    "disk",
    "fehler",
    "warnung",
    "ausgefallen",
    "stoerung",
    "störung",
    "alarme",
    "allarme",
    "erreur",
    "avertissement",
    "panne",
    "echec",
    "échec",
    "fallito",
    "scaduto",
    "ausfall",
)

# Marke + dieses Wort im selben Token («marke» + «bank» = «markebank»).
BRAND_COMPOUND_SUFFIXES = frozenset(
    {
        "bank",
        "service",
        "support",
        "team",
        "group",
        "schweiz",
        "suisse",
        "svizzera",
        "switzerland",
    }
)

# Harte Treffer: VIP darf sie nicht ausblenden.
HARD_BRAND_RULES = frozenset({"B1", "B2", "I1", "E10", "E1", "X1"})

_ALARM_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:"
    + "|".join(re.escape(tok) for tok in OPERATIONAL_ALARM_TOKENS)
    + r")(?![a-z0-9])"
)

SUCCESS_STATUS_TOKENS: tuple[str, ...] = (
    "erfolgreich",
    "successful",
    "completed successfully",
    "package updates",
    "package update",
    "no updates available",
    "backup created",
    "backup successful",
    "backup complete",
    "backup status",
    "rsync",
    "garbage collect",
    "verify datastore",
    "vzdump",
)

_ROUTINE_REVIEW_RE = re.compile(
    r"(?i)(package\s+updates?|no updates available|server\s+job|scan to e-?mail)"
)

_TRANSACTION_STATUS_RE = re.compile(
    r"(?i)("
    r"\bzugestellt\b|\bversandt\b|\bversendet\b|\bversandbereit\b|"
    r"\bunterwegs\b|\bshipped\b|\bdelivered\b|\bdispatched\b|"
    r"\bon its way\b|sendungsstatus|sendungsnummer"
    r")"
)

# Betreff-Schutz, mehrsprachig (DE/EN plus FR/IT für CH-Postfächer).
SENSITIVE_SUBJECT_TOKENS: tuple[str, ...] = (
    "sicherheit",
    "security",
    "sécurité",
    "securite",
    "sicurezza",
    "passwort",
    "password",
    "privatkonto",
    "konto",
    "account",
    "compte",
    "conto",
    "verifizierung",
    "verification",
    "vérification",
    "verifica",
    "login",
    "zugang",
    "rechnung",
    "invoice",
    "facture",
    "fattura",
    "bestellung",
    "commande",
    "ordine",
    "payment",
    "paiement",
    "pagamento",
    "refund",
    "rückerstattung",
    "rueckerstattung",
)

_SENSITIVE_SUBJECT_RE = re.compile(
    r"(?i)(?:verifiz|(?<![a-z0-9])(?:"
    + "|".join(re.escape(tok) for tok in SENSITIVE_SUBJECT_TOKENS)
    + r")(?![a-z0-9]))"
)

_REPLY_SUBJECT_RE = re.compile(r"^\s*(re|aw|sv|vs|antw)\s*[:]\s*", re.I)


def account_domain_counts_as_own(domain: str) -> bool:
    """Login-Freemail ist keine eigene Domain (Fremd-Absender derselben Domain bleiben prüfbar)."""
    from src.services.brand_domain_policy import registrable_domain_from_host
    from src.services.shared_mail_infrastructure import FREEMAIL_REGISTRABLE

    host = (domain or "").lower().strip().strip(".")
    if not host:
        return False
    reg = (registrable_domain_from_host(host) or host).lower()
    return reg not in FREEMAIL_REGISTRABLE


def clamp_age_days(value, default: int = DEFAULT_SUCCESS_SAFE_AFTER_DAYS) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < 1:
        return 1
    if n > 3650:
        return 3650
    return n


def clean_extra_words(items) -> list[str]:
    """Eigene Wörter: kurz, ohne Adresse oder Domain."""
    out: list[str] = []
    seen = set()
    for item in items or []:
        raw = str(item or "").strip()
        if not raw or len(raw) > 40 or "@" in raw or "." in raw:
            continue
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
        if len(out) >= 80:
            break
    return out


def parse_word_lists(raw) -> dict:
    """Systemliste bleibt im Code. Hier nur added und disabled pro Liste."""
    empty = {
        "sensitive": {"added": [], "disabled": []},
        "alarm": {"added": [], "disabled": []},
        "success": {"added": [], "disabled": []},
    }
    if not isinstance(raw, dict):
        return empty
    for key in empty:
        block = raw.get(key) if isinstance(raw.get(key), dict) else {}
        empty[key]["added"] = clean_extra_words(block.get("added"))
        empty[key]["disabled"] = clean_extra_words(block.get("disabled"))
    return empty


def effective_tokens(system: Sequence[str], word_lists, key: str) -> tuple[str, ...]:
    lists = parse_word_lists(word_lists)
    block = lists.get(key) or {"added": [], "disabled": []}
    disabled = {item.lower() for item in block["disabled"]}
    out: list[str] = []
    seen = set()
    for tok in system:
        if tok.lower() in disabled:
            continue
        if tok.lower() not in seen:
            seen.add(tok.lower())
            out.append(tok)
    for extra in block["added"]:
        if extra.lower() in seen or extra.lower() in disabled:
            continue
        seen.add(extra.lower())
        out.append(extra)
    return tuple(out)


def _phrase_re(tokens: Sequence[str], *, prefix: str = ""):
    parts = []
    if prefix:
        parts.append(prefix)
    if tokens:
        parts.append(
            r"(?<![a-z0-9])(?:"
            + "|".join(re.escape(tok) for tok in tokens)
            + r")(?![a-z0-9])"
        )
    if not parts:
        return re.compile(r"a^")
    return re.compile(r"(?i)(?:" + "|".join(parts) + r")")


def subject_has_operational_alarm(subject: str, word_lists=None) -> bool:
    tokens = effective_tokens(OPERATIONAL_ALARM_TOKENS, word_lists, "alarm")
    return bool(_phrase_re(tokens).search(subject or ""))


def alarm_counts_as_important(info) -> bool:
    """Alarmwörter nur ohne Werbe-Signal (List-Unsubscribe) Richtung Wichtig.

    Werbung mit Bulk bleibt Werbung. Eigene, vertraute und sonstige
    Nicht-Werbe-Absender behalten den Alarm.
    """
    subject = getattr(info, "subject", "") or ""
    if not subject_has_operational_alarm(subject, getattr(info, "word_lists", None)):
        return False
    if has_bulk_signal(info):
        return False
    return True


def is_success_status_subject(subject: str, word_lists=None) -> bool:
    if subject_has_operational_alarm(subject, word_lists):
        return False
    tokens = effective_tokens(SUCCESS_STATUS_TOKENS, word_lists, "success")
    return bool(_phrase_re(tokens).search(subject or ""))


def is_routine_status_subject(subject: str, word_lists=None) -> bool:
    """Status ohne Alarm: prüfen, nicht automatisch wichtig."""
    if subject_has_operational_alarm(subject, word_lists):
        return False
    return bool(_ROUTINE_REVIEW_RE.search(subject or ""))


def is_transaction_status_subject(subject: str, word_lists=None) -> bool:
    if subject_has_operational_alarm(subject, word_lists):
        return False
    return bool(_TRANSACTION_STATUS_RE.search(subject or ""))


def subject_is_sensitive(subject: str, word_lists=None) -> bool:
    tokens = effective_tokens(SENSITIVE_SUBJECT_TOKENS, word_lists, "sensitive")
    return bool(_phrase_re(tokens, prefix="verifiz").search(subject or ""))


def email_age_days(when: Optional[datetime]) -> Optional[int]:
    if when is None:
        return None
    now = datetime.now(timezone.utc) if when.tzinfo else datetime.now()
    try:
        return (now - when).days
    except TypeError:
        return None


def compound_brand_token(brand_key: str, token: str) -> bool:
    """True wenn token = Marke + Suffixwort aus der Datentabelle."""
    bk = (brand_key or "").lower()
    tok = (token or "").lower()
    if len(bk) < 4 or not tok.startswith(bk):
        return False
    rest = tok[len(bk) :]
    return rest in BRAND_COMPOUND_SUFFIXES


def normalize_folder_path(folder: str) -> str:
    raw = (folder or "").replace("\\", "/").strip()
    if not raw:
        return ""
    parts = []
    for seg in raw.split("/"):
        for piece in seg.split("."):
            p = piece.strip().lower()
            if p:
                parts.append(p)
    return "/".join(parts)


def is_plain_inbox_folder(folder: str) -> bool:
    return normalize_folder_path(folder) == "inbox"


def clean_folder_patterns(items: Sequence) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items or []:
        raw = str(item or "").strip()
        if not raw or len(raw) > 160:
            continue
        for part in re.split(r"[\n,;]+", raw):
            p = part.strip()
            if not p or len(p) > 160:
                continue
            key = p.lower()
            if key in seen or key == "inbox":
                continue
            seen.add(key)
            out.append(p)
            if len(out) >= 40:
                return out
    return out


def folder_is_curated(folder: str, patterns: Optional[Iterable[str]]) -> bool:
    """Plain INBOX nie. Treffer nur über die pro Konto gespeicherten Muster."""
    if is_plain_inbox_folder(folder):
        return False
    path = normalize_folder_path(folder)
    if not path:
        return False
    for raw in patterns or []:
        pat = normalize_folder_path(str(raw or ""))
        if not pat or pat == "inbox":
            continue
        if pat == path or pat in path.split("/") or pat in path:
            return True
    return False


def _has_thread(info) -> bool:
    if getattr(info, "is_reply", False):
        return True
    return bool(_REPLY_SUBJECT_RE.search(getattr(info, "subject", "") or ""))


def _provider_spam(info) -> bool:
    if getattr(info, "server_spam_flag", False):
        return True
    score = getattr(info, "spam_score", None)
    if score is not None and score >= 5:
        return True
    junk = getattr(info, "provider_junk_score", None)
    return junk is not None and junk >= 5


# Angezeigter Grund = die Regel, die die Kategorie gesetzt hat.
# Identität/Scam liefern ihre eigenen Zeilen; hier nur der Ersatztext.
DECISION_REASON_TEXT = {
    "important_alarm": "Betriebs-/Alarmmeldung (nicht löschbar)",
    "important_subject": "Wichtiger Betreff",
    "important_keyword": "Wichtig: '{keyword}'",
    "safe_bulk": "Newsletter oder Marketing (Massenmail)",
    "safe_provider_newsletter": "Newsletter trotz Provider-Spam (kein Markentreffer)",
    "safe_aged_success": "Erfolgs-/Statusmeldung (älter als {days} Tage)",
    "safe_aged_transaction": "Sendungsstatus älter als {days} Tage",
    "review_transaction_hold": "Sendungsstatus (löschbar nach {days} Tagen)",
    "review_routine": "Routine-Status (kein Wichtig-Signal)",
    "review_veto": "Löschschutz: {veto}",
    "important_veto_alarm": "Löschschutz: {veto}",
    "review_db_safe_pattern": "Safe-Pattern (DB, kein List-Unsubscribe)",
    "identity_suspicion": "Verdacht: Absender passt nicht zur genannten Marke",
    "scam": "Scam: Absender passt nicht zur genannten Marke",
}


def reasons_for_decision(rule_id: str, *, identity_lines=None, **fields) -> list:
    """Eine Zeile aus der Entscheidungsregel. Keine angesammelten Score-Bausteine."""
    if rule_id in ("identity_suspicion", "scam"):
        lines = [str(line) for line in (identity_lines or []) if line]
        if lines:
            return lines
    text = DECISION_REASON_TEXT[rule_id]
    if fields:
        text = text.format(**fields)
    return [text]


def with_domain_badge(lines, badge) -> list:
    """Identitätszeilen behalten das Domain-Badge, auch wenn es nicht in layer1_flags steht."""
    out = [str(line) for line in (lines or []) if line]
    text = str(badge or "").strip()
    if text and text not in out:
        out.append(text)
    return out


def has_bulk_signal(info) -> bool:
    if getattr(info, "has_list_unsubscribe", False):
        return True
    if getattr(info, "list_unsubscribe", None):
        return True
    return False


def provider_spam_newsletter_safe(info) -> bool:
    """Provider-Spam + Bulk, kein Thread, kein bekannter Kontakt, kein Markentreffer."""
    if not _provider_spam(info) or not has_bulk_signal(info):
        return False
    if _has_thread(info):
        return False
    if getattr(info, "known_contact", False):
        return False
    if getattr(info, "identity_brand_hit", False):
        return False
    return True


def aged_success_applies(info) -> bool:
    if not getattr(info, "aged_success_safe", False):
        return False
    if subject_has_operational_alarm(
        getattr(info, "subject", "") or "", getattr(info, "word_lists", None)
    ):
        return False
    return True


def aged_transaction_applies(info) -> bool:
    if not getattr(info, "aged_transaction_safe", False):
        return False
    if subject_has_operational_alarm(
        getattr(info, "subject", "") or "", getattr(info, "word_lists", None)
    ):
        return False
    if _has_thread(info):
        return False
    return True


def _e10_only(rule_ids) -> bool:
    """Marke nur im Local-Part, nicht zusätzlich in Domain oder Anzeigename."""
    rules = set(rule_ids or [])
    if "E10" not in rules:
        return False
    return not (rules & (HARD_BRAND_RULES - {"E10"}))


def brand_hit_has_warning(meta, *, auth_failed: bool = False, rule_ids=None) -> bool:
    """Hart + Warnung => Scam.

    E10 (nur Local-Part): Spam-Score >= 5 oder Auth-Fehler.
    Der Betreff allein reicht dort nicht. Domain, Unterdomäne und
    Anzeigename bleiben: auch ein sensibler Betreff ist die Warnung.
    """
    if _e10_only(rule_ids):
        if auth_failed:
            return True
        if getattr(meta, "server_spam_flag", False):
            return True
        score = getattr(meta, "spam_score", None)
        return score is not None and score >= 5
    if auth_failed:
        return True
    if _provider_spam(meta):
        return True
    return subject_is_sensitive(
        getattr(meta, "subject", "") or "", getattr(meta, "word_lists", None)
    )


def vip_suppresses_soft_identity(meta, rule_ids, *, auth_failed: bool) -> bool:
    """VIP übersteuert weiche Identität, solange Auth nicht fehlschlägt."""
    if not getattr(meta, "vip_matched", False) or auth_failed:
        return False
    return not (set(rule_ids or []) & HARD_BRAND_RULES)


def first_sentence(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    line = raw.splitlines()[0].strip()
    parts = re.split(r"(?<=[.!?])\s+", line, maxsplit=1)
    return (parts[0] or "").strip()
