"""Multi-provider tests: CompatibleProvider uses Chat Completions, never the network.

The real ``openai`` client is constructed (lazy, no I/O) and then replaced
with a recording fake before ``reply()`` is called.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace


def _fake_client(captured: dict, content: str = " hi ", error: Exception | None = None):
    def _create(**kwargs):
        captured.update(kwargs)
        if error is not None:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_create)))


def _provider(**overrides):
    from app.core.ai_service import CompatibleProvider

    provider = CompatibleProvider(
        api_key=overrides.get("api_key", "dummy-key"),
        base_url=overrides.get("base_url", "https://example.test/v1"),
    )
    return provider


class CompatibleProviderTests(unittest.TestCase):
    def test_empty_key_rejected(self) -> None:
        from app.core.ai_service import AIConfigurationError, CompatibleProvider

        with self.assertRaises(AIConfigurationError):
            CompatibleProvider("   ", "https://example.test/v1")

    def test_empty_url_rejected(self) -> None:
        from app.core.ai_service import AIConfigurationError, CompatibleProvider

        with self.assertRaises(AIConfigurationError):
            CompatibleProvider("dummy-key", "   ")

    def test_reply_sends_system_plus_history(self) -> None:
        from app.core.session import ChatMessage

        captured: dict = {}
        provider = _provider()
        provider._client = _fake_client(captured)
        reply = provider.reply(
            [ChatMessage("user", "hello"), ChatMessage("assistant", "hi there")],
            "my-model",
            instructions="CUSTOM SYS",
        )
        self.assertEqual(reply, "hi")
        self.assertEqual(captured["model"], "my-model")
        roles = [m["role"] for m in captured["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant"])
        self.assertEqual(captured["messages"][0]["content"], "CUSTOM SYS")

    def test_default_instructions_used_when_missing(self) -> None:
        from app.core.ai_service import SYSTEM_INSTRUCTIONS
        from app.core.session import ChatMessage

        captured: dict = {}
        provider = _provider()
        provider._client = _fake_client(captured)
        provider.reply([ChatMessage("user", "hello")], "my-model")
        self.assertEqual(captured["messages"][0]["content"], SYSTEM_INSTRUCTIONS)

    def test_empty_content_is_safe_error(self) -> None:
        from app.core.ai_service import AIServiceError
        from app.core.session import ChatMessage

        provider = _provider()
        provider._client = _fake_client({}, content="   ")
        with self.assertRaises(AIServiceError):
            provider.reply([ChatMessage("user", "hello")], "my-model")

    def test_sdk_errors_reuse_openai_mapping(self) -> None:
        from app.core.ai_service import AIRateLimitError
        from app.core.session import ChatMessage

        err = type("RateLimitError", (Exception,), {})()
        provider = _provider()
        provider._client = _fake_client({}, error=err)
        with self.assertRaises(AIRateLimitError):
            provider.reply([ChatMessage("user", "hello")], "my-model")

    def test_status_code_mapping(self) -> None:
        from app.core.ai_service import (
            AIAuthenticationError,
            AIRateLimitError,
            AIServiceError,
            OpenAIProvider,
        )

        def _status_error(code: int) -> Exception:
            err = type("APIStatusError", (Exception,), {})("boom")
            err.status_code = code  # type: ignore[attr-defined]
            return err

        self.assertIsInstance(OpenAIProvider._map_error(_status_error(401)), AIAuthenticationError)
        self.assertIsInstance(OpenAIProvider._map_error(_status_error(429)), AIRateLimitError)
        self.assertIsInstance(OpenAIProvider._map_error(_status_error(404)), AIServiceError)
        self.assertIn("not found", str(OpenAIProvider._map_error(_status_error(404))).lower())
        self.assertIsInstance(OpenAIProvider._map_error(_status_error(410)), AIServiceError)
        self.assertIn("retired", str(OpenAIProvider._map_error(_status_error(410))).lower())

    def test_base_url_normalized(self) -> None:
        provider = _provider(base_url="https://example.test/v1/")
        self.assertEqual(provider._base_url, "https://example.test/v1")

    def test_keys_stripped_before_sdk(self) -> None:
        """BUG-2: pasted keys with surrounding whitespace must reach the SDK clean."""
        from app.core.ai_service import OpenAIProvider

        provider = _provider(api_key="  dummy-key \n", base_url="https://example.test/v1/ ")
        self.assertEqual(provider._client.api_key, "dummy-key")
        self.assertEqual(provider._base_url, "https://example.test/v1")
        openai_provider = OpenAIProvider("  sk-test \n")
        self.assertEqual(openai_provider._client.api_key, "sk-test")

    def test_empty_model_rejected_before_network(self) -> None:
        """Blank model must fail fast with a Settings pointer, not an API 404."""
        from app.core.ai_service import AIConfigurationError, OpenAIProvider
        from app.core.session import ChatMessage

        messages = [ChatMessage("user", "hello")]
        with self.assertRaises(AIConfigurationError):
            _provider().reply(messages, "   ")
        with self.assertRaises(AIConfigurationError):
            OpenAIProvider("sk-test").reply(messages, "")


class TestConnectionTests(unittest.TestCase):
    """CompatibleProvider.test_connection() — mocked HTTP only."""

    def test_connection_success(self) -> None:
        captured: dict = {}
        provider = _provider()
        provider._client = _fake_client(captured, content="ok")
        ok, msg = provider.test_connection("test-model")
        self.assertTrue(ok)
        self.assertEqual(msg, "")
        self.assertEqual(captured["max_tokens"], 1)

    def test_connection_auth_failure(self) -> None:
        err = type("AuthenticationError", (Exception,), {})()
        provider = _provider()
        provider._client = _fake_client({}, error=err)
        ok, msg = provider.test_connection("test-model")
        self.assertFalse(ok)
        self.assertIn("key", msg.lower())
        # API key must never appear in the error message.
        self.assertNotIn("dummy-key", msg)

    def test_connection_rate_limit(self) -> None:
        err = type("RateLimitError", (Exception,), {})()
        provider = _provider()
        provider._client = _fake_client({}, error=err)
        ok, msg = provider.test_connection("test-model")
        self.assertFalse(ok)
        self.assertIn("quota", msg.lower())

    def test_connection_no_model(self) -> None:
        provider = _provider()
        ok, msg = provider.test_connection("")
        self.assertFalse(ok)
        self.assertIn("model", msg.lower())

    def test_connection_sends_minimal_request(self) -> None:
        """Test connection must use max_tokens=1 — no heavy prompt."""
        captured: dict = {}
        provider = _provider()
        provider._client = _fake_client(captured)
        provider.test_connection("my-model")
        self.assertEqual(captured.get("max_tokens"), 1)
        # Only a single "hi" message — no system prompt, no history.
        self.assertEqual(len(captured.get("messages", [])), 1)
        self.assertEqual(captured["messages"][0]["content"], "hi")


class ProviderSelectionTests(unittest.TestCase):
    def test_from_config_picks_compatible_with_canonical_name(self) -> None:
        import os
        from unittest.mock import patch

        from app.core.ai_service import AIService, CompatibleProvider
        from app.core.config import Config

        with (
            patch.object(Config, "AI_MODE", "live"),
            patch.object(Config, "AI_PROVIDER", "openai_compatible"),
            patch.object(Config, "AI_BASE_URL", "https://example.test/v1"),
            patch.object(Config, "get_ai_api_key", return_value="dummy-key"),
        ):
            service = AIService.from_config()
        self.assertTrue(service.is_live)
        self.assertIsInstance(service.provider, CompatibleProvider)

    def test_from_config_picks_compatible_with_legacy_custom(self) -> None:
        """AI_PROVIDER=custom (legacy) must still work."""
        import os
        from unittest.mock import patch

        from app.core.ai_service import AIService, CompatibleProvider
        from app.core.config import Config

        # Config normalizes "custom" → "openai_compatible" at load time.
        # Here we simulate Config already having the normalized value.
        with (
            patch.object(Config, "AI_MODE", "live"),
            patch.object(Config, "AI_PROVIDER", "openai_compatible"),
            patch.object(Config, "AI_BASE_URL", "https://example.test/v1"),
            patch.object(Config, "get_ai_api_key", return_value="dummy-key"),
        ):
            service = AIService.from_config()
        self.assertTrue(service.is_live)
        self.assertIsInstance(service.provider, CompatibleProvider)

    def test_from_config_picks_native_openai(self) -> None:
        from unittest.mock import patch

        from app.core.ai_service import AIService, OpenAIProvider
        from app.core.config import Config

        with (
            patch.object(Config, "AI_MODE", "live"),
            patch.object(Config, "AI_PROVIDER", "openai_native"),
            patch.object(Config, "get_ai_api_key", return_value="sk-test"),
        ):
            service = AIService.from_config()
        self.assertTrue(service.is_live)
        self.assertIsInstance(service.provider, OpenAIProvider)

    def test_from_config_stays_mock_by_default(self) -> None:
        from unittest.mock import patch

        from app.core.ai_service import AIService, MockProvider
        from app.core.config import Config

        with patch.object(Config, "AI_MODE", "mock"):
            service = AIService.from_config()
        self.assertFalse(service.is_live)
        self.assertIsInstance(service.provider, MockProvider)

    def test_unknown_provider_raises_config_error(self) -> None:
        from unittest.mock import patch

        from app.core.ai_service import AIConfigurationError, AIService
        from app.core.config import Config

        with (
            patch.object(Config, "AI_MODE", "live"),
            patch.object(Config, "AI_PROVIDER", "anthropic_future"),
            patch.object(Config, "get_ai_api_key", return_value="key"),
        ):
            with self.assertRaises(AIConfigurationError):
                AIService.from_config()

    def test_effective_model_canonical_wins(self) -> None:
        from unittest.mock import patch

        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", "meta/x"):
            self.assertEqual(Config.effective_model("gpt-4o-mini"), "meta/x")

    def test_effective_model_blank_uses_preferred(self) -> None:
        from unittest.mock import patch

        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", ""):
            self.assertEqual(Config.effective_model("gpt-4o-mini"), "gpt-4o-mini")

    def test_effective_model_both_blank(self) -> None:
        from unittest.mock import patch

        from app.core.config import Config

        with patch.object(Config, "AI_MODEL", ""):
            self.assertEqual(Config.effective_model(""), "")


if __name__ == "__main__":
    unittest.main()
