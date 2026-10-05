import importlib
import os


def test_ollama_timeout_defaults(monkeypatch):
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    monkeypatch.delenv("OLLAMA_EMBEDDING_TIMEOUT", raising=False)
    monkeypatch.delenv("OLLAMA_CHAT_NUM_CTX", raising=False)
    monkeypatch.delenv("CLASSIFICATION_BODY_MAX", raising=False)

    mod = importlib.import_module("src.ollama_timeouts")
    importlib.reload(mod)

    assert mod.OLLAMA_TIMEOUT == 900
    assert mod.OLLAMA_EMBEDDING_TIMEOUT == 120
    assert mod.OLLAMA_LLM_TASK_SOFT_LIMIT == 900
    assert mod.OLLAMA_LLM_TASK_HARD_LIMIT == 1020
    assert mod.OLLAMA_CHAT_NUM_CTX == 8192
    assert mod.OLLAMA_CHAT_NUM_PREDICT == 1024
    assert mod.CLASSIFICATION_BODY_MAX == 6000


def test_ollama_timeout_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT", "1200")
    monkeypatch.setenv("OLLAMA_EMBEDDING_TIMEOUT", "180")

    mod = importlib.import_module("src.ollama_timeouts")
    importlib.reload(mod)

    assert mod.OLLAMA_TIMEOUT == 1200
    assert mod.OLLAMA_EMBEDDING_TIMEOUT == 180
    assert mod.OLLAMA_LLM_TASK_HARD_LIMIT == 1320
