#!/usr/bin/env python3
"""Tranco-Abdeckung: wie viele Eingabe-Domains liegen in Top-N der CSV?

Usage:
  python scripts/tranco_domain_coverage.py /path/to/top-1m.csv domains.txt

domains.txt: eine Domain pro Zeile (# Kommentare erlaubt).
Ausgabe: Tabelle mit Schwellen (nur Zahlen, für TRANCO_TOP_N-Entscheid).
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

# Repo-root on sys.path for `src.*` when run as script
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.services.brand_domain_policy import registrable_domain_from_host

THRESHOLDS = (
    10_000,
    20_000,
    50_000,
    100_000,
    200_000,
    300_000,
    500_000,
    1_000_000,
)


def _load_rank_index(path: Path) -> dict[str, int]:
    raw = path.read_bytes()
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if len(names) != 1:
                raise SystemExit(f"ZIP: expected 1 entry, got {len(names)}")
            raw = zf.read(names[0])
    text = raw.decode("utf-8", errors="replace")
    ranks: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        rank_s, domain = line.split(",", 1)
        try:
            rank = int(rank_s.strip())
        except ValueError:
            continue
        dom = domain.strip().lower().strip(".")
        if dom and dom not in ranks:
            ranks[dom] = rank
    return ranks


def _load_domains(path: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().lower().strip(".")
        if not line or line.startswith("#"):
            continue
        reg = registrable_domain_from_host(line) or line
        if reg not in seen:
            seen.add(reg)
            out.append(reg)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    tranco_path = Path(argv[1])
    domains_path = Path(argv[2])
    if not tranco_path.is_file():
        print(f"Tranco file not found: {tranco_path}", file=sys.stderr)
        return 1
    if not domains_path.is_file():
        print(f"Domains file not found: {domains_path}", file=sys.stderr)
        return 1

    ranks = _load_rank_index(tranco_path)
    domains = _load_domains(domains_path)
    if not domains:
        print("No domains in input file", file=sys.stderr)
        return 1

    total = len(domains)
    found = 0
    by_threshold = {t: 0 for t in THRESHOLDS}

    for dom in domains:
        r = ranks.get(dom)
        if r is None:
            continue
        found += 1
        for t in THRESHOLDS:
            if r <= t:
                by_threshold[t] += 1

    print(f"input_domains={total}")
    print(f"listed_in_tranco={found}")
    print(f"not_in_list={total - found}")
    print("threshold\tcount\tpercent_of_input")
    for t in THRESHOLDS:
        c = by_threshold[t]
        pct = (100.0 * c / total) if total else 0.0
        print(f"{t}\t{c}\t{pct:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
