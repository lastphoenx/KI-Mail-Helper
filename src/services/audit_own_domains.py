"""Parsen und Validierung für «Meine Domains» (audit_own_domains)."""

from __future__ import annotations

import re
from typing import List, Sequence, Set, Tuple

_SPLIT_TOKENS = re.compile(r"[\s,;]+")
_OWN_DOMAIN_RE = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")


def expand_own_domain_tokens(items: Sequence) -> List[str]:
    out: List[str] = []
    for item in items or []:
        raw = str(item).strip()
        if not raw:
            continue
        parts = _SPLIT_TOKENS.split(raw)
        for part in parts:
            p = part.strip()
            if p:
                out.append(p)
    return out


def normalize_own_domain_token(raw: str) -> str:
    return str(raw or "").strip().lower().lstrip("@").strip(".")


def is_valid_own_domain_syntax(domain: str) -> bool:
    """Syntax only — no Public-Suffix check (Homelab: .lan, .local, .home.arpa, …)."""
    d = normalize_own_domain_token(domain)
    if not d or len(d) > 253:
        return False
    if "." not in d:
        return False
    if not _OWN_DOMAIN_RE.fullmatch(d):
        return False
    return True


_ADDRESS_RE = re.compile(
    "^" + r"[a-z0-9._%+\-]+" + "@" + r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$"
)


def normalize_own_address(raw: str) -> str:
    from src.services.audit_scam_detection import normalize_sender_email

    return normalize_sender_email(raw or "")


def is_valid_own_address_syntax(address: str) -> bool:
    addr = normalize_own_address(address)
    if not addr or len(addr) > 254 or addr.count("@") != 1:
        return False
    return bool(_ADDRESS_RE.fullmatch(addr))


def sender_matches_own_address(sender: str, own_addresses: Optional[Set[str]]) -> bool:
    """Nur diese Adresse, nie die ganze Domain."""
    addr = normalize_own_address(sender or "")
    if not addr:
        return False
    return addr in {normalize_own_address(item) for item in (own_addresses or set()) if item}


def own_addresses_set_from_items(items: Sequence) -> Set[str]:
    cleaned, _errors = clean_own_addresses_for_save(items)
    return set(cleaned)


def clean_own_addresses_for_save(items: Sequence) -> Tuple[List[str], List[str]]:
    """Volle Adressen. Eine Freemail-Adresse gibt ihre Domain nicht frei."""
    errors: List[str] = []
    cleaned: List[str] = []
    seen = set()
    for raw in expand_own_domain_tokens(items):
        if any(ch.isspace() for ch in raw):
            errors.append(f"Ungültige Adresse (Leerzeichen): {raw!r}")
            continue
        addr = normalize_own_address(raw)
        if not addr:
            continue
        if "@" not in addr:
            errors.append(f"Keine volle Adresse (fehlt @): {raw!r}")
            continue
        if not is_valid_own_address_syntax(addr):
            errors.append(f"Ungültige Adresse: {raw!r}")
            continue
        if addr in seen:
            continue
        seen.add(addr)
        cleaned.append(addr)
    return cleaned, errors


def sender_on_own_domains(sender: str, own_domains: Optional[Set[str]]) -> bool:
    from src.services.audit_scam_detection import extract_domain, normalize_sender_email

    dom = extract_domain(normalize_sender_email(sender or "") or "")
    if not dom:
        return False
    for od in own_domains or set():
        od = str(od or "").lower().strip().strip(".")
        if not od:
            continue
        if dom == od or dom.endswith("." + od):
            return True
    return False


def own_domains_set_from_items(items: Sequence) -> Set[str]:
    """Runtime: expand legacy comma-in-one-string JSON entries."""
    out: Set[str] = set()
    for raw in expand_own_domain_tokens(items):
        if any(ch.isspace() for ch in raw):
            continue
        dom = normalize_own_domain_token(raw)
        if not is_valid_own_domain_syntax(dom):
            continue
        out.add(dom)
    return out


def clean_own_domains_for_save(items: Sequence) -> Tuple[List[str], List[str]]:
    """Returns (cleaned unique domains, validation errors)."""
    errors: List[str] = []
    cleaned: List[str] = []
    seen = set()
    for raw in expand_own_domain_tokens(items):
        if any(ch.isspace() for ch in raw):
            errors.append(f"Ungültige Domain (Leerzeichen): {raw!r}")
            continue
        dom = normalize_own_domain_token(raw)
        if not dom:
            continue
        if "." not in dom:
            errors.append(f"Kein gültiger Domainname (Punkt fehlt): {raw!r}")
            continue
        if not is_valid_own_domain_syntax(dom):
            errors.append(f"Ungültige Domain: {raw!r}")
            continue
        if dom in seen:
            continue
        seen.add(dom)
        cleaned.append(dom)
    return cleaned, errors
