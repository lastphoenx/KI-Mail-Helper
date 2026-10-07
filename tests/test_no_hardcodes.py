"""Wächter: keine Konten, Marken oder Ordner als Logik-Literale in src/services."""

import ast
import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "src" / "services"
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
DOMAIN_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|ch|de|at|fr|it|li|eu|io|co|uk)(?![A-Za-z0-9])"
)
ALLOWED_HOSTS = {
    "example.com",
    "example.org",
    "example.net",
    "firma.de",
    "domain.com",
    "localhost",
}
# Ordner, die nicht als Logik fest verdrahtet sein dürfen (kommen aus der UI).
FORBIDDEN_FOLDER_LITERALS = {"informativ"}
# Nur diese UPPER_SNAKE-Tabellen dürfen Hosts/Marken enthalten.
# brand_domain_policy.py ist zusätzlich komplett ausgenommen.
# Jede neue Konstante wird geprüft — das ist Absicht.
ALLOWED_UPPER_TABLES = frozenset(
    {
        "AMBIGUOUS_SHORT_BRANDS",
        "BRAND_CHECK_WHITELIST_DOMAINS",
        "BRAND_DOMAIN_MAP",
        "BRAND_OFFICIAL_DOMAINS",
        "BUILTIN_BRAND_OFFICIAL_DOMAINS",
        "CAMPAIGN_INFRA_REGISTRABLE_DOMAINS",
        "CC_TLDS",
        "DEFAULT_BULK_MERGE_BLOCK_DOMAINS",
        "DISPOSABLE_DOMAIN_PATTERNS",
        "FREEMAIL_DOMAINS",
        "FREEMAIL_REGISTRABLE",
        "MARKETING_PLATFORMS",
        "MARKETING_PLATFORM_SUFFIXES",
        "MULTITENANT_REGISTRABLE_SUFFIXES",
        "RDAP_NIC_CH_BASE",
        "RDAP_TLD_OVERRIDES",
        "RELAY_SENDER_DOMAINS",
        "SCAM_DOMAIN_PATTERNS",
        "HOMOGLYPH_MAP",
        "KNOWN_SPAM_MAILER_PATTERNS",
        "SUGGESTED_STRICT_BULK_MERGE_BLOCK_DOMAINS",
        "TYPOSQUATTING_TARGETS",
        "TRANCO_DAILY_ZIP_URL",
        "TRANCO_DOWNLOAD_HOST",
        "TRUSTED_AUTH_PROVIDER_DOMAINS",
        "TRUSTED_GLOBAL_DOMAINS",
        "TRUSTED_SWISS_BASE",
        "TRUSTED_SWISS_DOMAINS",
    }
)


def _host_allowed(host: str) -> bool:
    host = (host or "").lower().strip(".")
    if host in ALLOWED_HOSTS or host.endswith(".example"):
        return True
    return False


def _mark_tree(node, bucket: set) -> None:
    bucket.add(id(node))
    for child in ast.iter_child_nodes(node):
        _mark_tree(child, bucket)


def _assignment_names(node):
    if isinstance(node, ast.Assign):
        return [
            t.id
            for t in node.targets
            if isinstance(t, ast.Name)
        ], node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id], node.value
    return [], None


def _exempt_ids(tree: ast.AST, path: Path) -> set:
    """Docstrings plus explizit erlaubte Datentabellen. Nicht jedes UPPER_SNAKE."""
    allowed: set = set()
    brand_file = path.name == "brand_domain_policy.py"
    for node in getattr(tree, "body", []):
        names, value = _assignment_names(node)
        if value is None or not names:
            continue
        upper = all(name.isupper() for name in names)
        if brand_file and upper:
            _mark_tree(value, allowed)
            continue
        if all(name in ALLOWED_UPPER_TABLES for name in names):
            _mark_tree(value, allowed)
    return allowed


def _docstring_ids(tree: ast.AST) -> set:
    found: set = set()

    def consider(body):
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            found.add(id(body[0].value))

    consider(getattr(tree, "body", []))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            consider(node.body)
    return found


def _builtin_brand_keys() -> set:
    from src.services.brand_domain_policy import BUILTIN_BRAND_OFFICIAL_DOMAINS

    return {key.lower() for key in BUILTIN_BRAND_OFFICIAL_DOMAINS if len(key) >= 4}


def _module_checked_ids(tree: ast.AST, path: Path, exempt: set) -> set:
    """Modul-Zuweisungen, die nicht auf der Allowlist stehen."""
    checked: set = set()
    for node in getattr(tree, "body", []):
        names, value = _assignment_names(node)
        if value is None:
            continue
        if id(value) in exempt:
            continue
        _mark_tree(value, checked)
    return checked


def test_services_have_no_account_email_literals():
    brand_keys = _builtin_brand_keys()
    from src.services.brand_domain_policy import BUILTIN_BRAND_OFFICIAL_DOMAINS

    official_hosts = {
        host.lower()
        for domains in BUILTIN_BRAND_OFFICIAL_DOMAINS.values()
        for host in domains
    }
    offenders = []
    for path in sorted(SERVICES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        exempt = _exempt_ids(tree, path) | _docstring_ids(tree)
        checked = _module_checked_ids(tree, path, exempt)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in exempt:
                continue
            text = node.value
            for email in EMAIL_RE.findall(text):
                if not _host_allowed(email.split("@", 1)[-1]):
                    offenders.append(f"{path.name}:{node.lineno}:email:{email}")
            if id(node) not in checked:
                continue
            whole = text.strip().lower()
            if DOMAIN_RE.fullmatch(whole) and not _host_allowed(whole):
                offenders.append(f"{path.name}:{node.lineno}:domain:{whole}")
            if whole in brand_keys or whole in official_hosts:
                if path.name != "brand_domain_policy.py":
                    offenders.append(f"{path.name}:{node.lineno}:brand:{whole}")
            if whole in FORBIDDEN_FOLDER_LITERALS:
                offenders.append(f"{path.name}:{node.lineno}:folder:{whole}")
    assert offenders == []


def test_informativ_is_not_a_curated_marker():
    text = (SERVICES / "audit_identity_helpers.py").read_text(encoding="utf-8")
    assert "informativ" not in text
