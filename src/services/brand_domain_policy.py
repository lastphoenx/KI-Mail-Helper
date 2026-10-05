"""Zentrale Marken → offizielle Domains (Audit, LLM-Kalibrierung, Scam-Layer).

System-Basis im Code; User-JSON wird per Union ergänzt (gleicher Marken-Key: Domains vereinigt).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple
from urllib.parse import urlparse

import tldextract

logger = logging.getLogger(__name__)

_tld_extractor: Optional[tldextract.TLDExtract] = None


def _get_tld_extractor() -> tldextract.TLDExtract:
    global _tld_extractor
    if _tld_extractor is None:
        _tld_extractor = tldextract.TLDExtract(include_psl_private_domains=True)
    return _tld_extractor


def _extract_host(host: str):
    return _get_tld_extractor()(host)

MAX_BRANDS = 500
MAX_DOMAINS_PER_BRAND = 20
MAX_CUSTOM_JSON_BYTES = 64 * 1024

# Domains die als «offiziell» nie erlaubt sind (Public Suffix / zu kurz)
_BLOCKED_OFFICIAL_SUFFIXES = frozenset(
    {
        "ch",
        "de",
        "com",
        "net",
        "org",
        "io",
        "co.uk",
        "com.br",
        "github.io",
        "appspot.com",
        "cloudfront.net",
        "amazonaws.com",
        "herokuapp.com",
        "vercel.app",
        "netlify.app",
        "pages.dev",
        "blogspot.com",
        "web.app",
        "azurewebsites.net",
    }
)

# Kurze/allgemeine Marken: höchstens Review, kein automatisches +60/Scam allein über Marke
AMBIGUOUS_SHORT_BRANDS = frozenset(
    {
        "css",
        "coop",
        "apple",
        "google",
        "microsoft",
        "bund",
        "blick",
        "bim",
        "bls",
        "booking",
        "brack",
    }
)

BRAND_CHECK_WHITELIST_DOMAINS = frozenset(
    {
        "heise.de",
        "newsletter.heise.de",
        "chip.de",
        "golem.de",
        "t3n.de",
        "digitec.ch",
        "galaxus.ch",
        "zalando.ch",
        "aboutyou.ch",
    }
)

BUILTIN_BRAND_OFFICIAL_DOMAINS: Dict[str, List[str]] = {
    "twint": ["twint.ch", "news.twint.ch"],
    "swisscom": ["swisscom.com", "swisscom.ch"],
    "sbb": ["sbb.ch", "mailings.sbb.ch", "mailing.swisspass.ch", "swisspass.ch"],
    "postfinance": ["postfinance.ch"],
    "yuh": ["yuh.com"],
    "helsana": ["helsana.ch", "myhelsana.ch"],
    "css": ["css.ch", "mycss.ch"],
    "swica": ["swica.ch"],
    "sanitas": ["sanitas.ch"],
    "ethz": ["ethz.ch"],
    "uzh": ["uzh.ch"],
    "serafe": ["serafe.ch"],
    "billag": ["billag.ch"],
    "raiffeisen": ["raiffeisen.ch"],
    "migros": ["migros.ch"],
    "coop": ["coop.ch"],
    "paypal": ["paypal.com", "paypal.ch"],
    "mcafee": ["mcafee.com"],
    "norton": ["norton.com", "nortonlifelock.com"],
    "microsoft": ["microsoft.com"],
    "amazon": [
        "amazon.com",
        "amazon.co.uk",
        "amazon.de",
        "amazon.fr",
        "amazon.it",
        "amazon.es",
        "amazon.nl",
        "amazon.pl",
        "amazon.se",
        "amazon.ca",
        "amazon.com.au",
        "amazon.co.jp",
        "amazon.in",
        "amazon.com.br",
    ],
    "apple": ["apple.com"],
    "google": ["google.com", "googlemail.com"],
    "ubs": ["ubs.com", "ubs.ch"],
    "zkb": ["zkb.ch"],
    "kantonalbank": [
        "zkb.ch",
        "blkb.ch",
        "bkb.ch",
        "lukb.ch",
        "bcv.ch",
        "bekb.ch",
        "sgkb.ch",
        "tkb.ch",
        "valiant.ch",
        "raiffeisen.ch",
    ],
    "insta360": ["insta360.com"],
}

# Abwärtskompatibilität (Folder-Audit-Importe)
BRAND_DOMAIN_MAP = BUILTIN_BRAND_OFFICIAL_DOMAINS
BRAND_OFFICIAL_DOMAINS = BUILTIN_BRAND_OFFICIAL_DOMAINS


@dataclass(frozen=True)
class BrandMismatch:
    brand_key: str
    message: str
    host: str


def registrable_domain_from_host(host: str) -> str:
    host = (host or "").lower().strip().strip(".")
    if not host:
        return ""
    ext = _extract_host(host)
    if not ext.domain or not ext.suffix:
        return host
    return f"{ext.domain}.{ext.suffix}".lower()


def host_matches_official_domain(host: str, official_domains: Iterable[str]) -> bool:
    host = (host or "").lower().strip()
    for valid in official_domains:
        v = valid.lower().strip()
        if not v:
            continue
        if host == v or host.endswith("." + v):
            return True
    return False


def sender_on_official_brand_domain(
    sender_email: str,
    brand_map: Optional[Mapping[str, List[str]]] = None,
) -> bool:
    """Absender-Host passt zu einer konfigurierten offiziellen Marken-Domain."""
    host = _sender_host(sender_email)
    if not host or not brand_map:
        return False
    for officials in brand_map.values():
        if host_matches_official_domain(host, officials):
            return True
    return False


def merge_brand_maps(
    builtin: Mapping[str, List[str]],
    custom: Optional[Mapping[str, List[str]]],
) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {
        k: list(dict.fromkeys(d.lower() for d in v)) for k, v in builtin.items()
    }
    if not custom:
        return out
    for key, domains in custom.items():
        brand = _normalize_brand_key(key)
        if not brand:
            continue
        existing = out.setdefault(brand, [])
        for dom in domains:
            d = dom.lower().strip()
            if d and d not in existing:
                existing.append(d)
    return out


def effective_brand_map(custom: Optional[Mapping[str, List[str]]] = None) -> Dict[str, List[str]]:
    return merge_brand_maps(BUILTIN_BRAND_OFFICIAL_DOMAINS, custom)


def _normalize_brand_key(key: str) -> str:
    """Marke als Dict-Key; «&» → «and», damit z. B. h&m → handm (≥3 Zeichen)."""
    raw = (key or "").lower().strip()
    raw = raw.replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", raw)


def _brand_display_label(brand_key: str) -> str:
    """Anzeige z. B. handm → H&M wenn «and» aus &-Normalisierung stammt."""
    if "and" in brand_key:
        idx = brand_key.find("and")
        left, right = brand_key[:idx], brand_key[idx + 3 :]
        if left and right and len(left) + len(right) + 3 == len(brand_key):
            return f"{left.upper()}&{right.upper()}"
    return brand_key.upper()


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = mism = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            mism += 1
            if mism > 1:
                return False
            if la == lb:
                i += 1
                j += 1
            else:
                j += 1
    return mism + (lb - j) <= 1


def _damerau_levenshtein_at_most_one(a: str, b: str) -> bool:
    """Eine Ersetzung/Löschung/Einfügung oder eine benachbarte Vertauschung."""
    if _edit_distance_at_most_one(a, b):
        return True
    if len(a) != len(b):
        return False
    first: Optional[int] = None
    last: Optional[int] = None
    for i in range(len(a)):
        if a[i] != b[i]:
            if first is None:
                first = i
            last = i
    if first is None:
        return True
    if last is None or last - first != 1:
        return False
    i, j = first, first + 1
    return (
        a[i] == b[j]
        and a[j] == b[i]
        and a[:i] + a[j + 1 :] == b[:i] + b[j + 1 :]
    )


# Angehängte Schreibvarianten (PlanzerFT) — nicht normale Wörter wie «Amazonas».
_BRAND_PREFIX_MIN_KEY_LEN = 7
_BRAND_PREFIX_MAX_SUFFIX_LEN = 2


def _display_name_tokens(name_lower: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", name_lower or "")


def _brand_key_matches_display_name(brand_key: str, name_lower: str) -> bool:
    bk = (brand_key or "").lower()
    if not bk:
        return False
    if re.search(rf"\b{re.escape(bk)}\b", name_lower):
        return True
    for tok in _display_name_tokens(name_lower):
        if len(bk) >= _BRAND_PREFIX_MIN_KEY_LEN and tok.startswith(bk):
            extra = len(tok) - len(bk)
            if 0 < extra <= _BRAND_PREFIX_MAX_SUFFIX_LEN:
                return True
        if len(bk) >= 6 and _damerau_levenshtein_at_most_one(tok, bk):
            return True
    if "and" in bk:
        idx = brand_key.find("and")
        left, right = brand_key[:idx], brand_key[idx + 3 :]
        if left and right and len(left) + len(right) + 3 == len(brand_key):
            amp = rf"\b{re.escape(left)}\s*&\s*{re.escape(right)}\b"
            if re.search(amp, name_lower, re.I):
                return True
    return False


def _is_valid_official_domain(domain: str) -> bool:
    d = (domain or "").lower().strip().strip(".")
    if not d or len(d) > 253:
        return False
    if d in _BLOCKED_OFFICIAL_SUFFIXES:
        return False
    if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", d):
        return False
    labels = d.split(".")
    if len(labels) < 2:
        return False
    reg = registrable_domain_from_host(d)
    if reg in _BLOCKED_OFFICIAL_SUFFIXES:
        return False
    ext = _extract_host(d)
    if not ext.suffix or not ext.domain:
        return False
    if getattr(ext, "is_private", False):
        return False
    return True


def validate_brand_map(raw: Mapping) -> Tuple[Dict[str, List[str]], List[str]]:
    """Parst und validiert User-Map. Raises ValueError bei harten Fehlern."""
    errors: List[str] = []
    if not isinstance(raw, dict):
        raise ValueError("Marken-Liste muss ein JSON-Objekt sein")
    if len(raw) > MAX_BRANDS:
        raise ValueError(f"Maximal {MAX_BRANDS} Marken erlaubt")

    cleaned: Dict[str, List[str]] = {}
    for key, domains in raw.items():
        brand = _normalize_brand_key(str(key))
        if len(brand) < 3:
            errors.append(f"Ungültiger Markenname: {key!r}")
            continue
        if len(brand) > 32:
            errors.append(f"Markenname zu lang: {key!r}")
            continue
        if not isinstance(domains, list):
            errors.append(f"Domains für {brand} müssen eine Liste sein")
            continue
        if len(domains) > MAX_DOMAINS_PER_BRAND:
            errors.append(f"Maximal {MAX_DOMAINS_PER_BRAND} Domains pro Marke ({brand})")
            continue
        dom_clean: List[str] = []
        for dom in domains:
            d = str(dom).lower().strip().strip(".")
            if not _is_valid_official_domain(d):
                errors.append(f"Ungültige Domain für {brand}: {dom!r}")
                continue
            if d not in dom_clean:
                dom_clean.append(d)
        if dom_clean:
            cleaned[brand] = dom_clean
    if errors:
        raise ValueError("; ".join(errors[:20]))
    return cleaned, errors


def parse_brand_domains_text(text: str) -> Dict[str, List[str]]:
    """JSON `{...}` oder Zeilen `marke: dom1, dom2` / `marke dom1 dom2`."""
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        data = json.loads(raw)
        cleaned, _ = validate_brand_map(data)
        return cleaned
    result: Dict[str, List[str]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, rest = line.split(":", 1)
            domains = re.split(r"[\s,;]+", rest.strip())
        else:
            parts = line.split()
            if len(parts) < 2:
                continue
            key, domains = parts[0], parts[1:]
        brand = _normalize_brand_key(key)
        if not brand:
            continue
        bucket = result.setdefault(brand, [])
        for dom in domains:
            d = dom.lower().strip().strip(".")
            if d and d not in bucket:
                bucket.append(d)
    cleaned, _ = validate_brand_map(result)
    return cleaned


def brand_map_to_lines(brand_map: Mapping[str, List[str]]) -> str:
    lines = []
    for brand in sorted(brand_map.keys()):
        doms = ", ".join(sorted(brand_map[brand]))
        lines.append(f"{brand}: {doms}")
    return "\n".join(lines)


def _sender_host(sender_email: str) -> str:
    if not sender_email or "@" not in sender_email:
        return ""
    return sender_email.split("@")[-1].lower().strip(">").strip()


def _trusted_or_whitelist_skips(host: str, trusted_domains: Optional[Set[str]]) -> bool:
    if not host:
        return True
    for whitelist_domain in BRAND_CHECK_WHITELIST_DOMAINS:
        if host == whitelist_domain or host.endswith("." + whitelist_domain):
            return True
    if trusted_domains:
        for trusted in trusted_domains:
            t = trusted.lower()
            if host == t or host.endswith("." + t):
                return True
    return False


def _skip_ambiguous_brand_false_positive(brand: str, sender_name_lower: str) -> bool:
    if brand == "css" and re.search(r"css[-\s]*tricks", sender_name_lower, re.I):
        return True
    return False


def find_brand_domain_mismatch(
    sender_name: str,
    sender_email: str,
    brand_map: Mapping[str, List[str]],
    *,
    trusted_domains: Optional[Set[str]] = None,
    label: str = "Absender",
) -> Optional[BrandMismatch]:
    if not sender_name or not sender_email:
        return None
    host = _sender_host(sender_email)
    if _trusted_or_whitelist_skips(host, trusted_domains):
        return None
    name_lower = sender_name.lower()
    for brand, valid_domains in brand_map.items():
        if not _brand_key_matches_display_name(brand, name_lower):
            continue
        if _skip_ambiguous_brand_false_positive(brand, name_lower):
            continue
        if host_matches_official_domain(host, valid_domains):
            continue
        from src.services.tranco_popularity import tranco_exempts_brand_mismatch

        if tranco_exempts_brand_mismatch(sender_name, sender_email):
            continue
        label_brand = _brand_display_label(brand)
        return BrandMismatch(
            brand_key=brand,
            message=(
                f"«{label_brand}» in {label}, "
                f"Domain «{host}» passt nicht zu offiziellen Domains"
            ),
            host=host,
        )
    return None


def find_brand_token_in_unofficial_host(
    sender_email: str,
    brand_map: Mapping[str, List[str]],
    *,
    trusted_domains: Optional[Set[str]] = None,
) -> Optional[BrandMismatch]:
    """Marke im Domain-String (volles Label), aber nicht offizielle Domain (Lookalike-Host)."""
    from src.services.audit_scam_detection import is_relay_sender_domain
    from src.services.tranco_popularity import get_tranco_store, tranco_top_n_threshold

    host = _sender_host(sender_email)
    if not host or _trusted_or_whitelist_skips(host, trusted_domains):
        return None
    if is_relay_sender_domain(sender_email):
        return None
    reg = registrable_domain_from_host(host)
    store = get_tranco_store()
    if store and reg and store.is_in_top_n(reg, tranco_top_n_threshold()):
        return None
    labels = {p for p in re.split(r"[.-]", host.lower()) if p}
    for brand, valid_domains in brand_map.items():
        bk = brand.lower().strip()
        if len(bk) < 4 and bk in AMBIGUOUS_SHORT_BRANDS:
            continue
        if host_matches_official_domain(host, valid_domains):
            continue
        label_hit = bk in labels
        if not label_hit and len(bk) >= 6:
            for lab in labels:
                if lab == bk:
                    label_hit = True
                    break
                if lab.startswith(bk + "-") or lab.endswith("-" + bk):
                    label_hit = True
                    break
                # Lookalike-SLD: Marke als Präfix im Host-Label (nicht Substring in «hub»)
                if lab.startswith(bk) and len(lab) > len(bk):
                    label_hit = True
                    break
        if not label_hit:
            continue
        label_brand = _brand_display_label(brand)
        return BrandMismatch(
            brand_key=brand,
            message=(
                f"Domain «{host}» enthält Marke «{label_brand}», "
                "keine offizielle Domain"
            ),
            host=host,
        )
    return None


def _host_on_marketing_platform(host: str) -> bool:
    from src.services.shared_mail_infrastructure import MARKETING_PLATFORM_SUFFIXES

    reg = registrable_domain_from_host(host)
    if not reg:
        return False
    reg = reg.lower()
    for plat in MARKETING_PLATFORM_SUFFIXES:
        if reg == plat or reg.endswith("." + plat):
            return True
    return False


def find_shared_infra_brand_local_mismatch(
    sender_name: str,
    sender_email: str,
    brand_map: Mapping[str, List[str]],
    *,
    trusted_domains: Optional[Set[str]] = None,
) -> Optional[BrandMismatch]:
    """Marke im Anzeigenamen + Marke im Local-Part über Versandplattform (ccsend, …)."""
    if not sender_name or not sender_email:
        return None
    host = _sender_host(sender_email)
    if _trusted_or_whitelist_skips(host, trusted_domains):
        return None
    if not _host_on_marketing_platform(host):
        return None
    lp = sender_email.split("@", 1)[0].lower()
    lp_compact = re.sub(r"[._+\-]", "", lp)
    name_lower = sender_name.lower()
    for brand, valid_domains in brand_map.items():
        if not _brand_key_matches_display_name(brand, name_lower):
            continue
        if _skip_ambiguous_brand_false_positive(brand, name_lower):
            continue
        bk = brand.lower().strip()
        if len(bk) < 4 and bk in AMBIGUOUS_SHORT_BRANDS:
            continue
        if bk not in lp and bk not in lp_compact:
            continue
        if host_matches_official_domain(host, valid_domains):
            continue
        label_brand = _brand_display_label(brand)
        return BrandMismatch(
            brand_key=brand,
            message=(
                f"«{label_brand}» über Versandplattform «{host}», "
                "Marke im Local-Part — keine offizielle Domain"
            ),
            host=host,
        )
    return None


def display_brand_authorized_sender(
    display_name: str,
    sender_email: str,
    *,
    significant_tokens: List[str],
    brand_map: Optional[Mapping[str, List[str]]] = None,
) -> bool:
    brand_map = brand_map or BUILTIN_BRAND_OFFICIAL_DOMAINS
    host = _sender_host(sender_email)
    if not host:
        return False
    registrable = registrable_domain_from_host(host)
    matched_known_brand = False
    for tok in significant_tokens:
        brand_key = _normalize_brand_key(tok)
        if len(brand_key) < 3:
            continue
        official = brand_map.get(brand_key)
        if official is None:
            continue
        matched_known_brand = True
        if host_matches_official_domain(host, official):
            return True
        official_reg = {registrable_domain_from_host(d) for d in official}
        if registrable in official_reg:
            return True
    if matched_known_brand:
        return False
    return False


def brand_mismatch_secondary_signals(meta) -> bool:
    """Zweite Beweisklasse für Scam statt nur Review."""
    if getattr(meta, "server_spam_flag", False):
        return True
    junk = getattr(meta, "provider_junk_score", None)
    if junk is not None and junk >= 5:
        return True
    auth = (getattr(meta, "auth_results", None) or "").lower()
    if "dmarc=fail" in auth or "spf=fail" in auth:
        return True
    sender = getattr(meta, "sender", "") or ""
    if sender and "@" in sender:
        local = sender.split("@")[0].lower()
        if len(local) >= 14 and sum(c.isdigit() for c in local) >= 2:
            return True
    return False


def diff_brand_maps(
    current: Mapping[str, List[str]],
    proposed: Mapping[str, List[str]],
) -> Dict[str, object]:
    cur = {k: set(v) for k, v in current.items()}
    prop = {k: set(v) for k, v in proposed.items()}
    added = {k: sorted(prop[k] - cur.get(k, set())) for k in prop if prop[k] - cur.get(k, set())}
    removed = {k: sorted(cur[k] - prop.get(k, set())) for k in cur if cur[k] - prop.get(k, set())}
    new_brands = sorted(set(prop) - set(cur))
    dropped_brands = sorted(set(cur) - set(prop))
    return {
        "added_domains": added,
        "removed_domains": removed,
        "new_brands": new_brands,
        "dropped_brands": dropped_brands,
    }


def assert_safe_brand_list_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        raise ValueError("Nur HTTPS-URLs erlaubt")
    if not parsed.hostname:
        raise ValueError("Ungültige URL")
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        raise ValueError("Interne URLs nicht erlaubt")
    import ipaddress
    import socket

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Host nicht auflösbar: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Private/interne Zieladressen nicht erlaubt")
    return url.strip()


def fetch_https_text_for_brand_import(
    url: str,
    *,
    max_bytes: int = MAX_CUSTOM_JSON_BYTES,
) -> str:
    """HTTPS-GET ohne Redirects, begrenzte Größe (SSRF-Härtung für URL-Import)."""
    import requests as http_requests

    safe_url = assert_safe_brand_list_url(url)
    resp = http_requests.get(
        safe_url,
        timeout=10,
        allow_redirects=False,
        stream=True,
        headers={"User-Agent": "KI-Mail-Helper/brand-domain-import"},
    )
    if 300 <= resp.status_code < 400:
        resp.close()
        raise ValueError(
            f"Weiterleitung (HTTP {resp.status_code}) nicht erlaubt — "
            "bitte die finale HTTPS-URL zur Marken-Liste angeben"
        )
    resp.raise_for_status()
    chunks: List[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("Antwort zu gross (max. 64 KB)")
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace").strip()
