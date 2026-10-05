"""Modell-Freigabe: .env, Registry, UI-Filter, Anzeigenamen."""

from __future__ import annotations

import fnmatch
import importlib
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

MODEL_ROLES = frozenset({"base", "optimize", "embedding", "audit"})

_SNAPSHOT_DATE_SUFFIX = re.compile(r"-(\d{4})-(\d{2})-(\d{2})$")
_AUXILIARY_SUBSTRINGS = (
    "-preview",
    "-codex",
    "-search-preview",
    "-search",
    "-chat-latest",
    "-transcribe",
    "-realtime",
)


def _env_allowlist_key(provider: str, role: str) -> str:
    return f"AI_MODELS_{provider.strip().upper()}_{role.strip().upper()}"


def parse_env_allowlist(provider: str, role: str) -> Optional[List[str]]:
    """None = Variable nicht gesetzt; leere Liste nach Split = keine Einträge → None."""
    key = _env_allowlist_key(provider, role)
    raw = os.getenv(key)
    if raw is None:
        return None
    patterns = [p.strip() for p in raw.split(",") if p.strip()]
    return patterns if patterns else None


def ui_snapshot_filter_enabled() -> bool:
    val = os.getenv("AI_MODELS_UI_FILTER", "true").strip().lower()
    return val not in ("0", "false", "no", "off")


def is_auxiliary_model_id(model_id: str, provider: str) -> bool:
    if not model_id:
        return True
    if provider.lower() == "ollama":
        return False
    mid = model_id.lower()
    if _SNAPSHOT_DATE_SUFFIX.search(model_id):
        return True
    return any(token in mid for token in _AUXILIARY_SUBSTRINGS)


def format_model_display_name(
    provider: str, model_id: str, fallback: Optional[str] = None
) -> str:
    """Lesbare Bezeichnung, z. B. gpt-5.5-pro-2026-04-23 → GPT-5.5 Pro (23.04.2026)."""
    if not model_id:
        return fallback or ""

    display = fallback or model_id
    if provider.lower() != "openai":
        return display

    m = _SNAPSHOT_DATE_SUFFIX.search(model_id)
    base_id = model_id[: m.start()] if m else model_id
    name = base_id.replace("_", " ")

    parts = name.split("-")
    out: List[str] = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "gpt" and i + 1 < len(parts):
            nxt = parts[i + 1]
            if nxt.startswith("4") or nxt.startswith("3") or nxt.startswith("5"):
                out.append(f"GPT-{nxt}")
                i += 2
                continue
        if p in ("o1", "o3", "o4") and i + 1 < len(parts):
            out.append(f"{p.upper()}-{parts[i + 1]}")
            i += 2
            continue
        if p == "text" and i + 2 < len(parts) and parts[i + 1] == "embedding":
            out.append(f"Text Embedding {parts[i + 2]}")
            i += 3
            continue
        out.append(p.upper() if len(p) <= 3 else p.capitalize())
        i += 1

    label = " ".join(out)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        label = f"{label} ({d}.{mo}.{y})"
    return label


def _registry_cfg(provider: str) -> Dict[str, Any]:
    try:
        ai_client = importlib.import_module("src.03_ai_client")
        return getattr(ai_client, "PROVIDER_REGISTRY", {}).get(provider.lower(), {})
    except ImportError:
        return {}


def registry_allowlist(provider: str, role: str) -> Optional[List[str]]:
    cfg = _registry_cfg(provider)
    if not cfg:
        return None
    role = role.lower()
    if role == "base":
        lst = cfg.get("models_base") or []
    elif role == "optimize":
        lst = cfg.get("models_optimize") or []
    elif role == "embedding":
        lst = cfg.get("models_embedding") or []
        if not lst and provider.lower() == "ollama":
            lst = [m for m in (cfg.get("models") or []) if "minilm" in m or "embed" in m.lower()]
    elif role == "audit":
        lst = cfg.get("models_audit") or cfg.get("models_optimize") or []
    else:
        return None
    cleaned = [x for x in lst if isinstance(x, str) and x.strip()]
    return cleaned if cleaned else None


def resolve_allowlist_patterns(provider: str, role: str) -> Optional[List[str]]:
    """Env schlägt Registry; None = keine Allowlist-Einschränkung."""
    env_list = parse_env_allowlist(provider, role)
    if env_list is not None:
        return env_list
    reg = registry_allowlist(provider, role)
    return reg if reg else None


def model_matches_allowlist(patterns: Sequence[str], model_id: str) -> bool:
    if not model_id:
        return False
    for pat in patterns:
        if fnmatch.fnmatchcase(model_id, pat):
            return True
        if pat == model_id:
            return True
    return False


def _log_unmatched_patterns(
    provider: str, role: str, patterns: Sequence[str], candidate_ids: Sequence[str]
) -> None:
    for pat in patterns:
        if not any(model_matches_allowlist([pat], mid) for mid in candidate_ids):
            logger.warning(
                "AI_MODELS Allowlist: Pattern %r für %s/%s trifft kein Modell (Tippfehler?)",
                pat,
                provider,
                role,
            )


def apply_standard_ui_filter(
    provider: str, models: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not ui_snapshot_filter_enabled():
        return list(models)
    return [
        m
        for m in models
        if not is_auxiliary_model_id((m.get("id") or m.get("name") or ""), provider)
    ]


def filter_models_for_role(
    provider: str,
    role: str,
    models: List[Dict[str, Any]],
    saved_model_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if role.lower() not in MODEL_ROLES:
        return apply_standard_ui_filter(provider, models)

    provider = provider.lower()
    role = role.lower()
    working = apply_standard_ui_filter(provider, models)
    all_ids = [m.get("id") or m.get("name") or "" for m in models]

    patterns = resolve_allowlist_patterns(provider, role)
    if patterns:
        _log_unmatched_patterns(provider, role, patterns, all_ids)
        working = [
            m
            for m in working
            if model_matches_allowlist(
                patterns, (m.get("id") or m.get("name") or "")
            )
        ]

    result: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for m in working:
        mid = m.get("id") or m.get("name") or ""
        if not mid or mid in seen:
            continue
        seen.add(mid)
        enriched = dict(m)
        enriched["display_name"] = format_model_display_name(
            provider, mid, enriched.get("display_name") or mid
        )
        result.append(enriched)

    saved = (saved_model_id or "").strip()
    if saved and saved not in seen:
        legacy_label = format_model_display_name(provider, saved, saved)
        result.append(
            {
                "id": saved,
                "name": saved,
                "display_name": f"{legacy_label} (nicht mehr freigegeben)",
                "type": models[0].get("type") if models else "chat",
                "legacy_not_allowed": True,
            }
        )

    return result


def is_model_allowed_for_role(provider: str, role: str, model_id: str) -> bool:
    model_id = (model_id or "").strip()
    if not model_id:
        return False
    if role.lower() not in MODEL_ROLES:
        return True
    patterns = resolve_allowlist_patterns(provider, role.lower())
    if not patterns:
        return True
    return model_matches_allowlist(patterns, model_id)


def can_save_model_for_role(
    provider: str,
    role: str,
    model_id: str,
    previous_model_id: Optional[str] = None,
) -> bool:
    """Speichern erlauben: Allowlist oder unverändertes (legacy) Modell behalten."""
    model_id = (model_id or "").strip()
    prev = (previous_model_id or "").strip()
    if prev and model_id == prev:
        return True
    return is_model_allowed_for_role(provider, role, model_id)


def role_from_query(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    r = role.strip().lower()
    return r if r in MODEL_ROLES else None
