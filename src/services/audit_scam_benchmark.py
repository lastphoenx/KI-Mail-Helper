"""Golden-Set-Benchmark für Ordner-Audit Identitäts-KI (Hybrid-Pipeline)."""
from __future__ import annotations

import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from src.services.audit_scam_detection import (
    clear_audit_scam_caches,
    evaluate_scam_risk,
    extract_domain,
    should_never_scam,
)
from src.services.audit_scam_llm_config import AuditScamLlmConfig


def _row_to_meta(row):
    from scripts.eval_scam import row_to_meta

    return row_to_meta(row)


def _pred_from_eval(ev) -> str:
    if ev.is_scam:
        return "S"
    if ev.needs_review_boost:
        return "U"
    return "O"


def run_golden_hybrid_benchmark(cfg: AuditScamLlmConfig) -> Dict[str, Any]:
    """Layer 1 + LLM Hybrid auf synthetischem Golden Set."""
    from scripts.golden_set import OWN_DOMAINS, ROWS

    clear_audit_scam_caches()
    t0 = time.time()
    preds: List[str] = []
    for row in ROWS:
        dom = extract_domain(row[2])
        if dom in OWN_DOMAINS:
            meta = _row_to_meta(row)
            if should_never_scam(meta, own_domains=OWN_DOMAINS):
                preds.append("O")
                continue
        meta = _row_to_meta(row)
        ev = evaluate_scam_risk(
            meta,
            llm_enabled=True,
            audit_llm_config=cfg,
        )
        preds.append(_pred_from_eval(ev))

    tp = fp = fn = tn = 0
    fps: List[Tuple] = []
    for row, pred in zip(ROWS, preds):
        label = row[0]
        is_s = label == "S"
        if pred == "S" and is_s:
            tp += 1
        elif pred == "S" and not is_s:
            fp += 1
            fps.append((label, row[1], row[2]))
        elif pred != "S" and is_s:
            fn += 1
        else:
            tn += 1

    duration = round(time.time() - t0, 1)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "duration_sec": duration,
        "model": cfg.model,
        "provider": cfg.provider,
        "think": cfg.think,
        "prompt_version": cfg.prompt_version,
        "false_positives": fps[:15],
        "label_counts": dict(Counter(r[0] for r in ROWS)),
    }
