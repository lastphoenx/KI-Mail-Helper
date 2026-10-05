"""Smoke: alle Python-Module unter src/ müssen importier-/parsebar sein."""

import compileall
from pathlib import Path


def test_src_tree_compiles():
    root = Path(__file__).resolve().parents[1] / "src"
    ok = compileall.compile_dir(str(root), quiet=1)
    assert ok, "compileall found syntax errors under src/"
