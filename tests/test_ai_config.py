"""AI configuration and security tests.

Verifies that:
- Missing config values produce clean, user-facing errors.
- API keys never appear in logged exception strings.
- Mock mode stays fully offline (no provider instantiation).
- Configuration validation is provider-specific.

No real API key or network connection is used.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class MissingConfigTests(unittest.TestCase):
    """Missing required values → clean AIConfigurationError, not raw exceptions."""

    def test_compatible_provider_no_key_raises_config_error(self) -> None:
        from app.core.ai_service import AIConfigurationError, CompatibleProvider

        with self.assertRaises(AIConfigurationError) as ctx:
            CompatibleProvider("", "https://example.test/v1")
        # Message must be user-friendly — no raw traceback text.
        self.assertIn("key", str(ctx.exception).lower())

    def test_compatible_provider_no_url_raises_config_error(self) -> None:
        from app.core.ai_service import AIConfigurationError, CompatibleProvider

        with self.assertRaises(AIConfigurationError) as ctx:
            CompatibleProvider("dummy-key", "")
        self.assertIn("url", str(ctx.exception).lower())

    def test_native_provider_no_key_raises_config_error(self) -> None:
        from app.core.ai_service import AIConfigurationError, OpenAIProvider

        with self.assertRaises(AIConfigurationError) as ctx:
            OpenAIProvider("")
        self.assertIn("key", str(ctx.exception).lower())

    def test_from_config_live_no_key_raises_config_error(self) -> None:
        from app.core.ai_service import AIConfigurationError, AIService
        from app.core.config import Config

        with (
            patch.object(Config, "AI_MODE", "live"),
            patch.object(Config, "AI_PROVIDER", "openai_compatible"),
            patch.object(Config, "AI_BASE_URL", "https://example.test/v1"),
            patch.object(Config, "get_ai_api_key", return_value=""),
        ):
            with self.assertRaises(AIConfigurationError):
                AIService.from_config()

    def test_from_config_live_no_url_raises_config_error(self) -> None:
        from app.core.ai_service import AIConfigurationError, AIService
        from app.core.config import Config

        with (
            patch.object(Config, "AI_MODE", "live"),
            patch.object(Config, "AI_PROVIDER", "openai_compatible"),
            patch.object(Config, "AI_BASE_URL", ""),
            patch.object(Config, "get_ai_api_key", return_value="dummy-key"),
        ):
            with self.assertRaises(AIConfigurationError):
                AIService.from_config()

    def test_blank_model_does_not_crash_config(self) -> None:
        """Blank model is valid config — the provider will surface the error."""
        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", ""):
            result = Config.effective_model("")
        self.assertEqual(result, "")


class MockModeOfflineTests(unittest.TestCase):
    """Mock mode must never instantiate a real provider."""

    def test_mock_mode_creates_mock_provider(self) -> None:
        from app.core.ai_service import AIService, MockProvider
        from app.core.config import Config

        with patch.object(Config, "AI_MODE", "mock"):
            service = AIService.from_config()
        self.assertIsInstance(service.provider, MockProvider)
        self.assertFalse(service.is_live)

    def test_mock_provider_needs_no_key_or_url(self) -> None:
        """Mock works even if no API key or base URL is configured."""
        from app.core.ai_service import AIService, MockProvider
        from app.core.config import Config

        with (
            patch.object(Config, "AI_MODE", "mock"),
            patch.object(Config, "AI_API_KEY_SET", False),
            patch.object(Config, "AI_BASE_URL", ""),
        ):
            service = AIService.from_config()
        self.assertIsInstance(service.provider, MockProvider)

    def test_mock_provider_returns_text_without_network(self) -> None:
        from app.core.ai_service import MockProvider
        from app.core.session import ChatMessage

        provider = MockProvider()
        reply = provider.reply([ChatMessage("user", "Explain a NameError")], "unused-model")
        self.assertTrue(len(reply) > 0)


class ApiKeySecurityTests(unittest.TestCase):
    """API keys must never appear in error messages or exception strings."""

    _SECRET_KEY = "sk-secret-key-that-must-not-leak"

    def test_auth_error_does_not_contain_key(self) -> None:
        from app.core.ai_service import OpenAIProvider

        auth_err = type("AuthenticationError", (Exception,), {})()
        mapped = OpenAIProvider._map_error(auth_err)
        self.assertNotIn(self._SECRET_KEY, str(mapped))

    def test_rate_limit_error_does_not_contain_key(self) -> None:
        from app.core.ai_service import OpenAIProvider

        rate_err = type("RateLimitError", (Exception,), {})()
        mapped = OpenAIProvider._map_error(rate_err)
        self.assertNotIn(self._SECRET_KEY, str(mapped))

    def test_timeout_error_does_not_contain_key(self) -> None:
        from app.core.ai_service import OpenAIProvider

        timeout_err = type("APITimeoutError", (Exception,), {})()
        mapped = OpenAIProvider._map_error(timeout_err)
        self.assertNotIn(self._SECRET_KEY, str(mapped))

    def test_connection_error_does_not_contain_key(self) -> None:
        from app.core.ai_service import OpenAIProvider

        conn_err = type("APIConnectionError", (Exception,), {})()
        mapped = OpenAIProvider._map_error(conn_err)
        self.assertNotIn(self._SECRET_KEY, str(mapped))

    def test_generic_error_does_not_contain_key(self) -> None:
        from app.core.ai_service import OpenAIProvider

        generic = Exception(f"Request failed with key={self._SECRET_KEY}")
        mapped = OpenAIProvider._map_error(generic)
        self.assertNotIn(self._SECRET_KEY, str(mapped))

    def test_test_connection_auth_failure_hides_key(self) -> None:
        from types import SimpleNamespace

        from app.core.ai_service import CompatibleProvider

        auth_err = type("AuthenticationError", (Exception,), {})()
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_: (_ for _ in ()).throw(auth_err)
                )
            )
        )
        provider = CompatibleProvider(self._SECRET_KEY, "https://example.test/v1")
        provider._client = fake_client
        ok, msg = provider.test_connection("some-model")
        self.assertFalse(ok)
        self.assertNotIn(self._SECRET_KEY, msg)

    def test_get_ai_api_key_reads_canonical_first(self) -> None:
        """get_ai_api_key() reads AI_API_KEY before CUSTOM_API_KEY."""
        from app.core.config import Config

        with patch.dict(os.environ, {"AI_API_KEY": "canon-key", "CUSTOM_API_KEY": "legacy-key"}):
            # Neutralize the real .env reload: refresh() uses override=True,
            # which would otherwise clobber the patched values with ambient
            # secrets (and leak them into failures). Class attrs still refresh
            # from the patched environment.
            with patch("app.core.config.load_dotenv"):
                Config.refresh()
                key = Config.get_ai_api_key()
        # Restore state.
        Config.refresh()
        self.assertEqual(key, "canon-key")


class ProviderErrorNormalizationTests(unittest.TestCase):
    """All provider errors should map to user-friendly AIServiceError subclasses."""

    def _make_err(self, name: str, status: int | None = None) -> Exception:
        attrs = {}
        if status is not None:
            attrs["status_code"] = status
        return type(name, (Exception,), attrs)()

    def test_401_maps_to_authentication_error(self) -> None:
        from app.core.ai_service import AIAuthenticationError, OpenAIProvider

        mapped = OpenAIProvider._map_error(self._make_err("SomeErr", status=401))
        self.assertIsInstance(mapped, AIAuthenticationError)

    def test_429_maps_to_rate_limit_error(self) -> None:
        from app.core.ai_service import AIRateLimitError, OpenAIProvider

        mapped = OpenAIProvider._map_error(self._make_err("SomeErr", status=429))
        self.assertIsInstance(mapped, AIRateLimitError)

    def test_404_maps_to_safe_service_error(self) -> None:
        from app.core.ai_service import AIServiceError, OpenAIProvider

        mapped = OpenAIProvider._map_error(self._make_err("SomeErr", status=404))
        self.assertIsInstance(mapped, AIServiceError)
        self.assertIn("not found", str(mapped).lower())

    def test_timeout_name_maps_to_timeout_error(self) -> None:
        from app.core.ai_service import AITimeoutError, OpenAIProvider

        mapped = OpenAIProvider._map_error(self._make_err("APITimeoutError"))
        self.assertIsInstance(mapped, AITimeoutError)

    def test_connection_name_maps_to_connection_error(self) -> None:
        from app.core.ai_service import AIConnectionError, OpenAIProvider

        mapped = OpenAIProvider._map_error(self._make_err("APIConnectionError"))
        self.assertIsInstance(mapped, AIConnectionError)


if __name__ == "__main__":
    unittest.main()
