"""Deferred LLM batch: Ranking und Budget (synthetisch)."""

import time
from types import SimpleNamespace
from unittest.mock import patch

from src.services.audit_scam_detection import (
    AuditScanContext,
    ScamEvaluation,
    run_deferred_llm_batch,
)
from src.services.audit_scam_llm_config import AuditScamLlmConfig


def _meta(n: int):
    return SimpleNamespace(
        subject=f"Subject {n}",
        sender=f"user{n}@example-freemail.ch",
        sender_name=f"Org {n}",
        auth_results=None,
        reply_to=None,
        x_mailer=None,
        server_spam_flag=False,
        provider_junk_score=None,
        is_auto_generated=False,
        to_header=None,
        list_unsubscribe=None,
    )


def _cfg():
    return AuditScamLlmConfig(
        enabled=True,
        provider="ollama",
        model="test-model:7b",
        think=False,
        base_url="http://127.0.0.1:11434",
        prompt_version=2,
        timeout=30,
        configured_via="env",
    )


def test_deferred_batch_respects_count_budget():
    ctx = AuditScanContext(llm_budget=1, llm_time_budget_sec=120.0)
    ctx.pending.append((_meta(1), ScamEvaluation(llm_deferred=True, llm_priority=50)))
    ctx.pending.append((_meta(2), ScamEvaluation(llm_deferred=True, llm_priority=90)))

    calls = []

    def fake_check(meta, *, cfg, db_session=None, manual_user_id=None, **_kw):
        calls.append(meta.sender)
        return {"verdict": "O", "reason": None}

    with patch(
        "src.services.audit_scam_detection.identity_llm_check",
        side_effect=fake_check,
    ), patch(
        "src.services.audit_scam_detection._llm_result_usable",
        side_effect=lambda r, m: r,
    ):
        out = run_deferred_llm_batch(ctx, cfg=_cfg())

    assert len(calls) == 1
    assert calls[0] == "user2@example-freemail.ch"
    assert ctx.skipped_candidates == 1
    assert len(ctx.pending) == 1
    assert len(out) == 1


def test_deferred_batch_time_budget_starts_when_batch_begins():
    """Langer IMAP-Scan darf die LLM-Phase nicht ausschalten (Uhr reset im Batch)."""
    ctx = AuditScanContext(llm_budget=2, llm_time_budget_sec=120.0)
    ctx.start_monotonic = time.monotonic() - 400.0
    ctx.pending.append((_meta(1), ScamEvaluation(llm_deferred=True, llm_priority=50)))

    calls = []

    def fake_check(meta, *, cfg, db_session=None, manual_user_id=None, **_kw):
        calls.append(meta.sender)
        return {"verdict": "O", "reason": None}

    with patch(
        "src.services.audit_scam_detection.identity_llm_check",
        side_effect=fake_check,
    ), patch(
        "src.services.audit_scam_detection._llm_result_usable",
        side_effect=lambda r, m: r,
    ):
        out = run_deferred_llm_batch(ctx, cfg=_cfg())

    assert len(calls) == 1
    assert len(out) == 1
    assert ctx.skipped_candidates == 0


def test_deferred_batch_manual_quota_none_keeps_pending():
    """Bei None (Tageslimit/Fehler): nicht abhaken; Rest bleibt pending."""
    ctx = AuditScanContext(llm_budget=10, llm_time_budget_sec=120.0)
    for n in (1, 2, 3):
        ctx.pending.append(
            (_meta(n), ScamEvaluation(llm_deferred=True, llm_priority=100 - n))
        )

    call_count = [0]

    def fake_check(meta, *, cfg, db_session=None, manual_user_id=None, **_kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return {"verdict": "O", "reason": None}
        return None

    with patch(
        "src.services.audit_scam_detection.identity_llm_check",
        side_effect=fake_check,
    ), patch(
        "src.services.audit_scam_detection._llm_result_usable",
        side_effect=lambda r, m: r,
    ):
        out = run_deferred_llm_batch(ctx, cfg=_cfg(), manual_user_id=99)

    assert call_count[0] == 2
    assert len(out) == 1
    assert len(ctx.pending) == 2


def test_deferred_batch_unusable_marks_checked_not_pending():
    ctx = AuditScanContext(llm_budget=5, llm_time_budget_sec=120.0)
    ctx.pending.append((_meta(1), ScamEvaluation(llm_deferred=True, llm_priority=50)))

    def fake_check(meta, *, cfg, db_session=None, manual_user_id=None, **_kw):
        return {
            "mismatch": True,
            "confidence": 90,
            "reason": "typisch für serafech.com (Typosquatting)",
            "impersonated": "serafe.ch",
        }

    with patch(
        "src.services.audit_scam_detection.identity_llm_check",
        side_effect=fake_check,
    ):
        out = run_deferred_llm_batch(ctx, cfg=_cfg())

    assert len(out) == 1
    assert len(ctx.pending) == 0
    assert out[0][1].llm_unusable


def test_format_llm_pending_notice_mixed_reasons():
    from src.services.audit_scam_detection import format_llm_pending_notice

    ctx = AuditScanContext(llm_budget=150, llm_time_budget_sec=600.0)
    pending = [
        (_meta(1), ScamEvaluation(llm_skip_reason="budget")),
        (_meta(2), ScamEvaluation(llm_skip_reason="error")),
    ]
    msg = format_llm_pending_notice(pending, ctx)
    assert "Scan-Budget" in msg
    assert "LLM-Fehler" in msg
    assert msg.startswith("2 LLM-Kandidaten nicht geprüft:")
