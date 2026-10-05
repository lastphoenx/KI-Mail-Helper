"""User-Ollama-Think-Präferenzen für Base/Optimize."""
from __future__ import annotations

import importlib
from typing import Literal, Optional

Role = Literal["base", "optimize"]


def _ai_client():
    return importlib.import_module("src.03_ai_client")


def user_ollama_think_pref(user, role: Role) -> bool:
    if role == "base":
        val = getattr(user, "preferred_ai_think_base", None)
    else:
        val = getattr(user, "preferred_ai_think_optimize", None)
    return bool(val) if val is not None else False


def build_client_for_user_role(user, role: Role, *, model: Optional[str] = None):
    ai = _ai_client()
    if role == "base":
        provider = (user.preferred_ai_provider or "ollama").lower()
        resolved = ai.resolve_model(provider, model or user.preferred_ai_model)
        think = user_ollama_think_pref(user, "base")
    else:
        provider = (user.preferred_ai_provider_optimize or "ollama").lower()
        resolved = ai.resolve_model(
            provider, model or user.preferred_ai_model_optimize
        )
        think = user_ollama_think_pref(user, "optimize")
    kwargs = {}
    if provider == "ollama":
        kwargs["ollama_think"] = think
    return ai.build_client(provider, model=resolved, **kwargs)
