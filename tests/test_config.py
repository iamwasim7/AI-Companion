"""Configuration tests: env-var reading, normalization, and backward compat.

No network calls, no paid APIs.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class ConfigBasicsTests(unittest.TestCase):
    def test_app_name(self) -> None:
        from app.core.config import Config

        self.assertEqual(Config.APP_NAME, "AI Companion")

    def test_ai_mode_is_known(self) -> None:
        from app.core.config import Config

        self.assertIn(Config.AI_MODE, {"mock", "live"})

    def test_version_updated(self) -> None:
        from app.core.config import Config

        # v1.3.0 introduced provider abstraction.
        self.assertEqual(Config.APP_VERSION, "1.3.0")


class ProviderNormalizationTests(unittest.TestCase):
    """Legacy AI_PROVIDER values must normalize to canonical names."""

    def test_custom_normalizes_to_openai_compatible(self) -> None:
        from app.core.config import _normalize_provider

        self.assertEqual(_normalize_provider("custom"), "openai_compatible")

    def test_openai_normalizes_to_openai_native(self) -> None:
        from app.core.config import _normalize_provider

        self.assertEqual(_normalize_provider("openai"), "openai_native")

    def test_openai_compatible_unchanged(self) -> None:
        from app.core.config import _normalize_provider

        self.assertEqual(_normalize_provider("openai_compatible"), "openai_compatible")

    def test_openai_native_unchanged(self) -> None:
        from app.core.config import _normalize_provider

        self.assertEqual(_normalize_provider("openai_native"), "openai_native")

    def test_case_insensitive(self) -> None:
        from app.core.config import _normalize_provider

        self.assertEqual(_normalize_provider("CUSTOM"), "openai_compatible")
        self.assertEqual(_normalize_provider("OpenAI"), "openai_native")


class LegacyEnvFallbackTests(unittest.TestCase):
    """Canonical AI_* names take priority; CUSTOM_* are the fallback."""

    def test_canonical_ai_api_key_wins_over_custom(self) -> None:
        from app.core.config import _read_ai_env

        with patch.dict(os.environ, {"AI_API_KEY": "canon-key", "CUSTOM_API_KEY": "old-key"}):
            result = _read_ai_env("AI_API_KEY", "CUSTOM_API_KEY")
        self.assertEqual(result, "canon-key")

    def test_custom_api_key_fallback_when_no_canonical(self) -> None:
        from app.core.config import _read_ai_env

        env = {"CUSTOM_API_KEY": "old-key"}
        with patch.dict(os.environ, env, clear=False):
            # Ensure AI_API_KEY is absent.
            os.environ.pop("AI_API_KEY", None)
            result = _read_ai_env("AI_API_KEY", "CUSTOM_API_KEY")
        self.assertEqual(result, "old-key")

    def test_ai_base_url_fallback_to_custom_base_url(self) -> None:
        from app.core.config import _read_ai_env

        env = {"CUSTOM_BASE_URL": "https://legacy.example.com/v1"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("AI_BASE_URL", None)
            result = _read_ai_env("AI_BASE_URL", "CUSTOM_BASE_URL")
        self.assertEqual(result, "https://legacy.example.com/v1")

    def test_ai_model_fallback_to_custom_model(self) -> None:
        from app.core.config import _read_ai_env

        env = {"CUSTOM_MODEL": "meta/llama-3.2-11b-vision-instruct"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("AI_MODEL", None)
            result = _read_ai_env("AI_MODEL", "CUSTOM_MODEL")
        self.assertEqual(result, "meta/llama-3.2-11b-vision-instruct")

    def test_default_returned_when_nothing_set(self) -> None:
        from app.core.config import _read_ai_env

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_API_KEY", None)
            os.environ.pop("CUSTOM_API_KEY", None)
            result = _read_ai_env("AI_API_KEY", "CUSTOM_API_KEY", default="fallback")
        self.assertEqual(result, "fallback")


class EffectiveModelTests(unittest.TestCase):
    def test_canonical_model_takes_priority(self) -> None:
        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", "meta/x"):
            self.assertEqual(Config.effective_model("gpt-4o-mini"), "meta/x")

    def test_preferred_used_when_ai_model_blank(self) -> None:
        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", ""):
            self.assertEqual(Config.effective_model("gpt-4o-mini"), "gpt-4o-mini")

    def test_empty_string_when_both_blank(self) -> None:
        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", ""):
            self.assertEqual(Config.effective_model(""), "")


class MockModeTests(unittest.TestCase):
    def test_mock_mode_does_not_require_api_key(self) -> None:
        from app.core.config import Config

        with patch.object(Config, "AI_MODE", "mock"):
            self.assertTrue(Config.is_mock_mode())

    def test_live_mode_detected(self) -> None:
        from app.core.config import Config

        with patch.object(Config, "AI_MODE", "live"):
            self.assertFalse(Config.is_mock_mode())


if __name__ == "__main__":
    unittest.main()
