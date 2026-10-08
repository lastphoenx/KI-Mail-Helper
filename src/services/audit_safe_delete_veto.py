"""Harte Vetos: «Sicher löschbar» → «Prüfen» (Datenverlust vermeiden)."""

from __future__ import annotations

import re
from typing import List, Optional, Set

from src.services.audit_scam_detection import (
    SENT_FOLDER_NAMES,
    normalize_sender_email,
    should_never_scam,
)

DRAFT_FOLDER_NAMES = frozenset(
    {
        "drafts",
        "draft",
        "entwürfe",
        "entwurf",
        "entw&apw-rfe",
        "brouillons",
        "borrador",
    }
)

AUDIT_MANDATORY_EXCLUDE_TAIL_NAMES = SENT_FOLDER_NAMES | DRAFT_FOLDER_NAMES

SENT_FOLDER_PREFIXES = (
    "sent",
    "gesendet",
    "gesendete",
    "envoy",
    "inviati",
)
DRAFT_FOLDER_PREFIXES = (
    "draft",
    "entw",
    "brouillon",
    "borrador",
)

REPLY_SUBJECT_RE = re.compile(r"^\s*(re|aw|sv|vs|antw)\s*[:]\s*", re.I)

SAFE_DELETE_VETO_SUBJECT_RE = re.compile(
    r"(?i)"
    r"("
    r"ticket|support[-\s]?fall|case\s*#|#\d{4,}|"
    r"sicherheits(?:warnung|information|hinweis|alert)|security\s+alert|"
    r"login\s+attempt|anmeldung|neue\s+anmeldung|"
    r"passwort|password|zugang|account\s+compromised|gehackt|compromised|"
    r"\bkonto\b|"
    r"bestätig|bestätigen|confirm(?:ation)?|verifizier|verification|"
    r"\bihr\s+code\b|\bcode\s*:\s*\d|"
    r"mahnung|zahlung(?:serinnerung)?|zahlung\s+ausstehend|payment\s+reminder|overdue|"
    r"rechnung(?:en)?|invoice|faktura|fattura|"
    r"vertrag|contratto|bolletta|quittung|ricevuta|"
    r"garantie|garantia|rückerstattung|rueckerstattung|refund|stornierung|"
    r"importkosten|\bzoll\b|customs|auftragsnummer|order\s*#|"
    r"\babo\b|subscription|konfiguration|configuration|"
    r"bestellung|bestell(?:ung)?\s+wurde|order\s+confirm|\blieferung\b|"
    r"termin(?:bestätigung)?|appointment|"
    r"frist|deadline|rappel|\bpayment\b(?!\w)|"
    r"offerte|angebot\s+für|angebot\s+arbeiten|\bwarnung\b"
    r")"
)

FINANCIAL_BILLING_SIGNAL_RE = re.compile(
    r"(?i)"
    r"("
    r"\bgebühr(?:en)?(?:information(?:en)?)?\b|"
    r"\babrechnung(?:en)?\b|"
    r"\bbilling\b|"
    r"\bkontoauszug\b|"
    r"\bsaldo\b|"
    r"\bwallet\b|"
    r"\bverlänger\w*\b|"
    r"\brenewal\b|"
    r"\brenew\b|"
    r"\bfees?\b"
    r")"
)

BILLING_SENDER_LOCAL_RE = re.compile(
    r"(?i)^(billing|invoice|rechnung|payments?|accounting|finance)$"
)


def _financial_billing_signal(info) -> bool:
    subject = getattr(info, "subject", "") or ""
    sender_name = getattr(info, "sender_name", "") or ""
    sender = normalize_sender_email(getattr(info, "sender", "") or "") or ""
    local = sender.split("@", 1)[0] if "@" in sender else ""
    haystack = f"{subject}\n{sender_name}"
    if FINANCIAL_BILLING_SIGNAL_RE.search(haystack):
        return True
    if local and BILLING_SENDER_LOCAL_RE.match(local):
        return True
    return False


def _folder_segment_is_sent_or_draft(segment: str) -> bool:
    seg = (segment or "").strip().lower()
    if not seg:
        return False
    if seg in AUDIT_MANDATORY_EXCLUDE_TAIL_NAMES:
        return True
    for prefix in SENT_FOLDER_PREFIXES:
        if seg.startswith(prefix):
            return True
    for prefix in DRAFT_FOLDER_PREFIXES:
        if seg.startswith(prefix):
            return True
    return False


def folder_tail_lower(folder: str) -> str:
    if not folder:
        return ""
    tail = folder.replace("\\", "/").split("/")[-1].strip().lower()
    return tail


def is_sent_or_drafts_folder(folder: Optional[str]) -> bool:
    if not folder:
        return False
    norm = folder.replace("\\", "/")
    for segment in re.split(r"[/\.]", norm):
        if _folder_segment_is_sent_or_draft(segment):
            return True
    return False


def mandatory_audit_exclude_folder_names(all_folder_names: List[str]) -> List[str]:
    """Ordner, die immer vom Scan ausgeschlossen sind (Gesendet/Entwürfe)."""
    out: List[str] = []
    for name in all_folder_names:
        if is_sent_or_drafts_folder(name):
            out.append(name)
    return out


def safe_delete_veto_reason(
    info,
    *,
    account_email: Optional[str] = None,
    own_domains: Optional[Set[str]] = None,
    own_addresses: Optional[Set[str]] = None,
    is_user_trusted: bool = False,
    is_marketing: bool = False,
) -> Optional[str]:
    """Ein Grund genügt — Mail darf nicht «sicher löschbar» bleiben."""
    from src.services.audit_identity_helpers import is_curated_inbox_context
    from src.services.audit_quality_rules import (
        aged_success_applies,
        aged_transaction_applies,
        has_bulk_signal,
        alarm_counts_as_important,
        provider_spam_newsletter_safe,
    )

    folder = getattr(info, "folder", "") or ""
    subject = getattr(info, "subject", "") or ""
    if alarm_counts_as_important(info):
        return "Betriebs-/Alarmmeldung"

    if is_sent_or_drafts_folder(folder):
        return "Ordner Gesendet/Entwürfe (kein Lösch-Audit)"

    if is_curated_inbox_context(info):
        return "Wichtiger Ordner (Konfiguration)"

    bulk = has_bulk_signal(info)
    aged_ok = aged_success_applies(info)
    aged_txn = aged_transaction_applies(info)
    if (
        is_marketing
        and not provider_spam_newsletter_safe(info)
        and (
            getattr(info, "server_spam_flag", False)
            or (
                getattr(info, "spam_score", None) is not None
                and getattr(info, "spam_score", None) >= 5.0
            )
        )
    ):
        return "Provider-Spam trotz Newsletter-Merkmalen"

    if not aged_ok and should_never_scam(
        info,
        account_email=account_email,
        own_domains=own_domains,
        own_addresses=own_addresses,
        folder=folder,
    ):
        return "Eigene Adresse oder Domain"

    reasons = list(getattr(info, "reasons", None) or [])
    reason_blob = " ".join(reasons).lower()
    if getattr(info, "is_reply", False) or "konversation" in reason_blob:
        return "Teil einer Konversation"
    if REPLY_SUBJECT_RE.search(subject):
        return "Antwort-Betreff (Re:/AW:)"

    if not aged_ok and (is_user_trusted or "vertrauenswürdig" in reason_blob):
        return "Vertrauenswürdiger Absender"

    from src.services.audit_identity_helpers import DOCUMENT_SUBJECT_RE

    subject_protected = bool(
        SAFE_DELETE_VETO_SUBJECT_RE.search(subject) or DOCUMENT_SUBJECT_RE.search(subject)
    )
    if subject_protected and not bulk and not aged_txn:
        return "Betreff: geschütztes Muster (Ticket/Sicherheit/Zahlung/Angebot)"

    has_unsub = bool(getattr(info, "has_list_unsubscribe", False))
    if not has_unsub and not is_marketing and _financial_billing_signal(info):
        return "Finanz-/Abrechnungsmail ohne Newsletter-Kontext"

    flags = getattr(info, "flags", None) or []
    if "\\Flagged" in flags or "$Flagged" in flags:
        return "Als wichtig markiert (Flag)"

    doc_in_subject = subject_protected and not bulk and not aged_txn
    if getattr(info, "has_attachments", False):
        if doc_in_subject:
            return "Anhang mit geschütztem Betreff"
        if not has_unsub:
            return "Anhang ohne Newsletter-Kontext"
        if not is_marketing:
            return "Anhang ohne Newsletter-Einstufung"

    sender = normalize_sender_email(getattr(info, "sender", "") or "")
    if (
        not aged_ok
        and sender
        and account_email
        and sender == account_email.strip().lower()
    ):
        return "Eigene Absender-Adresse"

    from src.services.audit_own_domains import sender_on_own_domains

    if not aged_ok and own_domains and sender_on_own_domains(sender, own_domains):
        blob = reason_blob + " " + subject.lower()
        if re.search(
            r"(?i)(system-mail|system-status|erfolgsmeldung|backup|cron|"
            r"erfolgreich|completed successfully)",
            blob,
        ):
            return "Eigene Server-/Statusmail"

    return None
