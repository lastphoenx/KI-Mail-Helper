"""Bekannte Kontakte pro Mail-Account (lokal, aus Gesendet/VIP/Trusted)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from src.services.audit_identity_helpers import (
    fold_identity_ascii,
    normalize_display_name_for_identity,
    person_display_with_firstnames,
)
from src.services.audit_scam_detection import extract_domain, normalize_sender_email

logger = logging.getLogger(__name__)


@dataclass
class KnownContactContext:
    trusted_emails: Set[str] = field(default_factory=set)
    name_keys: Set[str] = field(default_factory=set)
    name_domains: Dict[str, Set[str]] = field(default_factory=dict)
    email_counts: Dict[str, int] = field(default_factory=dict)


def _name_keys(display_name: str) -> Set[str]:
    name = normalize_display_name_for_identity(display_name)
    if not name:
        return set()
    keys = {fold_identity_ascii(name)}
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        keys.add(fold_identity_ascii(f"{parts[1]} {parts[0]}"))
    return keys


def load_known_contact_context(db_session, user_id: int, account_id: int) -> KnownContactContext:
    ctx = KnownContactContext()
    if not db_session or not user_id:
        return ctx
    try:
        import importlib

        from src.services.brand_domain_policy import registrable_domain_from_host

        models = importlib.import_module(".02_models", "src")
        if hasattr(models, "AuditKnownContact"):
            q = (
                db_session.query(models.AuditKnownContact)
                .filter(
                    models.AuditKnownContact.user_id == user_id,
                    models.AuditKnownContact.account_id == account_id,
                    models.AuditKnownContact.is_active.is_(True),
                )
            )
            for row in q:
                em = (row.email_normalized or "").lower()
                if not em:
                    continue
                cnt = int(row.mail_count or 0)
                ctx.email_counts[em] = cnt
                if cnt >= 2 or row.source in ("vip", "trusted", "reply"):
                    ctx.trusted_emails.add(em)
                for k in _name_keys(row.display_name or ""):
                    ctx.name_keys.add(k)
                    reg = registrable_domain_from_host(
                        extract_domain(row.email_normalized or "")
                    )
                    if reg:
                        ctx.name_domains.setdefault(k, set()).add(reg.lower())
        vip_q = (
            db_session.query(models.AuditVIPSender)
            .filter(
                models.AuditVIPSender.user_id == user_id,
                models.AuditVIPSender.is_active.is_(True),
            )
        )
        if account_id:
            vip_q = vip_q.filter(
                (models.AuditVIPSender.account_id == account_id)
                | (models.AuditVIPSender.account_id.is_(None))
            )
        for vip in vip_q:
            pat = (vip.sender_pattern or "").lower()
            if "@" in pat:
                ctx.trusted_emails.add(normalize_sender_email(pat))
            ctx.trusted_emails.add(pat)
        if hasattr(models, "AuditTrustedDomain"):
            td_q = (
                db_session.query(models.AuditTrustedDomain)
                .filter(
                    models.AuditTrustedDomain.user_id == user_id,
                    models.AuditTrustedDomain.is_active.is_(True),
                )
            )
            if account_id:
                td_q = td_q.filter(
                    (models.AuditTrustedDomain.account_id == account_id)
                    | (models.AuditTrustedDomain.account_id.is_(None))
                )
            for td in td_q:
                dom = (td.domain or "").lower().strip(".")
                if dom:
                    ctx.trusted_emails.add(f"domain:{dom}")
        if hasattr(models, "TrustedSender"):
            ts_q = db_session.query(models.TrustedSender).filter(
                models.TrustedSender.user_id == user_id,
            )
            if account_id and hasattr(models.TrustedSender, "account_id"):
                ts_q = ts_q.filter(
                    (models.TrustedSender.account_id == account_id)
                    | (models.TrustedSender.account_id.is_(None))
                )
            for ts in ts_q:
                pat = (ts.sender_pattern or "").lower()
                ptype = (getattr(ts, "pattern_type", None) or "exact").lower()
                if ptype == "exact" and "@" in pat:
                    ctx.trusted_emails.add(normalize_sender_email(pat))
                elif ptype in ("email_domain", "domain"):
                    dom = pat.lstrip("@").strip(".")
                    if dom:
                        ctx.trusted_emails.add(f"domain:{dom}")
    except Exception as e:
        logger.debug("known contacts load failed: %s", e)
    return ctx


def is_known_contact_email(ctx: KnownContactContext, sender: str) -> bool:
    em = normalize_sender_email(sender or "")
    if not em:
        return False
    if em in ctx.trusted_emails:
        return True
    if ctx.email_counts.get(em, 0) >= 2:
        return True
    dom = em.split("@")[-1] if "@" in em else ""
    if dom and f"domain:{dom}" in ctx.trusted_emails:
        return True
    if dom:
        for marker in ctx.trusted_emails:
            if marker.startswith("domain:") and (
                dom == marker[7:] or dom.endswith("." + marker[7:])
            ):
                return True
    return False


def _display_name_matches_known_name(ctx: KnownContactContext, display_name: str) -> bool:
    keys = _name_keys(display_name)
    if not keys:
        return False
    return any(k in ctx.name_keys for k in keys)


def _sender_domain_known_for_display_name(
    ctx: KnownContactContext,
    display_name: str,
    sender: str,
) -> bool:
    from src.services.brand_domain_policy import registrable_domain_from_host

    reg = registrable_domain_from_host(extract_domain(sender or ""))
    if not reg:
        return False
    reg = reg.lower()
    for k in _name_keys(display_name):
        for known in ctx.name_domains.get(k, set()):
            if reg == known or reg.endswith("." + known):
                return True
    return False


def find_name_impersonation(
    ctx: KnownContactContext,
    display_name: str,
    sender: str,
    *,
    meta=None,
    firstnames: Optional[Set[str]] = None,
) -> Optional[str]:
    em = normalize_sender_email(sender or "")
    if not em or is_known_contact_email(ctx, em):
        return None
    if meta is not None:
        if getattr(meta, "has_list_unsubscribe", False) or getattr(
            meta, "list_unsubscribe", None
        ):
            return None
    if not _display_name_matches_known_name(ctx, display_name):
        return None
    if not person_display_with_firstnames(display_name, firstnames):
        return None
    if _sender_domain_known_for_display_name(ctx, display_name, sender):
        return None
    return "Bekannter Personenname, unbekannte Absender-Adresse"
