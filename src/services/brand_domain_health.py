"""Marken-Domain-Health: Speichern, manueller Check, DBL-Blockliste."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from src.services.brand_domain_policy import (
    BUILTIN_BRAND_OFFICIAL_DOMAINS,
    brand_map_to_lines,
    diff_brand_maps,
    effective_brand_map,
    parse_brand_domains_text,
    registrable_domain_from_host,
    validate_brand_map,
)
from src.services.domain_reputation import (
    assess_domain_health,
    audit_scam_rdap_sender_enabled,
    brand_health_rdap_admin_disabled,
    brand_health_rdap_enabled,
    invalidate_rdap_cache_for_domain,
    resolve_brand_health_rdap,
    validate_official_domains_for_save,
)

logger = logging.getLogger(__name__)


def health_report_to_json(health: dict) -> str:
    """DB/API-sicher serialisieren (kein datetime o.ä.)."""

    def _default(obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    return json.dumps(health, ensure_ascii=False, default=_default)


def persist_brand_health_row(row, health: dict) -> None:
    row.brand_domains_health_json = health_report_to_json(health) if health else None
    row.brand_domains_health_checked_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) if health else None
    )


def iso_utc_for_api(dt: Optional[datetime]) -> Optional[str]:
    """Naive UTC aus DB → ISO mit Z für Browser (toLocaleString korrekt)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def domains_in_brand_map(brand_map: Mapping[str, List[str]]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for domains in brand_map.values():
        for dom in domains:
            d = str(dom).lower().strip(".")
            if d and d not in seen:
                seen.add(d)
                out.append(d)
    return sorted(out)


def brand_scope_stats(
    custom_map: Mapping[str, List[str]],
    health: Optional[dict] = None,
) -> Dict[str, int]:
    """Zählwerte für UI: Custom vs. System-Scan vs. Health (nur Custom-Domains)."""
    custom = dict(custom_map or {})
    effective = effective_brand_map(custom)
    custom_set = set(domains_in_brand_map(custom))
    effective_set = set(domains_in_brand_map(effective))
    system_only = effective_set - custom_set
    by_domain = dict((health or {}).get("domains") or {})
    records = sum(1 for d in custom_set if d in by_domain)
    verified = sum(
        1 for d in custom_set if domain_verified_for_list(by_domain.get(d))
    )
    pending_list = pending_verification_domains(custom, by_domain)
    query_failed = sum(
        1
        for d in custom_set
        if (by_domain.get(d) or {}).get("rdap_status") == "query_failed"
    )
    return {
        "builtin_brands": len(BUILTIN_BRAND_OFFICIAL_DOMAINS),
        "custom_brands": len(custom),
        "effective_brands": len(effective),
        "custom_domains": len(custom_set),
        "system_only_domains": len(system_only),
        "effective_domains": len(effective_set),
        "health_records": records,
        "health_verified": verified,
        "health_pending": len(pending_list),
        "health_query_failed": query_failed,
    }


def new_domains_from_maps(
    old_map: Optional[Mapping[str, List[str]]],
    new_map: Mapping[str, List[str]],
) -> List[str]:
    """Domains neu in der Map (Speichern — nur diese live prüfen)."""
    if not old_map:
        return domains_in_brand_map(new_map)
    diff = diff_brand_maps(old_map, new_map)
    out: Set[str] = set()
    for doms in (diff.get("added_domains") or {}).values():
        for d in doms:
            dd = str(d).lower().strip(".")
            if dd:
                out.add(dd)
    for brand in diff.get("new_brands") or []:
        for d in new_map.get(brand) or []:
            dd = str(d).lower().strip(".")
            if dd:
                out.add(dd)
    return sorted(out)


def _domain_passes_verification_rules(h: dict) -> bool:
    if h.get("dbl_hard_listed"):
        return False
    if h.get("dns_status") in ("nxdomain", "no_record"):
        return False
    if brand_health_rdap_enabled() and h.get("rdap_status") == "query_failed":
        return False
    return True


def domain_verified_for_list(h: Optional[dict]) -> bool:
    if not h or not h.get("verified_at"):
        return False
    return _domain_passes_verification_rules(h)


def stamp_domain_health_checked(h: dict) -> dict:
    out = dict(h)
    now = datetime.now(timezone.utc).isoformat()
    out["checked_at"] = now
    if _domain_passes_verification_rules(out):
        out["verified_at"] = now
    return out


def pending_verification_domains(
    brand_map: Mapping[str, List[str]],
    by_domain: Dict[str, dict],
) -> List[str]:
    return [
        d
        for d in domains_in_brand_map(brand_map)
        if not domain_verified_for_list(by_domain.get(d))
    ]


def clear_domain_verification_state(
    by_domain: Dict[str, dict],
    domains,
) -> None:
    """Verifizierung zurücksetzen (Neu-Prüfung)."""
    for raw in domains or ():
        d = str(raw).lower().strip(".")
        if not d:
            continue
        h = by_domain.get(d)
        if not h:
            continue
        updated = dict(h)
        updated.pop("verified_at", None)
        updated.pop("checked_at", None)
        by_domain[d] = updated
        invalidate_rdap_cache_for_domain(d)


def prune_health_to_brand_map(health: dict, brand_map: Mapping[str, List[str]]) -> dict:
    allowed = set(domains_in_brand_map(brand_map))
    out = dict(health or {})
    by_domain = {
        k: v for k, v in dict(out.get("domains") or {}).items() if k in allowed
    }
    out["domains"] = by_domain
    out["brands"] = _rebuild_brand_severities(brand_map, by_domain)
    if brand_health_rdap_enabled():
        out["rdap_summary"] = _rdap_summary_from_domains(by_domain)
    out["pending_verification"] = pending_verification_domains(brand_map, by_domain)
    return out


def _rdap_summary_from_domains(by_domain: Dict[str, dict]) -> Dict[str, int]:
    summary = {
        "with_date": 0,
        "no_date": 0,
        "query_failed": 0,
        "unsupported": 0,
    }
    for h in by_domain.values():
        st = h.get("rdap_status") or ""
        if h.get("rdap_registered") or st == "ok":
            summary["with_date"] += 1
        elif st == "no_registration":
            summary["no_date"] += 1
        elif st == "query_failed":
            summary["query_failed"] += 1
        elif st == "unsupported_tld":
            summary["unsupported"] += 1
    return summary


def _rebuild_brand_severities(
    brand_map: Mapping[str, List[str]],
    by_domain: Dict[str, dict],
) -> Dict[str, dict]:
    brands: Dict[str, dict] = {}
    for brand, doms in brand_map.items():
        worst = "ok"
        domain_status = {}
        for dom in doms:
            dd = str(dom).lower().strip(".")
            h = by_domain.get(dd) or {"severity": "unknown"}
            domain_status[dd] = h.get("severity", "unknown")
            sev = h.get("severity", "ok")
            if sev == "error":
                worst = "error"
            elif sev == "warn" and worst != "error":
                worst = "warn"
        brands[brand] = {"severity": worst, "domains": domain_status}
    return brands


def _followup_domain_list(
    brand_map: Mapping[str, List[str]],
    by_domain: Dict[str, dict],
    *,
    cap: int,
    truncated: bool,
) -> List[str]:
    pending: List[str] = []
    seen: Set[str] = set()
    for d, h in by_domain.items():
        if h.get("rdap_status") == "query_failed":
            pending.append(d)
            seen.add(d)
    for d in domains_in_brand_map(brand_map):
        if truncated and d not in by_domain and d not in seen:
            pending.append(d)
            seen.add(d)
    return pending


def run_health_report(
    brand_map: Mapping[str, List[str]],
    *,
    include_rdap: Optional[bool] = None,
    db_session=None,
    max_domains: Optional[int] = None,
    existing_health: Optional[dict] = None,
    only_domains: Optional[List[str]] = None,
    stop_on_rdap_429: Optional[bool] = None,
) -> Dict[str, Any]:
    from src.services.domain_reputation import (
        brand_health_max_domains,
        brand_health_rdap_aborted,
        clear_brand_health_rdap_abort_policy,
        clear_brand_health_rdap_deadline,
        prepare_brand_health_rdap_batch,
        set_brand_health_rdap_abort_policy,
        set_brand_health_rdap_deadline,
        brand_health_rdap_budget_seconds,
    )

    include_rdap = brand_health_rdap_enabled() if include_rdap is None else include_rdap
    if stop_on_rdap_429 is None:
        from src.services.domain_reputation import brand_health_stop_on_rdap_429

        stop_on_rdap_429 = brand_health_stop_on_rdap_429()

    cap = max_domains if max_domains is not None else brand_health_max_domains()
    base_health = dict(existing_health or {})
    by_domain: Dict[str, dict] = dict(base_health.get("domains") or {})

    if only_domains is not None:
        queue = sorted({str(d).lower().strip(".") for d in only_domains if d})
    else:
        queue = pending_verification_domains(brand_map, by_domain)

    truncated = False
    aborted: Optional[str] = None
    processed = 0
    deadline: Optional[float] = None

    if include_rdap and queue:
        prepare_brand_health_rdap_batch(queue)
        set_brand_health_rdap_abort_policy(stop_on_rdap_429)
        deadline = time.monotonic() + brand_health_rdap_budget_seconds()
        set_brand_health_rdap_deadline(deadline)
    try:
        for d in queue:
            if processed >= cap:
                truncated = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                truncated = True
                break
            if domain_verified_for_list(by_domain.get(d)):
                continue
            by_domain[d] = stamp_domain_health_checked(
                assess_domain_health(d, include_rdap=include_rdap, db_session=db_session)
            )
            processed += 1
            if include_rdap and brand_health_rdap_aborted():
                aborted = "rdap_429"
                break
    finally:
        if include_rdap:
            clear_brand_health_rdap_deadline()
            clear_brand_health_rdap_abort_policy()

    health = prune_health_to_brand_map(base_health, brand_map)
    health["domains"] = by_domain
    health["brands"] = _rebuild_brand_severities(brand_map, by_domain)
    health["checked_at"] = datetime.now(timezone.utc).isoformat()
    health["truncated"] = truncated
    health["max_domains"] = cap
    health["processed_this_run"] = processed
    if include_rdap:
        health["rdap_summary"] = _rdap_summary_from_domains(by_domain)
    health["pending_verification"] = pending_verification_domains(brand_map, by_domain)
    health["rdap_pending"] = health["pending_verification"]
    health["rdap_followup_enqueued"] = False
    if aborted:
        health["aborted"] = aborted
    return health


def parse_dbl_blocked_json(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return sorted({str(x).lower().strip(".") for x in data if x})
    except json.JSONDecodeError:
        pass
    return []


def brand_health_rdap_user_pref(row) -> bool:
    if not row:
        return False
    return bool(getattr(row, "brand_health_rdap", False))


def brand_settings_api_payload(row, user_id: int) -> dict:
    """Marken-Domains-API-Felder (Gunicorn + Celery — ohne Blueprint-Import)."""
    del user_id  # reserviert für künftige user-spezifische Felder
    custom_raw = ""
    custom_map: dict = {}
    pending = None
    health = None
    health_checked_at = None
    dbl_blocked: list = []
    if row:
        custom_raw = row.brand_official_domains_json or ""
        if row.brand_import_pending_json:
            try:
                pending = json.loads(row.brand_import_pending_json)
            except json.JSONDecodeError:
                pending = None
        if row.brand_domains_health_json:
            try:
                health = json.loads(row.brand_domains_health_json)
            except json.JSONDecodeError:
                health = None
        if row.brand_domains_health_checked_at:
            health_checked_at = iso_utc_for_api(row.brand_domains_health_checked_at)
        dbl_blocked = parse_dbl_blocked_json(
            getattr(row, "brand_dbl_blocked_domains_json", None)
        )
        if custom_raw.strip():
            try:
                custom_map = parse_brand_domains_text(custom_raw)
            except ValueError:
                custom_map = {}
    effective = effective_brand_map(custom_map)
    scope = brand_scope_stats(custom_map, health)
    user_rdap = brand_health_rdap_user_pref(row)
    rdap_effective = resolve_brand_health_rdap(user_rdap)
    return {
        "builtin_count": len(BUILTIN_BRAND_OFFICIAL_DOMAINS),
        "custom_count": len(custom_map),
        "effective_count": len(effective),
        "scope": scope,
        "custom_text": custom_raw.strip() or brand_map_to_lines(custom_map),
        "custom_map": custom_map,
        "effective_preview": brand_map_to_lines(dict(list(effective.items())[:20])),
        "pending_import": pending,
        "system_lines": brand_map_to_lines(BUILTIN_BRAND_OFFICIAL_DOMAINS),
        "health": health,
        "health_checked_at": health_checked_at,
        "dbl_blocked_domains": dbl_blocked,
        "audit_scam_rdap_sender_enabled": audit_scam_rdap_sender_enabled(),
        "brand_health_rdap": user_rdap,
        "brand_health_rdap_enabled": rdap_effective,
        "brand_health_rdap_admin_disabled": brand_health_rdap_admin_disabled(),
    }


def merge_dbl_blocked(existing: List[str], new_domains: List[str]) -> List[str]:
    s = set(existing)
    for d in new_domains:
        reg = registrable_domain_from_host(d)
        if reg:
            s.add(reg)
    return sorted(s)


def strip_dbl_domains_from_map(
    brand_map: Dict[str, List[str]],
    blocked_regs: List[str],
) -> Tuple[Dict[str, List[str]], List[str]]:
    """Entfernt blockierte registrable Domains aus der Map."""
    blocked_set = set(blocked_regs)
    removed: List[str] = []
    out: Dict[str, List[str]] = {}
    for brand, domains in brand_map.items():
        kept = []
        for dom in domains:
            d = str(dom).lower().strip(".")
            reg = registrable_domain_from_host(d)
            if reg in blocked_set:
                removed.append(d)
                continue
            kept.append(d)
        if kept:
            out[brand] = kept
    return out, removed


def prepare_save_brand_map(
    raw_map: Mapping,
    dbl_blocked_existing: List[str],
    *,
    run_live_checks: bool = True,
    db_session=None,
    existing_health: Optional[dict] = None,
    previous_map: Optional[Mapping[str, List[str]]] = None,
    include_rdap: Optional[bool] = None,
) -> Tuple[Dict[str, List[str]], List[str], List[str], Dict[str, Any], List[str]]:
    """
    Returns cleaned_map, errors, warnings, health_report, new_dbl_registrable.
    """
    cleaned, _ = validate_brand_map(raw_map)
    cleaned, _ = strip_dbl_domains_from_map(cleaned, dbl_blocked_existing)

    errors: List[str] = []
    warnings: List[str] = []
    health: Dict[str, Any] = dict(existing_health or {})
    if run_live_checks:
        prior = dict(existing_health or {})
        if previous_map is not None:
            added = new_domains_from_maps(previous_map, cleaned)
            if not added:
                health = prune_health_to_brand_map(prior, cleaned)
            else:
                health = run_health_report(
                    cleaned,
                    db_session=db_session,
                    existing_health=prior,
                    only_domains=added,
                    include_rdap=include_rdap,
                )
        else:
            health = run_health_report(
                cleaned,
                db_session=db_session,
                existing_health=prior,
                include_rdap=include_rdap,
            )
        errors, warnings = validate_official_domains_for_save(
            cleaned,
            db_session=db_session,
            precomputed=health.get("domains"),
        )
        if health.get("aborted") == "rdap_429":
            warnings = list(warnings) + [
                "RDAP 429 — Prüfung gestoppt. Bereits verifizierte Domains gespeichert; "
                "nach Pause erneut speichern oder «Domains prüfen»."
            ]
    else:
        health = prune_health_to_brand_map(health, cleaned)

    new_dbl: List[str] = []
    for dom, info in (health.get("domains") or {}).items():
        if info.get("dbl_hard_listed"):
            reg = registrable_domain_from_host(dom)
            if reg:
                new_dbl.append(reg)

    return cleaned, errors, warnings, health, new_dbl


def apply_brand_health_rdap_followup(
    user_id: int,
    domains: List[str],
    *,
    db_session,
    models,
) -> Dict[str, Any]:
    """RDAP-Nachzug (gedrosselt) — merged in gespeichertes health JSON."""
    row = (
        db_session.query(models.AuditClusterSettings)
        .filter_by(user_id=user_id, account_id=None)
        .first()
    )
    if not row or not row.brand_official_domains_json:
        return {"ok": False, "reason": "no_settings"}

    brand_map, _ = validate_brand_map(parse_brand_domains_text(row.brand_official_domains_json))
    try:
        health = json.loads(row.brand_domains_health_json or "{}")
    except json.JSONDecodeError:
        health = {}

    by_domain: Dict[str, dict] = dict(health.get("domains") or {})
    updated = 0
    include_rdap = resolve_brand_health_rdap(brand_health_rdap_user_pref(row))
    if not include_rdap:
        return {"ok": True, "updated": 0, "skipped": "rdap_disabled"}

    from src.services.domain_reputation import (
        brand_health_max_domains,
        brand_health_rdap_aborted,
        clear_brand_health_rdap_abort_policy,
        clear_brand_health_rdap_context,
        clear_brand_health_rdap_deadline,
        prepare_brand_health_rdap_followup,
        set_brand_health_rdap_abort_policy,
        set_brand_health_rdap_context,
        set_brand_health_rdap_deadline,
        brand_health_rdap_budget_seconds,
        brand_health_stop_on_rdap_429,
    )
    set_brand_health_rdap_context(True)
    try:
        return _apply_brand_health_rdap_followup_body(
            row,
            brand_map,
            health,
            by_domain,
            domains,
            db_session,
            updated,
        )
    finally:
        clear_brand_health_rdap_context()


def _apply_brand_health_rdap_followup_body(
    row,
    brand_map,
    health,
    by_domain,
    domains,
    db_session,
    updated,
):
    from src.services.domain_reputation import (
        brand_health_max_domains,
        brand_health_rdap_aborted,
        brand_health_stop_on_rdap_429,
        clear_brand_health_rdap_abort_policy,
        clear_brand_health_rdap_deadline,
        patch_rdap_into_domain_health,
        prepare_brand_health_rdap_followup,
        set_brand_health_rdap_abort_policy,
        set_brand_health_rdap_deadline,
        brand_health_rdap_budget_seconds,
    )
    prepare_brand_health_rdap_followup(domains)

    deadline = time.monotonic() + brand_health_rdap_budget_seconds()
    set_brand_health_rdap_deadline(deadline)
    set_brand_health_rdap_abort_policy(brand_health_stop_on_rdap_429())
    aborted = False
    try:
        for dom in domains:
            d = str(dom).lower().strip(".")
            if not d:
                continue
            if domain_verified_for_list(by_domain.get(d)):
                continue
            if deadline is not None and time.monotonic() >= deadline:
                break
            existing = by_domain.get(d)
            if existing and existing.get("dns_status"):
                by_domain[d] = stamp_domain_health_checked(
                    patch_rdap_into_domain_health(existing, d)
                )
            else:
                by_domain[d] = stamp_domain_health_checked(
                    assess_domain_health(
                        d, include_rdap=True, db_session=db_session
                    )
                )
            updated += 1
            if brand_health_rdap_aborted():
                aborted = True
                break
    finally:
        clear_brand_health_rdap_deadline()
        clear_brand_health_rdap_abort_policy()

    health = prune_health_to_brand_map(health, brand_map)
    health["domains"] = by_domain
    health["brands"] = _rebuild_brand_severities(brand_map, by_domain)
    if aborted:
        health["aborted"] = "rdap_429"
    health["checked_at"] = datetime.now(timezone.utc).isoformat()
    persist_brand_health_row(row, health)
    db_session.commit()
    return {
        "ok": True,
        "updated": updated,
        "rdap_pending": len(health.get("pending_verification") or []),
    }
