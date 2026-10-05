"""Smoke-Test für Golden-Set-Benchmark (ohne echtes LLM)."""
from unittest.mock import patch

from src.services.audit_scam_benchmark import run_golden_hybrid_benchmark
from src.services.audit_scam_llm_config import AuditScamLlmConfig


def test_run_golden_hybrid_benchmark_rule_only_when_llm_disabled():
    cfg = AuditScamLlmConfig(
        enabled=False,
        provider="ollama",
        model="llama3.2:1b",
        think=False,
        base_url="http://127.0.0.1:11434",
        prompt_version=2,
        timeout=90,
        configured_via="user",
    )
    with patch(
        "src.services.audit_scam_detection.identity_llm_check",
        side_effect=AssertionError("LLM should not run"),
    ):
        result = run_golden_hybrid_benchmark(cfg)
    assert "tp" in result
    assert result["provider"] == "ollama"
    assert result["model"] == "llama3.2:1b"
