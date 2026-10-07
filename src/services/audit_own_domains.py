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
