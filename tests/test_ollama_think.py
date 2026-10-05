"""Ollama Qwen3 think payload helpers."""
from unittest.mock import MagicMock, patch

import pytest

from src.ollama_timeouts import (
    model_supports_ollama_think,
    ollama_chat_payload_extras,
    ollama_chat_request_options,
)
from src.services.ollama_think_capability import (
    OllamaThinkCapability,
    clear_ollama_think_capability_cache,
)


@pytest.fixture(autouse=True)
def _clear_cap_cache():
    clear_ollama_think_capability_cache()
    yield
    clear_ollama_think_capability_cache()


def test_model_supports_ollama_think():
    assert model_supports_ollama_think("qwen3:8b") is True
    assert model_supports_ollama_think("qwen3.8:27b") is True
    assert model_supports_ollama_think("llama3.2:1b") is False


def test_payload_extras_qwen3_default_think_false():
    with patch.dict("os.environ", {}, clear=False):
        extras = ollama_chat_payload_extras("qwen3:8b")
    assert extras == {"think": False}


def test_payload_extras_include_think_for_thinking_model():
    extras = ollama_chat_payload_extras(
        "gpt-oss:20b", think=True, include_think=True
    )
    assert extras == {"think": True}


def test_payload_extras_llama_omits_think():
    assert ollama_chat_payload_extras("llama3.2:1b") == {}


def test_request_options_higher_predict_when_think_active():
    with patch.dict("os.environ", {"OLLAMA_CHAT_NUM_PREDICT": "1024"}, clear=False):
        normal = ollama_chat_request_options(think_active=False)
        thinking = ollama_chat_request_options(think_active=True)
    assert normal["num_predict"] == 1024
    assert thinking["num_predict"] >= 4096


def test_post_chat_json_payload_includes_think_and_predict():
    import importlib

    ai_client = importlib.import_module("src.03_ai_client")
    with patch.object(
        ai_client.LocalOllamaClient, "_fetch_available_models", return_value=[]
    ), patch.object(
        ai_client.LocalOllamaClient, "_detect_model_type", return_value=False
    ), patch.object(
        ai_client.LocalOllamaClient, "_load_classifiers", return_value=None
    ):
        client = ai_client.LocalOllamaClient(model="qwen3:8b", ollama_think=False)
    cap = OllamaThinkCapability(mode="toggle", source="test")
    client._think_cap_cache = cap

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "message": {"content": '{"tags":[],"spam_flag":false}'}
        }
        return resp

    with patch.object(ai_client.requests, "post", side_effect=fake_post):
        client._post_chat_json(
            [{"role": "user", "content": "hi"}], subject="test"
        )

    assert captured["payload"].get("think") is False

    client.ollama_think = True
    with patch.object(ai_client.requests, "post", side_effect=fake_post):
        client._post_chat_json(
            [{"role": "user", "content": "hi"}], subject="test"
        )
    assert captured["payload"]["think"] is True
    assert captured["payload"]["options"]["num_predict"] >= 4096
