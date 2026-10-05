#!/usr/bin/env python3
"""Golden-Set-Auswertung (Regeln + optional Ollama). Siehe --help."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.golden_set import OWN_DOMAINS, ROWS  # noqa: E402
from src.services.audit_scam_detection import (  # noqa: E402
    evaluate_scam_risk,
    extract_domain,
    should_never_scam,
)
from src.services.audit_scam_llm_config import resolve_audit_scam_llm_config  # noqa: E402


@dataclass
class _Meta:
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    auth_results: Optional[str] = None
    reply_to: Optional[str] = None
    x_mailer: Optional[str] = None
    server_spam_flag: bool = False
    provider_junk_score: Optional[int] = None
    is_auto_generated: bool = False
    to_header: Optional[str] = None
    list_unsubscribe: Optional[str] = None


def row_to_meta(row) -> _Meta:
    _label, name, addr, subj, p, auth, lu = row
    if auth == "none":
        auth_results = "mailprovider.example; dkim=none; spf=pass; dmarc=none"
    elif auth == "fail":
        auth_results = "mailprovider.example; dkim=fail; spf=fail; dmarc=fail"
    else:
        auth_results = "mailprovider.example; dkim=pass; spf=pass; dmarc=pass"
    junk = 10 if p else None
    return _Meta(
        subject=subj,
        sender=addr,
        sender_name=name,
        auth_results=auth_results,
        server_spam_flag=bool(p),
        provider_junk_score=junk,
        list_unsubscribe="1" if lu else None,
    )


def _pred_from_eval(ev) -> str:
    if ev.is_scam:
        return "S"
    if getattr(ev, "identity_suspicion", False):
        return "U"
    if ev.needs_review_boost:
        return "U"
    return "O"


def rule_eval(row):
    label, name, addr, subj, p, auth, lu = row
    dom = extract_domain(addr)
    if dom in OWN_DOMAINS:
        meta = row_to_meta(row)
        if should_never_scam(meta, own_domains=OWN_DOMAINS):
            return "O", [], 0, 1 if p else 0
    meta = row_to_meta(row)
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    return _pred_from_eval(ev), ev.identity_rules, ev.transport_score, 1 if p else 0


def hybrid_eval(row, llm_cfg):
    dom = extract_domain(row[2])
    if dom in OWN_DOMAINS:
        meta = row_to_meta(row)
        if should_never_scam(meta, own_domains=OWN_DOMAINS):
            return "O", [], 0, 1 if row[4] else 0
    meta = row_to_meta(row)
    ev = evaluate_scam_risk(
        meta,
        llm_enabled=True,
        audit_llm_config=llm_cfg,
    )
    return _pred_from_eval(ev), ev.identity_rules, ev.transport_score, 1 if row[4] else 0


def report(title, preds, rows):
    tp = fp = fn = tn = 0
    fps, fns = [], []
    u = Counter()
    for row, v in zip(rows, preds):
        label = row[0]
        is_s = label == "S"
        if v == "U":
            u[label] += 1
        if v == "S" and is_s:
            tp += 1
        elif v == "S" and not is_s:
            fp += 1
            fps.append((label, row[1], row[2]))
        elif v != "S" and is_s:
            fn += 1
            fns.append((row[1], row[2], v))
        else:
            tn += 1
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    print(f"\n== {title} ==")
    print(f"SCAM: TP={tp} FP={fp} FN={fn} TN={tn}  Präzision={prec:.0%}  Trefferquote={rec:.0%}")
    print('  "unklar" je Klasse:', dict(u))
    for x in fps[:12]:
        print("  FALSCHALARM", x)
    for x in fns[:12]:
        print("  VERFEHLT", x)
    return fns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="Nur Layer-1-Regeln")
    ap.add_argument(
        "--hybrid",
        action="store_true",
        help="Layer 1 + Ollama Identitäts-KI (Prompt v2, Hybrid-Zweitbeleg)",
    )
    args = ap.parse_args()
    rows = ROWS
    print("Golden Set:", len(rows), dict(Counter(r[0] for r in rows)))

    preds = [rule_eval(r)[0] for r in rows]
    report("PRODUKTIONS-REGELN (Layer 1)", preds, rows)

    if args.hybrid and not args.dry:
        cfg = resolve_audit_scam_llm_config(None)
        print(
            f"\nHybrid-Lauf: model={cfg.model} prompt_v={cfg.prompt_version} "
            f"think={cfg.think} (ruft Ollama pro Grauzeilen-Mail)"
        )
        hybrid_preds = [hybrid_eval(r, cfg)[0] for r in rows]
        report("HYBRID (Layer 1 + Identitäts-KI)", hybrid_preds, rows)
    elif not args.dry:
        print("\nOptional: --hybrid für Ollama-Auswertung (siehe /settings Audit-LLM)")


if __name__ == "__main__":
    main()
