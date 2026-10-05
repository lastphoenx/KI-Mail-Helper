"""DNS-, Spamhaus-DBL- und RDAP-Hilfen (Marken-Health, Scam-Audit).

Spamhaus DBL (Domain Blocklist): Antworten unter 127.0.1.0/24 und 127.0.2.0/24.
127.0.0.0/24 gehört zu Zen (IP) — bei DBL-Query Fehlkonfiguration → «unavailable».
127.255.255.252/254/255 = Fehler (Tippfehler / öffentlicher Resolver / Rate-Limit).

Resolver: kein öffentlicher DNS (8.8.8.8, 1.1.1.1) für DBL — siehe Doku docs/audit/spamhaus-dbl.md
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests

from src.services.brand_domain_policy import registrable_domain_from_host

logger = logging.getLogger(__name__)

RDAP_YOUNG_DAYS_WARN = 90
RDAP_VERY_YOUNG_DAYS_WARN = 30

_DBL_UNAVAILABLE_CODES = frozenset(
    {
        "127.255.255.252",
        "127.255.255.254",
        "127.255.255.255",
    }
)


def dbl_answer_code(code_or_detail: str) -> str:
    """Extrahiert 127.x.x.x aus DBL-Antwort oder Detail-String."""
    import re

    text = (code_or_detail or "").strip()
    m = re.search(r"127\.\d+\.\d+\.\d+", text)
    return m.group(0) if m else text


def dbl_is_abused_legit_code(code: str) -> bool:
    """127.0.1.102–106: missbrauchte legitime Domain — warnen, nicht speicher-blockieren."""
    code = dbl_answer_code(code)
    if not code.startswith("127.0.1."):
        return False
    try:
        last = int(code.rsplit(".", 1)[-1])
    except ValueError:
        return False
    return 102 <= last <= 106


def dbl_is_hard_listing_code(code: str) -> bool:
    code = dbl_answer_code(code)
    if code.startswith("127.0.2."):
        return True
    if code.startswith("127.0.1."):
        return not dbl_is_abused_legit_code(code)
    return False

_iana_bootstrap_cache: Optional[dict] = None
_iana_bootstrap_loaded_at: float = 0.0
_rdap_domain_cache: Dict[str, Tuple[Optional[datetime], float, str, str]] = {}
_rdap_server_lock = threading.Lock()
_rdap_server_next_ok: Dict[str, float] = {}
_rdap_server_interval: Dict[str, float] = {}
_rdap_server_blocked_until: Dict[str, float] = {}
_rdap_batch_deadline: Optional[float] = None
RDAP_NIC_CH_BASE = "https://rdap.nic.ch"
_rdap_redis_client_cache = None
_rdap_redis_disabled = False
_brand_health_stop_on_rdap_429: bool = False
_brand_health_rdap_aborted: bool = False
_mem_dbl_cache: Dict[str, Tuple["DblLookupResult", float]] = {}
_mem_dns_cache: Dict[str, Tuple[Tuple[str, str], float]] = {}

# Nur wo IANA-Bootstrap fehlt/fehlerhaft — aligned mit whoisit/overrides (Jan 2026).
# Immer zuerst IANA, dann diese Tabelle (_rdap_base_url_for_suffix).
RDAP_TLD_OVERRIDES: Dict[str, str] = {
    "ch": "https://rdap.nic.ch",
    "de": "https://rdap.denic.de",
    "li": "https://rdap.nic.li",
    "io": "https://rdap.identitydigital.services/rdap",
    "me": "https://rdap.identitydigital.services/rdap",
    "us": "https://rdap.nic.us",
}


@dataclass(frozen=True)
class DblLookupResult:
    listed: bool
    detail: str
    unavailable: bool


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def cache_ttl_seconds() -> int:
    return _int_env("DOMAIN_REPUTATION_CACHE_HOURS", 24) * 3600


def unavailable_cache_ttl_seconds() -> int:
    """Kurz cachen wenn DBL nicht erreichbar (öffentlicher Resolver, Rate-Limit)."""
    return _int_env("DOMAIN_REPUTATION_UNAVAILABLE_CACHE_MINUTES", 10) * 60


def rdap_transient_cache_ttl_seconds() -> int:
    return _int_env("RDAP_TRANSIENT_CACHE_MINUTES", 15) * 60


def rdap_stable_cache_ttl_seconds() -> int:
    return _int_env("RDAP_STABLE_CACHE_HOURS", 168) * 3600


def _dbl_entry_ttl_seconds(result: Optional[DblLookupResult] = None, *, status: str = "") -> int:
    if (result is not None and result.unavailable) or status == "unavailable":
        return unavailable_cache_ttl_seconds()
    return cache_ttl_seconds()


_brand_health_rdap_context: Optional[bool] = None


def brand_health_rdap_admin_disabled() -> bool:
    """Admin-Notbremse: BRAND_DOMAIN_HEALTH_RDAP=false erzwingt RDAP aus."""
    raw = os.getenv("BRAND_DOMAIN_HEALTH_RDAP")
    if raw is None or not str(raw).strip():
        return False
    return not _bool_env("BRAND_DOMAIN_HEALTH_RDAP", True)


def resolve_brand_health_rdap(user_pref: bool) -> bool:
    if brand_health_rdap_admin_disabled():
        return False
    return bool(user_pref)


def set_brand_health_rdap_context(enabled: Optional[bool]) -> None:
    global _brand_health_rdap_context
    _brand_health_rdap_context = enabled


def clear_brand_health_rdap_context() -> None:
    global _brand_health_rdap_context
    _brand_health_rdap_context = None


def brand_health_rdap_enabled() -> bool:
    if brand_health_rdap_admin_disabled():
        return False
    if _brand_health_rdap_context is not None:
        return _brand_health_rdap_context
    return False


def audit_scam_rdap_sender_enabled() -> bool:
    return _bool_env("AUDIT_SCAM_RDAP_SENDER", False)


def brand_health_max_domains() -> int:
    return _int_env("BRAND_HEALTH_MAX_DOMAINS", 100)


def rdap_min_interval_seconds() -> float:
    raw = os.getenv("RDAP_MIN_INTERVAL_SECONDS", "3")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        val = 1.0
    return max(0.0, val)


def rdap_retry_after_max_seconds() -> float:
    return float(_int_env("RDAP_RETRY_AFTER_MAX_SECONDS", 15))


def rdap_server_block_seconds() -> float:
    return float(_int_env("RDAP_SERVER_BLOCK_SECONDS", 120))


def rdap_use_circuit_breaker() -> bool:
    return _bool_env("RDAP_USE_CIRCUIT_BREAKER", False)


def rdap_redis_throttle_enabled() -> bool:
    return _bool_env("RDAP_REDIS_THROTTLE", True)


def rdap_nic_ch_interval_seconds() -> float:
    raw = os.getenv("RDAP_NIC_CH_INTERVAL_SECONDS", "4")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        val = 4.0
    return min(max(1.0, val), 10.0)


def brand_health_rdap_followup_chunk_size() -> int:
    return _int_env("BRAND_HEALTH_RDAP_FOLLOWUP_CHUNK", 25)


def brand_health_rdap_followup_cooldown_seconds() -> int:
    return _int_env("BRAND_HEALTH_RDAP_FOLLOWUP_COOLDOWN", 90)


def brand_health_rdap_auto_followup() -> bool:
    return _bool_env("BRAND_HEALTH_RDAP_AUTO_FOLLOWUP", False)


def brand_health_stop_on_rdap_429() -> bool:
    return _bool_env("BRAND_HEALTH_STOP_ON_RDAP_429", True)


def set_brand_health_rdap_abort_policy(stop_on_429: Optional[bool] = None) -> None:
    global _brand_health_stop_on_rdap_429, _brand_health_rdap_aborted
    _brand_health_stop_on_rdap_429 = (
        brand_health_stop_on_rdap_429() if stop_on_429 is None else bool(stop_on_429)
    )
    _brand_health_rdap_aborted = False


def clear_brand_health_rdap_abort_policy() -> None:
    global _brand_health_stop_on_rdap_429, _brand_health_rdap_aborted
    _brand_health_stop_on_rdap_429 = False
    _brand_health_rdap_aborted = False


def brand_health_rdap_aborted() -> bool:
    return _brand_health_rdap_aborted


def _mark_brand_health_rdap_aborted() -> None:
    global _brand_health_rdap_aborted
    _brand_health_rdap_aborted = True


def brand_health_rdap_budget_seconds() -> float:
    return float(_int_env("BRAND_HEALTH_RDAP_BUDGET_SECONDS", 480))


def set_brand_health_rdap_deadline(deadline_monotonic: Optional[float]) -> None:
    global _rdap_batch_deadline
    _rdap_batch_deadline = deadline_monotonic


def clear_brand_health_rdap_deadline() -> None:
    global _rdap_batch_deadline
    _rdap_batch_deadline = None


def reset_rdap_rate_limit_state_for_tests() -> None:
    """Nur Tests — Circuit-Breaker und Batch-Deadline zurücksetzen."""
    global _rdap_batch_deadline
    with _rdap_server_lock:
        _rdap_server_next_ok.clear()
        _rdap_server_interval.clear()
        _rdap_server_blocked_until.clear()
    _rdap_batch_deadline = None
    clear_brand_health_rdap_abort_policy()
    clear_brand_health_rdap_deadline()
    clear_brand_health_rdap_context()


def invalidate_rdap_cache_for_domain(domain: str) -> None:
    reg = registrable_domain_from_host((domain or "").lower().strip("."))
    if reg:
        _rdap_domain_cache.pop(reg, None)


def prepare_brand_health_rdap_batch(domains) -> None:
    """Neuer Marken-Health-Lauf: transient RDAP-Cache + Circuit-Breaker zurücksetzen."""
    with _rdap_server_lock:
        _rdap_server_blocked_until.clear()
        _rdap_server_interval.clear()
        _rdap_server_next_ok.clear()
        _rdap_server_interval[RDAP_NIC_CH_BASE] = rdap_nic_ch_interval_seconds()
    for domain in domains or ():
        invalidate_rdap_cache_for_domain(str(domain))


def prepare_brand_health_rdap_followup(domains) -> None:
    """RDAP-Nachzug: nur Cache der Ziel-Domains — Circuit von nic.ch nicht zurücksetzen."""
    for domain in domains or ():
        invalidate_rdap_cache_for_domain(str(domain))


def classify_spamhaus_dbl_answer(code: str) -> DblLookupResult:
    """Klassifiziert eine A-Record-Antwort von *.dbl.spamhaus.org."""
    code = (code or "").strip()
    if code in _DBL_UNAVAILABLE_CODES:
        return DblLookupResult(
            False,
            f"Spamhaus DBL nicht verfügbar ({code})",
            True,
        )
    if code.startswith("127.0.0."):
        return DblLookupResult(
            False,
            f"Unerwartete DBL-Antwort {code} (Zen/IP-Liste? Resolver prüfen)",
            True,
        )
    if code.startswith("127.0.1.") or code.startswith("127.0.2."):
        return DblLookupResult(True, f"Spamhaus DBL ({code})", False)
    if code.startswith("127."):
        return DblLookupResult(False, f"Unbekannte DBL-Antwort {code}", True)
    return DblLookupResult(False, f"Nicht-DBL-Antwort {code}", True)


def _lookup_spamhaus_dbl_live(domain: str) -> DblLookupResult:
    domain = (domain or "").lower().strip(".")
    if not domain:
        return DblLookupResult(False, "", False)
    try:
        import dns.resolver

        query = f"{domain}.dbl.spamhaus.org"
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 2.0
        resolver.timeout = 2.0
        answers = resolver.resolve(query, "A")
        for rdata in answers:
            return classify_spamhaus_dbl_answer(str(rdata))
    except ImportError:
        logger.debug("dnspython fehlt — DBL übersprungen")
        return DblLookupResult(False, "dnspython fehlt", True)
    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name in ("NXDOMAIN", "NoAnswer", "NoNameservers"):
            return DblLookupResult(False, "", False)
        if exc_name in ("LifetimeTimeout", "Timeout"):
            return DblLookupResult(False, "DBL-Timeout", True)
        logger.debug("DBL lookup %s: %s", domain, exc_name)
    return DblLookupResult(False, "", False)


def _read_dbl_cache(reg: str, db_session) -> Optional[DblLookupResult]:
    now = time.time()
    mem = _mem_dbl_cache.get(reg)
    if mem and (now - mem[1]) < _dbl_entry_ttl_seconds(mem[0]):
        return mem[0]
    if db_session is None:
        return None
    try:
        import importlib

        models = importlib.import_module(".02_models", "src")
        row = (
            db_session.query(models.DomainReputationCache)
            .filter_by(domain=reg)
            .first()
        )
        if not row or not row.checked_at:
            return None
        age = (datetime.now(timezone.utc) - row.checked_at.replace(tzinfo=timezone.utc)).total_seconds()
        if age > _dbl_entry_ttl_seconds(status=row.dbl_status or ""):
            return None
        return DblLookupResult(
            row.dbl_status == "listed",
            row.dbl_detail or "",
            row.dbl_status == "unavailable",
        )
    except Exception as exc:
        logger.debug("DBL cache read: %s", exc)
        return None


def _write_dbl_cache(reg: str, result: DblLookupResult, db_session) -> None:
    del db_session  # eigene Session — kein commit auf Scan-Session
    _mem_dbl_cache[reg] = (result, time.time())
    try:
        import importlib

        from src.helpers.database import get_db_session

        models = importlib.import_module(".02_models", "src")
        status = "listed" if result.listed else ("unavailable" if result.unavailable else "clean")
        with get_db_session() as session:
            row = (
                session.query(models.DomainReputationCache)
                .filter_by(domain=reg)
                .first()
            )
            if not row:
                row = models.DomainReputationCache(domain=reg)
                session.add(row)
            row.dbl_status = status
            row.dbl_detail = (result.detail or "")[:250]
            row.checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.commit()
    except Exception as exc:
        logger.debug("DBL cache write: %s", exc)


def read_spamhaus_dbl_cache(domain: str, db_session=None) -> Optional[DblLookupResult]:
    """Nur Cache (Memory/DB), kein Live-DNS — für Scan-Limits."""
    reg = registrable_domain_from_host(domain) or (domain or "").lower().strip(".")
    if not reg:
        return None
    return _read_dbl_cache(reg, db_session)


def lookup_spamhaus_dbl(domain: str, db_session=None) -> DblLookupResult:
    """DBL mit Memory- und optional DB-Cache (DOMAIN_REPUTATION_CACHE_HOURS)."""
    reg = registrable_domain_from_host(domain) or (domain or "").lower().strip(".")
    if not reg:
        return DblLookupResult(False, "", False)
    cached = _read_dbl_cache(reg, db_session)
    if cached is not None:
        return cached
    result = _lookup_spamhaus_dbl_live(reg)
    _write_dbl_cache(reg, result, db_session)
    if result.unavailable:
        logger.warning("Spamhaus DBL unavailable for %s: %s", reg, result.detail)
    return result


def lookup_dns_reachable(domain: str, db_session=None) -> Tuple[str, str]:
    """Returns status ok|nxdomain|no_record|timeout|unknown and detail."""
    domain = (domain or "").lower().strip(".")
    if not domain:
        return "no_record", "leer"
    ttl = cache_ttl_seconds()
    now = time.time()
    mem = _mem_dns_cache.get(domain)
    if mem and (now - mem[1]) < ttl:
        return mem[0]
    try:
        import dns.resolver

        resolver = dns.resolver.Resolver()
        resolver.lifetime = 2.0
        resolver.timeout = 2.0
        for rtype in ("A", "AAAA", "MX"):
            try:
                resolver.resolve(domain, rtype)
                result = ("ok", rtype)
                _mem_dns_cache[domain] = (result, now)
                return result
            except Exception as exc:
                if type(exc).__name__ == "NXDOMAIN":
                    result = ("nxdomain", "NXDOMAIN")
                    _mem_dns_cache[domain] = (result, now)
                    return result
        result = ("no_record", "kein A/AAAA/MX")
        _mem_dns_cache[domain] = (result, now)
        return result
    except ImportError:
        return "unknown", "dnspython fehlt"
    except Exception as exc:
        if type(exc).__name__ in ("LifetimeTimeout", "Timeout"):
            return "timeout", "timeout"
        return "unknown", type(exc).__name__


def _load_iana_rdap_bootstrap() -> dict:
    global _iana_bootstrap_cache, _iana_bootstrap_loaded_at
    if _iana_bootstrap_cache and (time.time() - _iana_bootstrap_loaded_at) < 86400:
        return _iana_bootstrap_cache
    try:
        resp = requests.get(
            "https://data.iana.org/rdap/dns.json",
            timeout=15,
            allow_redirects=False,
        )
        resp.raise_for_status()
        _iana_bootstrap_cache = resp.json()
        _iana_bootstrap_loaded_at = time.time()
        return _iana_bootstrap_cache
    except Exception as exc:
        logger.debug("RDAP bootstrap: %s", exc)
        return {}


def _public_suffix_candidates(registrable: str) -> list[str]:
    labels = (registrable or "").lower().strip(".").split(".")
    if len(labels) < 2:
        return []
    out: list[str] = []
    for i in range(1, len(labels)):
        out.append(".".join(labels[i:]))
    return out


def _rdap_base_url_for_suffix(suffix: str) -> Optional[str]:
    suffix = (suffix or "").lower().strip(".")
    if not suffix:
        return None
    data = _load_iana_rdap_bootstrap()
    for entry in data.get("services") or []:
        tlds, urls = entry[0], entry[1]
        if suffix in tlds and urls:
            url = urls[0].rstrip("/")
            if url.lower().startswith("https://"):
                return url
    override = RDAP_TLD_OVERRIDES.get(suffix)
    if override and override.lower().startswith("https://"):
        return override.rstrip("/")
    return None


def _rdap_base_url_for_registrable(registrable: str) -> Optional[str]:
    reg = (registrable or "").lower().strip(".")
    if not reg or "." not in reg:
        return None
    for suffix in _public_suffix_candidates(reg):
        base = _rdap_base_url_for_suffix(suffix)
        if base:
            return base
    return None


def _rdap_base_url_for_domain(domain: str) -> Optional[str]:
    ext = registrable_domain_from_host(domain)
    if not ext:
        return None
    return _rdap_base_url_for_registrable(ext)


def _rdap_cache_ttl(fail_kind: str) -> int:
    if fail_kind == "transient":
        return rdap_transient_cache_ttl_seconds()
    return rdap_stable_cache_ttl_seconds()


def _rdap_cache_get(reg: str) -> Optional[Tuple[Optional[datetime], str]]:
    row = _rdap_domain_cache.get(reg)
    if not row:
        return None
    reg_dt, cached_at, fail_kind, status = row
    if (time.time() - cached_at) >= _rdap_cache_ttl(fail_kind):
        return None
    return reg_dt, status


def _rdap_cache_put(
    reg: str,
    reg_dt: Optional[datetime],
    *,
    fail_kind: str,
    status: str,
) -> None:
    _rdap_domain_cache[reg] = (reg_dt, time.time(), fail_kind, status)


def _rdap_interval_for_base(base: str) -> float:
    base = (base or "").rstrip("/")
    interval = _rdap_server_interval.get(base, rdap_min_interval_seconds())
    if base == RDAP_NIC_CH_BASE.rstrip("/"):
        interval = max(interval, rdap_nic_ch_interval_seconds())
    return interval


def _rdap_redis_client():
    global _rdap_redis_client_cache, _rdap_redis_disabled
    if _rdap_redis_disabled:
        return None
    if _rdap_redis_client_cache is not None:
        return _rdap_redis_client_cache
    try:
        import redis

        _rdap_redis_client_cache = redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0")
        )
        return _rdap_redis_client_cache
    except Exception:
        _rdap_redis_disabled = True
        return None


def _rdap_throttle_redis(base: str, interval: float) -> bool:
    client = _rdap_redis_client()
    if client is None:
        return False
    slot_key = f"rdap_throttle:next_ok:{base}"
    lock_key = f"rdap_throttle:lock:{base}"
    lock = client.lock(
        lock_key,
        timeout=max(120, int(interval * 4) + 30),
        blocking_timeout=300,
    )
    if not lock.acquire(blocking=True):
        return False
    try:
        now = time.time()
        raw = client.get(slot_key)
        next_ok = float(raw) if raw else 0.0
        if now < next_ok:
            time.sleep(next_ok - now)
        client.set(
            slot_key,
            str(time.time() + interval),
            ex=max(7200, int(interval * 20) + 60),
        )
        return True
    finally:
        try:
            lock.release()
        except Exception:
            pass


def _rdap_throttle(base_url: str) -> None:
    base = (base_url or "").rstrip("/")
    if not base:
        return
    interval = _rdap_interval_for_base(base)
    if rdap_redis_throttle_enabled():
        try:
            if _rdap_throttle_redis(base, interval):
                return
        except Exception as exc:
            logger.debug("RDAP redis throttle failed: %s", type(exc).__name__)

    with _rdap_server_lock:
        now = time.monotonic()
        wait_until = _rdap_server_next_ok.get(base, 0.0)
        if now < wait_until:
            time.sleep(wait_until - now)
        _rdap_server_next_ok[base] = time.monotonic() + interval


def _rdap_server_is_blocked(base: str) -> bool:
    base = (base or "").rstrip("/")
    if not base:
        return False
    with _rdap_server_lock:
        until = _rdap_server_blocked_until.get(base, 0.0)
    return time.monotonic() < until


def _rdap_trip_server(base: str) -> None:
    base = (base or "").rstrip("/")
    if not base:
        return
    block = rdap_server_block_seconds()
    with _rdap_server_lock:
        _rdap_server_blocked_until[base] = time.monotonic() + block
        cur = _rdap_server_interval.get(base, rdap_min_interval_seconds())
        _rdap_server_interval[base] = min(max(cur, 3.0), 5.0)
    logger.warning("RDAP server rate-limited — pausing %s for %.0fs", base, block)


def _rdap_bump_server_interval(base: str) -> None:
    base = (base or "").rstrip("/")
    if not base:
        return
    with _rdap_server_lock:
        cur = _rdap_server_interval.get(base, rdap_min_interval_seconds())
        _rdap_server_interval[base] = min(max(cur * 1.5, 2.0), 5.0)


def _rdap_retry_after_seconds(resp: requests.Response) -> float:
    raw = (resp.headers.get("Retry-After") or "").strip()
    cap = rdap_retry_after_max_seconds()
    try:
        val = float(int(raw))
    except (TypeError, ValueError):
        val = cap
    return min(max(1.0, val), cap)


def _rdap_http_get(url: str, base: str) -> requests.Response:
    base_key = (base or "").rstrip("/")
    if _rdap_server_is_blocked(base_key):
        logger.debug("RDAP skip (circuit open): %s", base_key)
        resp = requests.Response()
        resp.status_code = 429
        return resp

    _rdap_throttle(base_key)
    resp = requests.get(
        url,
        timeout=8,
        allow_redirects=False,
        headers={"Accept": "application/rdap+json"},
    )
    if resp.status_code != 429:
        return resp

    _rdap_bump_server_interval(base_key)
    wait = _rdap_retry_after_seconds(resp)
    if wait > 0:
        time.sleep(wait)
        _rdap_throttle(base_key)
        resp = requests.get(
            url,
            timeout=8,
            allow_redirects=False,
            headers={"Accept": "application/rdap+json"},
        )
    if resp.status_code == 429:
        _rdap_bump_server_interval(base_key)
        with _rdap_server_lock:
            interval = _rdap_server_interval.get(base_key, rdap_min_interval_seconds())
        logger.warning(
            "RDAP 429 nach Retry — %s (Intervall %.1fs, Domain übersprungen)",
            base_key,
            interval,
        )
        if rdap_use_circuit_breaker():
            _rdap_trip_server(base_key)
    return resp


def lookup_rdap_registration_date(
    domain: str,
    *,
    bypass_cache: bool = False,
) -> Tuple[Optional[datetime], str]:
    """
    Returns (registration_date, status).
    status: ok | no_registration | unsupported_tld | query_failed
    (legacy callers may still see 'unknown' mapped in UI)
    """
    domain = (domain or "").lower().strip(".")
    reg = registrable_domain_from_host(domain)
    if not reg:
        return None, "unsupported_tld"
    cached = _rdap_cache_get(reg)
    if cached is not None and not bypass_cache:
        reg_dt, status = cached
        return reg_dt, status

    dl = _rdap_batch_deadline
    if dl is not None and time.monotonic() >= dl:
        _rdap_cache_put(reg, None, fail_kind="transient", status="query_failed")
        return None, "query_failed"

    base = _rdap_base_url_for_domain(reg)
    if not base:
        _rdap_cache_put(reg, None, fail_kind="stable", status="unsupported_tld")
        return None, "unsupported_tld"

    url = f"{base}/domain/{reg}"
    try:
        resp = _rdap_http_get(url, base)
        if resp.status_code == 429 and _brand_health_stop_on_rdap_429:
            _mark_brand_health_rdap_aborted()
        if resp.status_code == 429 or resp.status_code >= 500:
            _rdap_cache_put(reg, None, fail_kind="transient", status="query_failed")
            return None, "query_failed"
        if resp.status_code >= 400:
            _rdap_cache_put(reg, None, fail_kind="stable", status="no_registration")
            return None, "no_registration"
        payload = resp.json()
        reg_dt = _parse_rdap_registration(payload)
        if reg_dt:
            _rdap_cache_put(reg, reg_dt, fail_kind="stable", status="ok")
            return reg_dt, "ok"
        _rdap_cache_put(reg, None, fail_kind="stable", status="no_registration")
        return None, "no_registration"
    except requests.Timeout:
        _rdap_cache_put(reg, None, fail_kind="transient", status="query_failed")
        return None, "query_failed"
    except Exception as exc:
        logger.debug("RDAP %s: %s", reg, type(exc).__name__)
        _rdap_cache_put(reg, None, fail_kind="transient", status="query_failed")
        return None, "query_failed"


def _parse_rdap_registration(payload: dict) -> Optional[datetime]:
    for ev in payload.get("events") or []:
        if (ev.get("eventAction") or "").lower() == "registration":
            raw = ev.get("eventDate")
            if not raw:
                continue
            try:
                raw = raw.replace("Z", "+00:00")
                return datetime.fromisoformat(raw).astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def assess_domain_health(
    domain: str,
    *,
    include_rdap: bool = True,
    db_session=None,
) -> Dict[str, Any]:
    """Einzel-Domain: DNS, DBL, optional RDAP — severity ok|warn|error."""
    d = (domain or "").lower().strip(".")
    out: Dict[str, Any] = {"domain": d, "severity": "ok", "issues": []}

    dbl = lookup_spamhaus_dbl(d, db_session)
    out["dbl_listed"] = dbl.listed
    out["dbl_unavailable"] = dbl.unavailable
    out["dbl_detail"] = dbl.detail
    code = dbl_answer_code(dbl.detail) if dbl.listed else ""
    out["dbl_code"] = code
    out["dbl_hard_listed"] = bool(dbl.listed and dbl_is_hard_listing_code(code or dbl.detail))
    out["dbl_abused_legit"] = bool(dbl.listed and dbl_is_abused_legit_code(code or dbl.detail))
    if dbl.unavailable:
        out["severity"] = "warn"
        out["issues"].append("dbl_unavailable")
    elif out["dbl_abused_legit"]:
        out["severity"] = "warn"
        out["issues"].append("dbl_abused_legit")
    elif out["dbl_hard_listed"]:
        out["severity"] = "error"
        out["issues"].append("dbl")
    elif dbl.listed:
        out["severity"] = "error"
        out["issues"].append("dbl")

    dns_status, dns_detail = lookup_dns_reachable(d, db_session)
    out["dns_status"] = dns_status
    out["dns_detail"] = dns_detail
    if dns_status in ("nxdomain", "no_record") and out["severity"] != "error":
        out["severity"] = "warn"
        out["issues"].append("dns")

    if include_rdap:
        reg_dt, rdap_st = lookup_rdap_registration_date(d)
        out["rdap_status"] = rdap_st
        if reg_dt:
            out["rdap_registered"] = reg_dt.date().isoformat()
            age_days = (datetime.now(timezone.utc) - reg_dt).days
            out["rdap_age_days"] = age_days
            if age_days < RDAP_VERY_YOUNG_DAYS_WARN and out["severity"] != "error":
                out["severity"] = "warn"
                out["issues"].append("rdap_young")
        elif rdap_st in ("unsupported_tld", "no_registration") and out["severity"] == "ok":
            out["issues"].append("rdap_no_date")
        elif rdap_st == "query_failed":
            out["issues"].append("rdap_query_failed")
            if out["severity"] == "ok":
                out["severity"] = "warn"
        elif rdap_st == "unknown" and out["severity"] == "ok":
            out["issues"].append("rdap_unknown")

    return out


def patch_rdap_into_domain_health(
    existing: Optional[dict],
    domain: str,
) -> dict:
    """Nur RDAP-Felder aktualisieren (Nachzug — DNS/DBL unverändert lassen)."""
    d = (domain or "").lower().strip(".")
    out: Dict[str, Any] = dict(existing) if existing else {"domain": d, "severity": "ok", "issues": []}
    out["domain"] = d
    issues = [i for i in (out.get("issues") or []) if i not in (
        "rdap_query_failed",
        "rdap_no_date",
        "rdap_unknown",
        "rdap_young",
    )]
    for key in (
        "rdap_status",
        "rdap_registered",
        "rdap_age_days",
    ):
        out.pop(key, None)

    if not brand_health_rdap_enabled():
        out["issues"] = issues
        return out

    reg_dt, rdap_st = lookup_rdap_registration_date(d)
    out["rdap_status"] = rdap_st
    if reg_dt:
        out["rdap_registered"] = reg_dt.date().isoformat()
        age_days = (datetime.now(timezone.utc) - reg_dt).days
        out["rdap_age_days"] = age_days
        if age_days < RDAP_VERY_YOUNG_DAYS_WARN and out.get("severity") != "error":
            out["severity"] = "warn"
            issues.append("rdap_young")
    elif rdap_st in ("unsupported_tld", "no_registration") and out.get("severity") == "ok":
        issues.append("rdap_no_date")
    elif rdap_st == "query_failed":
        issues.append("rdap_query_failed")
        if out.get("severity") == "ok":
            out["severity"] = "warn"
    elif rdap_st == "unknown" and out.get("severity") == "ok":
        issues.append("rdap_unknown")
    out["issues"] = issues
    return out


def _warnings_errors_from_health_row(
    domain: str,
    h: Dict[str, Any],
    *,
    brand: str = "",
) -> Tuple[list, list]:
    errors: list = []
    warnings: list = []
    d = domain
    if h.get("dbl_hard_listed"):
        errors.append(
            f"{d}: Spamhaus DBL — Speichern blockiert ({h.get('dbl_detail')})"
        )
    elif h.get("dbl_abused_legit"):
        warnings.append(
            f"{d}: DBL missbrauchte legitime Domain ({h.get('dbl_detail')}) — prüfen, nicht auto-entfernen"
        )
    elif h.get("dbl_unavailable"):
        warnings.append(f"{d}: {h.get('dbl_detail') or 'DBL nicht verfügbar'}")
    elif h.get("dns_status") == "nxdomain":
        warnings.append(f"{d}: DNS NXDOMAIN — Domain existiert nicht?")
    elif h.get("dns_status") == "no_record":
        warnings.append(f"{d}: kein A/AAAA/MX")
    age = h.get("rdap_age_days")
    if age is not None and age < RDAP_YOUNG_DAYS_WARN:
        warnings.append(f"{d}: RDAP-Alter {age} Tage")
    return errors, warnings


def validate_official_domains_for_save(
    brand_map: Dict[str, list],
    *,
    include_rdap: bool = True,
    db_session=None,
    max_domains: Optional[int] = None,
    precomputed: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[list, list]:
    """errors block save; warnings allow save."""
    errors: list = []
    warnings: list = []
    cap = max_domains if max_domains is not None else brand_health_max_domains()
    seen: set = set()
    unique: list = []
    for brand, domains in brand_map.items():
        for dom in domains:
            d = str(dom).lower().strip(".")
            if not d or d in seen:
                continue
            seen.add(d)
            unique.append((brand, d))

    checked = 0
    for brand, d in unique:
        if precomputed is not None:
            h = precomputed.get(d)
            if h is None:
                continue
        else:
            if checked >= cap:
                warnings.append(
                    f"Health-Check abgebrochen nach {cap} Domains — Rest ungeprüft"
                )
                return errors, warnings
            checked += 1
            h = assess_domain_health(
                d, include_rdap=include_rdap, db_session=db_session
            )
        row_errors, row_warnings = _warnings_errors_from_health_row(d, h, brand=brand)
        errors.extend(row_errors)
        warnings.extend(row_warnings)

    # Mit precomputed (Celery-Teillauf): Cap gilt pro Lauf in run_health_report,
    # nicht als «Liste > cap» — sonst irreführende Warnung bei z. B. 225 Domains.
    return errors, warnings
