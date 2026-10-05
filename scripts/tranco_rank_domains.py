#!/usr/bin/env python3
"""Domain-Ränge gegen lokale Tranco-SQLite prüfen (CT-Auswertung, keine Mail-Daten).

Beispiel:
  TRANCO_DB_PATH=/opt/KI-Mail-Helper/data/tranco/tranco.db \\
  python scripts/tranco_rank_domains.py domains.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.tranco_popularity import get_tranco_store, tranco_top_n_threshold  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: tranco_rank_domains.py <domains-file>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    store = get_tranco_store()
    if store is None:
        print("Tranco DB missing — run update or set TRANCO_DB_PATH", file=sys.stderr)
        return 1
    top_n = tranco_top_n_threshold()
    lines = [ln.strip().lower() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    in_top = 0
    for dom in lines:
        r = store.rank(dom)
        tag = "MISS"
        if r is not None:
            if r <= 10_000:
                tag = "TOP10K"
            elif r <= top_n:
                tag = f"TOP{top_n}"
            else:
                tag = f"rank={r}"
            if r <= top_n:
                in_top += 1
        print(f"{dom}\t{tag}")
    print(f"\n{in_top}/{len(lines)} in top {top_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
