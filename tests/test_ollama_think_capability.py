"""Tests für Ollama Denk-Modus-Erkennung (gemocktes /api/show)."""
from unittest.mock import MagicMock, patch

import pytest

from src.services.ollama_think_capability import (
    clear_ollama_think_capability_cache,
    detect_ollama_think_capability,
    effective_ollama_think,
    ollama_chat_think_extras,
)


@pytest.fixture(autouse=True)
def _clear_cap_cache():
    clear_ollama_think_capability_cache()
    yield
    clear_ollama_think_capability_cache()


def test_effective_think_never():
    show = {"capabilities": ["completion"], "digest": "llama-dig"}
    with patch(
        "src.services.ollama_think_capability._fetch_show", return_value=show
    ):
        cap = detect_ollama_think_capability("llama3.2:1b", base_url="http://t")
    assert cap.mode == "never"
    assert effective_ollama_think("llama3.2:1b", True, cap=cap) is False


def test_effective_think_toggle_respects_user():
    cap = detect_ollama_think_capability("qwen3:8b")
    assert cap.mode == "toggle"
    assert effective_ollama_think("qwen3:8b", True, cap=cap) is True
    assert effective_ollama_think("qwen3:8b", False, cap=cap) is False


def test_show_thinking_capability_toggle():
    show = {"capabilities": ["thinking"], "digest": "abc123"}
    with patch(
        "src.services.ollama_think_capability._fetch_show", return_value=show
    ):
        cap = detect_ollama_think_capability("gpt-oss:20b", base_url="http://ollama.test")
    assert cap.mode == "toggle"
    assert cap.source == "show"
    extras = ollama_chat_think_extras(
        "gpt-oss:20b", True, base_url="http://ollama.test", cap=cap
    )
    assert extras == {"think": True}


def test_show_no_thinking_never_cached():
    show = {"capabilities": ["completion"], "digest": "def456"}
    with patch(
        "src.services.ollama_think_capability._fetch_show", return_value=show
    ):
        cap = detect_ollama_think_capability("llama3.2:1b", base_url="http://ollama.test")
    assert cap.mode == "never"
    assert cap.source == "show"


def test_show_unavailable_unknown_not_cached():
    with patch(
        "src.services.ollama_think_capability._fetch_show", return_value=None
    ):
        cap = detect_ollama_think_capability(
            "gpt-oss:20b", base_url="http://ollama.test"
        )
    assert cap.mode == "unknown"
    assert cap.source == "show_unavailable"
    cache_key = ("http://ollama.test", "gpt-oss:20b")
    from src.services import ollama_think_capability as mod

    assert cache_key not in mod._memory_cache


def test_qwen3_toggle_without_show():
    with patch(
        "src.services.ollama_think_capability._fetch_show", return_value=None
    ) as mock_show:
        cap = detect_ollama_think_capability("qwen3:8b")
    mock_show.assert_not_called()
    assert cap.mode == "toggle"
    assert cap.source == "qwen3"


def test_db_digest_mismatch_refetches():
    show = {"capabilities": ["thinking"], "digest": "new-digest"}
    db = MagicMock()
    row = MagicMock()
    row.think_mode = "never"
    row.model_digest = "old-digest"
    row.checked_at = None

    with patch(
        "src.services.ollama_think_capability._fetch_show", return_value=show
    ), patch(
        "src.services.ollama_think_capability._load_from_db",
        side_effect=[
            None,
            None,
        ],
    ), patch(
        "src.services.ollama_think_capability._save_to_db"
    ) as save:
        cap = detect_ollama_think_capability(
            "custom-model", base_url="http://ollama.test", db_session=db
        )
    assert cap.mode == "toggle"
    save.assert_called_once()
