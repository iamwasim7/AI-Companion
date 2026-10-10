"""Provider-boundary tests: no network and no API key required."""

from __future__ import annotations

import unittest

from app.core.ai_service import AIService, AIServiceError, MockProvider, OpenAIProvider
from app.core.session import ChatMessage


class AIServiceTests(unittest.TestCase):
    def test_mock_provider_returns_reply(self) -> None:
        reply = MockProvider().reply([ChatMessage("user", "Explain a NameError")], "unused")
        self.assertIn("Cause", reply)

    def test_mock_failure_is_safe_error(self) -> None:
        with self.assertRaises(AIServiceError):
            MockProvider().reply([ChatMessage("user", "fail")], "unused")

    def test_context_is_bounded(self) -> None:
        class RecordingProvider:
            def __init__(self) -> None:
                self.messages: list[ChatMessage] = []

            def reply(self, messages: list[ChatMessage], model: str) -> str:
                self.messages = list(messages)
                return model

        provider = RecordingProvider()
        service = AIService(provider=provider, is_live=False)
        messages = [ChatMessage("user", str(index)) for index in range(30)]
        self.assertEqual(service.reply(messages, "model"), "model")
        self.assertLessEqual(len(provider.messages), 12)

    def test_sdk_errors_map_to_safe_text(self) -> None:
        error = type("RateLimitError", (Exception,), {})()
        mapped = OpenAIProvider._map_error(error)
        self.assertIn("quota", str(mapped).lower())


class PersonaTests(unittest.TestCase):
    def test_prompts_mention_no_degree_course_or_personal_details(self) -> None:
        # Regression: chat answered "Who are you?" with
        # "programming tutor ... BSc.IT journey". Personas must stay
        # generic with an explicit no-personal-details rule.
        from app.ai.prompts import SYSTEM_PROMPT
        from app.core.ai_service import SYSTEM_INSTRUCTIONS

        guardrail = "never mention education, degrees, courses, or personal details about the user."
        for prompt in (SYSTEM_INSTRUCTIONS, SYSTEM_PROMPT):
            lowered = prompt.lower()
            self.assertIn(guardrail, lowered)
            self.assertIn("programming assistant", lowered)
            # Strip the guardrail itself before scanning for identity
            # claims, otherwise "degrees"/"courses" in the rule trip us.
            body = lowered.replace(guardrail, "")
            for banned in ("bsc", "tutor", "journey", "degree", "course", "student"):
                self.assertNotIn(banned, body, f"banned word {banned!r} in persona")


if __name__ == "__main__":
    unittest.main()