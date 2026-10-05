"""Freemail, Versandplattformen und Multi-Tenant-Hosting — eine Quelle für Scam + Tranco."""

from __future__ import annotations

import tldextract

_tld_extractor: tldextract.TLDExtract | None = None


def _extract(host: str) -> tldextract.ExtractResult:
    global _tld_extractor
    if _tld_extractor is None:
        _tld_extractor = tldextract.TLDExtract(include_psl_private_domains=True)
    return _tld_extractor(host)


# Registrable Domains — kein «beliebt = vertrauen»
FREEMAIL_REGISTRABLE = frozenset(
    {
        "example-freemail.ch",
        "example-freemail.de",
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "live.com",
        "hotmail.com",
        "hotmail.ch",
        "yahoo.com",
        "icloud.com",
        "web.de",
        "bluewin.ch",
        "gmx.ch",
        "gmx.net",
        "gmx.de",
        "t-online.de",
        "proton.me",
        "protonmail.com",
        "mail.com",
        "aol.com",
    }
)

MARKETING_PLATFORM_SUFFIXES = (
    "shopifyemail.com",
    "mailchimp.com",
    "sendgrid.net",
    "constantcontact.com",
    "hubspot.com",
    "sparkpost.com",
    "mailgun.org",
    "ccsend.com",
    "resend.dev",
)

MULTITENANT_REGISTRABLE_SUFFIXES = frozenset(
    {
        "github.io",
        "blogspot.com",
        "herokuapp.com",
        "web.app",
        "azurewebsites.net",
        "pages.dev",
        "vercel.app",
        "netlify.app",
        "appspot.com",
        "cloudfront.net",
        "amazonaws.com",
        "wixsite.com",
        "sites.google.com",
        "wordpress.com",
        "myshopify.com",
    }
)


def shared_infrastructure_registrable(reg: str) -> bool:
    """Freemail, Versandplattformen, öffentliche Hosting-/PSL-private Suffixe."""
    reg = (reg or "").lower().strip(".")
    if not reg:
        return True
    if reg in FREEMAIL_REGISTRABLE:
        return True
    for plat in MARKETING_PLATFORM_SUFFIXES:
        if reg == plat or reg.endswith("." + plat):
            return True
    if reg in MULTITENANT_REGISTRABLE_SUFFIXES:
        return True
    for suf in MULTITENANT_REGISTRABLE_SUFFIXES:
        if reg.endswith("." + suf):
            return True
    ext = _extract(reg)
    if ext.suffix:
        registered = (
            f"{ext.domain}.{ext.suffix}".lower() if ext.domain else ext.suffix.lower()
        )
        if registered in MULTITENANT_REGISTRABLE_SUFFIXES:
            return True
        if ext.suffix.lower() in MULTITENANT_REGISTRABLE_SUFFIXES:
            return True
    return False
