"""Hilfsfunktionen Identität (Rollen-Local-Parts, Person, INBOX-Kontext)."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Set

from src.services.audit_scam_detection import extract_local_part

ROLE_LOCAL_PARTS = frozenset(
    {
        "noreply",
        "no-reply",
        "no_reply",
        "donotreply",
        "do-not-reply",
        "donot-reply",
        "info",
        "news",
        "newsletter",
        "support",
        "service",
        "customerservice",
        "customer.service",
        "customer-service",
        "event-mailings",
        "event",
        "mailings",
        "mailer",
        "billing",
        "hello",
        "contact",
        "office",
        "team",
        "admin",
        "sales",
        "help",
        "notifications",
        "notification",
    }
)

ORG_NAME_WORDS = ROLE_LOCAL_PARTS | {
    "team",
    "support",
    "service",
    "gmbh",
    "ag",
    "bank",
    "newsletter",
    "kundenservice",
    "hotline",
    "store",
    "shop",
    "ticket",
    "deutschlandticket",
}

INVOICE_SUBJECT_RE = re.compile(
    r"(?i)(rechnung|invoice|faktura|fattura|bill|quittung|ricevuta|kopie\s+rechnung)"
)

DOCUMENT_SUBJECT_RE = re.compile(
    r"(?i)("
    r"vertrag|contratto|bolletta|fattura|quittung|ricevuta|garantie|garantia|"
    r"rückerstattung|rueckerstattung|refund|importkosten|\bzoll\b|customs|"
    r"auftragsnummer|order\s*#|\babo\b|subscription|case\s*#|konfiguration|"
    r"configuration|rappel|\bpayment\b(?!\w)|mahnung|zahlung|stornierung|"
    r"wasserrechnung|\blieferung\b|"
    r"sicherheits(?:warnung|information|hinweis)|security\s+alert|\bwarnung\b"
    r")"
)


def fold_identity_ascii(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return s


def normalize_display_name_for_identity(display_name: str) -> str:
    n = (display_name or "").strip()
    for _ in range(3):
        n2 = re.sub(r'^[\s"\']+|[\s"\']+$', "", n)
        if n2 == n:
            break
        n = n2
    n = n.strip()
    if n and re.search(r"[A-Za-zÄÖÜäöü]", n) and not re.search(r"[a-zäöü]", n):
        n = " ".join(part.lower() for part in n.split())
    return n


def is_functional_role_local(sender: str) -> bool:
    lp = extract_local_part(sender or "").lower().split("+")[0]
    if not lp:
        return False
    if lp in ROLE_LOCAL_PARTS:
        return True
    compact = lp.replace(".", "").replace("-", "").replace("_", "")
    for role in ROLE_LOCAL_PARTS:
        rc = role.replace(".", "").replace("-", "").replace("_", "")
        if compact == rc:
            return True
    if re.match(r"^no[-_.]?reply", lp):
        return True
    if re.match(r"^donot[-_.]?reply", lp):
        return True
    return False


def _local_compact(sender: str) -> str:
    lp = extract_local_part(sender or "").lower()
    return lp.replace(".", "").replace("-", "").replace("_", "").split("+")[0]


def _firstname_in_set(word: str, fn_set: Set[str]) -> bool:
    w = fold_identity_ascii(word)
    if not w:
        return False
    if w in fn_set:
        return True
    if "ue" in w and w.replace("ue", "u") in fn_set:
        return True
    return w.replace("u", "ue") in fn_set


def person_display_with_firstnames(
    display_name: str,
    firstnames: Optional[Set[str]] = None,
) -> bool:
    """Person = Listen-Vorname + mindestens ein weiteres Namenswort (kein Rollen-/Firmenwort)."""
    fn_set = firstnames or set()
    if not fn_set:
        return False
    name = normalize_display_name_for_identity(display_name)
    if not name:
        return False
    words = [w for w in re.split(r"\s+", name) if w]
    if len(words) < 2:
        return False
    if any(fold_identity_ascii(w) in ORG_NAME_WORDS or w.lower() in ORG_NAME_WORDS for w in words):
        return False
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        for part in parts:
            pw = [x for x in part.split() if x]
            if len(pw) >= 1 and _firstname_in_set(pw[0], fn_set):
                return True
        return False
    return _firstname_in_set(words[0], fn_set)


def local_reflects_person_name(display_name: str, sender: str) -> bool:
    """Nachname/Name im Local-Part (ü/ue-normalisiert)."""
    lp = fold_identity_ascii(_local_compact(sender))
    if not lp:
        return False
    name = normalize_display_name_for_identity(display_name)
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        tokens = [fold_identity_ascii(p) for p in parts if p]
        for tok in tokens:
            for word in tok.split():
                if len(word) >= 4 and word in lp:
                    return True
        return False
    for word in name.split():
        w = fold_identity_ascii(word)
        if len(w) >= 4 and w in lp:
            return True
    return False


def is_curated_inbox_context(meta) -> bool:
    """Eigene Ablage — ohne Spam/Junk keine Identitäts-Verdacht-Kachel."""
    if getattr(meta, "server_spam_flag", False):
        return False
    junk = getattr(meta, "provider_junk_score", None)
    if junk is not None and junk >= 5:
        return False
    folder = (getattr(meta, "folder", "") or "").replace("\\", "/").lower()
    if not folder.startswith("inbox"):
        return False
    if folder in ("inbox",):
        return True
    markers = ("wichtig", "dringend", "informativ", "important", "urgent")
    return any(m in folder for m in markers)


def identity_rules_warrant_suspicion(
    id_rules: list,
    *,
    strong_transport: bool,
) -> bool:
    hard = {"B1", "B2", "I1", "E1", "E3", "E4", "E5", "E8", "E9"}
    s = set(id_rules or [])
    if s & hard:
        return True
    soft_only = s <= {"E6", "E7", "N1"} and bool(s)
    if soft_only:
        return bool(strong_transport)
    if strong_transport and len(s) >= 2:
        return True
    if strong_transport and (s - {"E6", "E7", "N1"}):
        return True
    return False
