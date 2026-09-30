import importlib
import json
from unittest.mock import MagicMock, patch

import pytest


def _reload_ollama_timeouts(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, str(value))
    mod = importlib.import_module("src.ollama_timeouts")
    importlib.reload(mod)
    return mod


def test_truncate_for_classification_short_body(monkeypatch):
    mod = _reload_ollama_timeouts(monkeypatch, CLASSIFICATION_BODY_MAX=6000)
    body = "Kurze Mail"
    assert mod.truncate_for_classification(body) == body


def test_truncate_for_classification_long_body(monkeypatch):
    mod = _reload_ollama_timeouts(monkeypatch, CLASSIFICATION_BODY_MAX=100)
    body = "x" * 500
    result = mod.truncate_for_classification(body)
    assert len(result) <= 100
    assert result.endswith("KI-Klassifizierung ...]")


def test_ollama_chat_request_options_from_env(monkeypatch):
    mod = _reload_ollama_timeouts(
        monkeypatch,
        OLLAMA_CHAT_NUM_CTX="16384",
        OLLAMA_CHAT_NUM_PREDICT="512",
    )
    assert mod.ollama_chat_request_options() == {
        "num_ctx": 16384,
        "num_predict": 512,
    }


def test_validate_ai_payload_coerces_dict_fields():
    ai_client = importlib.import_module("src.03_ai_client")
    payload = ai_client._validate_ai_payload(
        {
            "dringlichkeit": 2,
            "wichtigkeit": 3,
            "summary_de": {"foo": "bar"},
            "text_de": ["line1", "line2"],
            "tags": [{"bad": "tag"}, "ok"],
            "suggested_tags": [123],
        }
    )
    assert json.loads(payload["summary_de"]) == {"foo": "bar"}
    assert payload["text_de"] == json.dumps(["line1", "line2"], ensure_ascii=False)
    assert payload["tags"] == [json.dumps({"bad": "tag"}, ensure_ascii=False), "ok"]
    assert payload["suggested_tags"] == ["123"]


def test_analyze_email_posts_bounded_chat_options(monkeypatch):
    ai_client = importlib.import_module("src.03_ai_client")
    monkeypatch.setenv("OLLAMA_CHAT_NUM_CTX", "8192")
    monkeypatch.setenv("OLLAMA_CHAT_NUM_PREDICT", "1024")
    monkeypatch.setenv("OLLAMA_CHAT_KEEP_ALIVE", "10m")
    importlib.reload(importlib.import_module("src.ollama_timeouts"))
    importlib.reload(ai_client)

    client = ai_client.LocalOllamaClient(model="llama3.2:1b")
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "message": {
                "content": json.dumps(
                    {
                        "dringlichkeit": 1,
                        "wichtigkeit": 1,
                        "kategorie_aktion": "nur_information",
                        "tags": [],
                        "suggested_tags": [],
                        "spam_flag": False,
                        "summary_de": "ok",
                        "text_de": "",
                    }
                )
            }
        }
        return response

    long_body = "A" * 20000
    with patch("src.03_ai_client.requests.post", side_effect=fake_post):
        result = client.analyze_email(subject="Test", body=long_body)

    assert result["summary_de"] == "ok"
    assert "options" in captured["json"]
    assert captured["json"]["options"]["num_ctx"] == 8192
    assert captured["json"]["options"]["num_predict"] == 1024
    assert captured["json"]["keep_alive"] == "10m"
    assert "KI-Klassifizierung" in captured["json"]["messages"][1]["content"]


def test_renew_sync_lock_extends_ttl():
    mail_sync = importlib.import_module("src.tasks.mail_sync_tasks")
    redis_client = MagicMock()
    redis_client.get.return_value = b"task-abc"
    mail_sync._renew_sync_lock(redis_client, "lock-key", "task-abc", 7200)
    redis_client.expire.assert_called_once_with("lock-key", 7200)
