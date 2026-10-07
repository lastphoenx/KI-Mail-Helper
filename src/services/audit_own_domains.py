"""Parsen und Validierung für «Meine Domains» (audit_own_domains)."""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from src.services.brand_domain_policy import _is_valid_official_domain

_SPLIT_TOKENS = re.compile(r"[\s,;]+")


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


def clean_own_domains_for_save(items: Sequence) -> Tuple[List[str], List[str]]:
    """Returns (cleaned unique domains, validation errors)."""
    errors: List[str] = []
    cleaned: List[str] = []
    seen = set()
    for raw in expand_own_domain_tokens(items):
        if any(ch.isspace() for ch in raw):
            errors.append(f"Ungültige Domain (Leerzeichen): {raw!r}")
            continue
        dom = raw.strip().lower().lstrip("@").strip(".")
        if not dom:
            continue
        if "." not in dom:
            errors.append(f"Kein gültiger Domainname (Punkt fehlt): {raw!r}")
            continue
        if not _is_valid_official_domain(dom):
            errors.append(f"Ungültige Domain: {raw!r}")
            continue
        if dom in seen:
            continue
        seen.add(dom)
        cleaned.append(dom)
    return cleaned, errors
