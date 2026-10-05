"""Sichere Werte für Security-Logs (fail2ban, Audit)."""

from __future__ import annotations

import re

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_log_field(value, *, max_len: int = 64) -> str:
    """Entfernt Zeilenumbrüche/Steuerzeichen — verhindert Log-Injection."""
    if value is None:
        return "-"
    text = str(value).strip()
    text = _CONTROL_RE.sub(" ", text)
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text or "-"
