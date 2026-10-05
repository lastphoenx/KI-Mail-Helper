"""Pytest-Import: kanonische Daten liegen in scripts/golden_set.py (keine Duplikate)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "scripts" / "golden_set.py"
_spec = importlib.util.spec_from_file_location("_scam_golden_set_data", _path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

OWN_DOMAINS = _mod.OWN_DOMAINS
ROWS = _mod.ROWS
