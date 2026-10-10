"""AI provider boundary: deterministic mock by default, configurable live providers.

Provider selection (AI_PROVIDER env var):
    openai_compatible — OpenAI-compatible Chat Completions endpoint
                        (NVIDIA NIM, Groq, Together, Ollama, OpenRouter, ...)
    openai_native     — Native OpenAI Responses API (api.openai.com)

Legacy values are transparently mapped by Config:
    "custom"  → openai_compatible
    "openai"  → openai_native
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.core.config import Config
from app.core.mock_ai import MockAIError, generate_error_analysis, generate_reply
from app.core.session import ChatMessage

SYSTEM_INSTRUCTIONS = """You are AI Companion, a helpful programming assistant.
Explain programming errors clearly. State the likely cause,
then give a small, safe fix with a code example when helpful. Be concise and never
claim to have inspected the user's screen or files unless they explicitly provide text.
Never mention education, degrees, courses, or personal details about the user.
If asked who you are, say you are AI Companion, a programming assistant."""


class AIServiceError(Exception):
    """Safe, user-facing error from the selected AI provider."""


class AIConfigurationError(AIServiceError):
    pass


class AIAuthenticationError(AIServiceError):
    pass


class AIRateLimitError(AIServiceError):
    pass


class AITimeoutError(AIServiceError):
    pass


class AIConnectionError(AIServiceError):
    pass


class AIProvider(Protocol):
    def reply(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        instructions: str | None = None,
    ) -> str: ...


class MockProvider:
    def reply(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        instructions: str | None = None,
    ) -> str:
        del model
        del instructions
        latest = next((message.text for message in reversed(messages) if message.role == "user"), "")
        # Structured error-analysis requests contain the JSON schema trigger phrase
        if "JSON schema" in latest or "json schema" in latest:
            # Extract error_type hint from the message if possible
            import re
            match = re.search(
                r"(NameError|TypeError|SyntaxError|IndexError|ValueError|AttributeError|ReferenceError|RangeError|URIError)",
                latest,
            )
            error_type = match.group(1) if match else "General"
            lang_match = re.search(r"Language:\s*([A-Za-z]+)", latest)
            language = lang_match.group(1) if lang_match else ("JavaScript" if ".js" in latest.lower() or "node:" in latest.lower() else "General")
            return generate_error_analysis(error_type, language=language)
        try:
            return generate_reply(latest)
        except MockAIError as exc:
            raise AIServiceError(str(exc)) from exc


class OpenAIProvider:
    """Synchronous service called from the dedicated UI worker thread.

    Uses the native OpenAI Responses API (``/responses``).
    Set AI_PROVIDER=openai_native to activate this provider.
    """

    def __init__(self, api_key: str, timeout_seconds: float = Config.OPENAI_TIMEOUT_SECONDS) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise AIConfigurationError("Add an AI API key in Settings before using live AI.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigurationError("The OpenAI package is not installed. Run `pip install -r requirements.txt`.") from exc
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=Config.OPENAI_MAX_RETRIES)

    def reply(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        instructions: str | None = None,
    ) -> str:
        if not model.strip():
            raise AIConfigurationError("No model configured. Enter a model name in Settings first.")
        try:
            response = self._client.responses.create(
                model=model,
                instructions=instructions or SYSTEM_INSTRUCTIONS,
                input=[{"role": item.role, "content": item.text} for item in messages if item.role in {"user", "assistant"}],
                max_output_tokens=700,
                store=False,
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        text = getattr(response, "output_text", "")
        if not text or not text.strip():
            raise AIServiceError("The AI returned no text. Please try again.")
        return text.strip()

    @staticmethod
    def _map_error(error: Exception) -> AIServiceError:
        name = type(error).__name__
        status = getattr(error, "status_code", None)
        if name == "AuthenticationError" or status == 401:
            return AIAuthenticationError("The API key was rejected. Check it in Settings and try again.")
        if name == "RateLimitError" or status == 429:
            return AIRateLimitError("The AI service is busy or your quota is exhausted. Please try again later.")
        if name == "APITimeoutError":
            return AITimeoutError("The AI request took too long. Please try again.")
        if name in {"APIConnectionError", "APIConnectionTimeoutError"}:
            return AIConnectionError("Could not reach the AI service. Check your internet connection and try again.")
        if status == 404:
            return AIServiceError("The selected model was not found on this endpoint. Check the model name in Settings.")
        if status == 410:
            return AIServiceError("The selected model has been retired by the provider. Pick a current model in Settings.")
        return AIServiceError("The AI request could not be completed. Please try again.")


class CompatibleProvider(OpenAIProvider):
    """OpenAI-compatible endpoint (NVIDIA NIM, Groq, Together, Ollama, ...).

    Uses Chat Completions instead of the Responses API because third-party
    OpenAI-compatible gateways implement ``/chat/completions`` but not
    ``/responses``. Structured ``instructions`` become the ``system`` message,
    so error-analysis prompts keep working unchanged.

    Set AI_PROVIDER=openai_compatible to activate this provider.
    """

    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = Config.OPENAI_TIMEOUT_SECONDS) -> None:
        api_key = api_key.strip()
        base_url = base_url.strip().rstrip("/")
        if not api_key:
            raise AIConfigurationError("Add an AI API key in Settings before using a custom endpoint.")
        if not base_url:
            raise AIConfigurationError("Set the Base URL in Settings before using an OpenAI-compatible endpoint.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigurationError("The OpenAI package is not installed. Run `pip install -r requirements.txt`.") from exc
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=Config.OPENAI_MAX_RETRIES,
        )
        self._base_url = base_url

    def reply(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        instructions: str | None = None,
    ) -> str:
        if not model.strip():
            raise AIConfigurationError("No model configured. Enter a model name in Settings first.")
        chat_messages = [{"role": "system", "content": instructions or SYSTEM_INSTRUCTIONS}]
        chat_messages += [
            {"role": item.role, "content": item.text}
            for item in messages
            if item.role in {"user", "assistant"}
        ]
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=chat_messages,
                max_tokens=700,
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        try:
            text = response.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError):
            text = ""
        if not text.strip():
            raise AIServiceError("The AI returned no text. Please try again.")
        return text.strip()

    def test_connection(self, model: str) -> tuple[bool, str]:
        """Send a minimal 1-token request and return (success, error_message).

        Designed to be called from a non-UI thread.
        The error message never contains the API key.
        """
        if not model:
            return False, "No model configured. Enter a model name in Settings first."
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            # Any valid response object counts as success.
            _ = response.choices[0].message.content
            return True, ""
        except Exception as exc:
            mapped = self._map_error(exc)
            return False, str(mapped)


@dataclass
class AIService:
    provider: AIProvider
    is_live: bool

    @classmethod
    def from_config(cls) -> "AIService":
        if Config.is_mock_mode():
            return cls(provider=MockProvider(), is_live=False)

        provider_type = Config.AI_PROVIDER
        api_key = Config.get_ai_api_key()

        if provider_type == "openai_compatible":
            return cls(
                provider=CompatibleProvider(api_key, Config.AI_BASE_URL),
                is_live=True,
            )
        if provider_type == "openai_native":
            return cls(provider=OpenAIProvider(api_key), is_live=True)

        raise AIConfigurationError(
            f"Unknown AI provider '{provider_type}'. "
            "Set AI_PROVIDER to 'openai_compatible' or 'openai_native' in Settings."
        )

    def reply(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        instructions: str | None = None,
    ) -> str:
        windowed = messages[-Config.AI_CONTEXT_MESSAGES :]
        try:
            return self.provider.reply(windowed, model, instructions)  # type: ignore[call-arg]
        except TypeError:
            # Backwards compatibility with 2-arg test doubles.
            return self.provider.reply(windowed, model)  # type: ignore[misc]
