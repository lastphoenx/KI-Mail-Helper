"""Wächter: keine Konten, Marken oder Ordner als Logik-Literale in src/services."""

import ast
import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "src" / "services"
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
ALLOWED_HOSTS = {
    "example.com",
    "example.org",
    "example.net",
    "firma.de",
    "domain.com",
    "localhost",
}


def _host_allowed(email: str) -> bool:
    host = email.split("@", 1)[-1].lower()
    if host in ALLOWED_HOSTS or host.endswith(".example"):
        return True
    return False


def _mark_tree(node, bucket: set) -> None:
    bucket.add(id(node))
    for child in ast.iter_child_nodes(node):
        _mark_tree(child, bucket)


def _data_table_ids(tree: ast.AST) -> set:
    allowed: set = set()
    for node in getattr(tree, "body", []):
        targets = []
        value = None
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        if all(isinstance(t, ast.Name) and t.id.isupper() for t in targets):
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


def test_services_have_no_account_email_literals():
    offenders = []
    for path in sorted(SERVICES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        allowed = _data_table_ids(tree) | _docstring_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in allowed:
                continue
            for email in EMAIL_RE.findall(node.value):
                if not _host_allowed(email):
                    offenders.append(f"{path.name}:{node.lineno}:{email}")
    assert offenders == []


def test_informativ_is_not_a_curated_marker():
    text = (SERVICES / "audit_identity_helpers.py").read_text(encoding="utf-8")
    assert "informativ" not in text
