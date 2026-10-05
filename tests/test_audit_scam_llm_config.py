"""Tests für resolve_audit_scam_llm_config (User vs .env)."""
from dataclasses import dataclass
from unittest.mock import patch

from src.services.audit_scam_llm_config import (
    model_supports_ollama_think,
    resolve_audit_scam_llm_config,
)


@dataclass
class _User:
    audit_scam_llm_enabled: bool | None = None
    audit_scam_llm_model: str | None = None
    audit_scam_llm_think: bool | None = None
    audit_scam_llm_provider: str | None = None


def test_resolve_env_defaults():
    with patch.dict(
        "os.environ",
        {
            "AUDIT_SCAM_LLM_ENABLED": "false",
            "AUDIT_SCAM_LLM_MODEL": "test-model:7b",
            "AUDIT_SCAM_LLM_THINK": "true",
            "OLLAMA_BASE_URL": "http://ollama.example:11434",
        },
        clear=False,
    ):
        cfg = resolve_audit_scam_llm_config(None)
    assert cfg.enabled is False
    assert cfg.model == "test-model:7b"
    assert cfg.think is False
    assert cfg.base_url == "http://ollama.example:11434"
    assert cfg.configured_via == "env"


def test_resolve_user_overrides_env():
    user = _User(
        audit_scam_llm_enabled=True,
        audit_scam_llm_model="user-model:27b",
        audit_scam_llm_think=False,
    )
    with patch.dict(
        "os.environ",
        {"AUDIT_SCAM_LLM_ENABLED": "false", "AUDIT_SCAM_LLM_MODEL": "env-model"},
        clear=False,
    ):
        cfg = resolve_audit_scam_llm_config(user)
    assert cfg.enabled is True
    assert cfg.model == "user-model:27b"
    assert cfg.think is False
    assert cfg.configured_via == "user"


def test_think_only_for_qwen3_ollama():
    user = _User(
        audit_scam_llm_enabled=True,
        audit_scam_llm_model="qwen3:8b",
        audit_scam_llm_think=True,
        audit_scam_llm_provider="ollama",
    )
    cfg = resolve_audit_scam_llm_config(user)
    assert cfg.think is True
    assert model_supports_ollama_think("qwen3.8:27b") is True
    assert model_supports_ollama_think("llama3.2:1b") is False


def test_cloud_provider_clears_think():
    user = _User(
        audit_scam_llm_enabled=True,
        audit_scam_llm_model="gpt-4o-mini",
        audit_scam_llm_think=True,
        audit_scam_llm_provider="openai",
    )
    cfg = resolve_audit_scam_llm_config(user)
    assert cfg.provider == "openai"
    assert cfg.think is False
