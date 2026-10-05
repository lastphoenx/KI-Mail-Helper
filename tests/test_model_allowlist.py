"""Tests für Modell-Allowlist (synthetisch, ohne Netzwerk)."""

import os
import unittest
from unittest.mock import patch

from src.services.model_allowlist import (
    can_save_model_for_role,
    filter_models_for_role,
    is_model_allowed_for_role,
    model_matches_allowlist,
    parse_env_allowlist,
    resolve_allowlist_patterns,
)


def _chat(*ids: str):
    return [{"id": i, "name": i, "type": "chat", "display_name": i} for i in ids]


class TestModelAllowlist(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_env_empty_means_no_env_layer(self):
        os.environ.pop("AI_MODELS_OPENAI_BASE", None)
        self.assertIsNone(parse_env_allowlist("openai", "base"))

    def test_glob_matching(self):
        patterns = ["gpt-4o*"]
        self.assertTrue(model_matches_allowlist(patterns, "gpt-4o-mini"))
        self.assertFalse(model_matches_allowlist(patterns, "gpt-4.1"))

    @patch.dict(os.environ, {"AI_MODELS_OPENAI_BASE": "gpt-4o-mini,gpt-4.1-mini"}, clear=False)
    def test_env_overrides_registry(self):
        patterns = resolve_allowlist_patterns("openai", "base")
        self.assertEqual(patterns, ["gpt-4o-mini", "gpt-4.1-mini"])

    @patch.dict(os.environ, {"AI_MODELS_UI_FILTER": "false"}, clear=False)
    def test_filter_respects_env_allowlist(self):
        models = _chat("gpt-4o-mini", "gpt-4.1", "gpt-4o-mini-2024-07-18")
        with patch.dict(
            os.environ,
            {"AI_MODELS_OPENAI_BASE": "gpt-4o-mini,gpt-4.1"},
            clear=False,
        ):
            out = filter_models_for_role("openai", "base", models)
        ids = [m["id"] for m in out]
        self.assertEqual(ids, ["gpt-4o-mini", "gpt-4.1"])

    def test_disallowed_save(self):
        with patch(
            "src.services.model_allowlist.resolve_allowlist_patterns",
            return_value=["gpt-4o-mini"],
        ):
            self.assertFalse(is_model_allowed_for_role("openai", "base", "gpt-4.1"))
            self.assertTrue(is_model_allowed_for_role("openai", "base", "gpt-4o-mini"))

    def test_keep_legacy_model_on_save(self):
        with patch(
            "src.services.model_allowlist.resolve_allowlist_patterns",
            return_value=["gpt-4o-mini"],
        ):
            self.assertTrue(
                can_save_model_for_role(
                    "openai", "base", "gpt-legacy-id", previous_model_id="gpt-legacy-id"
                )
            )
            self.assertFalse(
                can_save_model_for_role("openai", "base", "gpt-legacy-id", previous_model_id="")
            )

    @patch.dict(os.environ, {"AI_MODELS_UI_FILTER": "false"}, clear=False)
    def test_saved_not_in_list_gets_legacy_hint(self):
        models = _chat("gpt-4o-mini")
        with patch(
            "src.services.model_allowlist.resolve_allowlist_patterns",
            return_value=["gpt-4o-mini"],
        ):
            out = filter_models_for_role(
                "openai", "base", models, saved_model_id="gpt-old-snapshot"
            )
        legacy = [m for m in out if m.get("legacy_not_allowed")]
        self.assertEqual(len(legacy), 1)
        self.assertIn("nicht mehr freigegeben", legacy[0]["display_name"])


if __name__ == "__main__":
    unittest.main()
