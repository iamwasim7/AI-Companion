"""Error analysis service: sends detected context to the AI and parses the result.

Architecture
------------
* ``ErrorAnalysisService`` wraps the existing ``AIService`` and uses structured
  prompts from ``app.ai.prompts`` to request JSON-schema responses.
* ``ErrorAnalysisWorker`` is a ``QThread`` that calls the service off the UI
  thread, then emits ``succeeded(ErrorAnalysis)`` or ``failed(str)``.
* ``get_error_analysis_service()`` returns a process-level singleton so that
  repeated analyses do not recreate the service on every keystroke.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.ai.prompts import SYSTEM_PROMPT, build_analysis_prompt
from app.ai.response_parser import ErrorAnalysis, parse_error_analysis
from app.core.ai_service import AIService, AIServiceError
from app.core.config import Config
from app.core.logger import get_logger
from app.core.session import ChatMessage
from app.core.state import app_state
from app.detection.context_detector import ContextDetector
from app.detection.models import DetectedError

logger = get_logger("ai.error_analysis")


# ── Service ───────────────────────────────────────────────────────────────────

class ErrorAnalysisService:
    """Request structured AI error analysis for a ``DetectedError`` object.

    Uses a one-shot prompt pattern (no multi-turn history) with the structured
    JSON system prompt so the response is always machine-parseable.
    """

    def __init__(self, ai_service: AIService) -> None:
        self._service = ai_service
        self._context_detector = ContextDetector()

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse(self, detected: DetectedError) -> ErrorAnalysis:
        """Run synchronous analysis.  Call only from a non-UI thread."""
        # Privacy-safe diagnostics: presence/length only, never content.
        logger.info(
            "Analysis context: has_code=%s code_chars=%d lang=%s error=%s",
            bool(detected.relevant_code),
            len(detected.relevant_code or ""),
            detected.language,
            detected.error_type or "-",
        )
        context_str = ContextDetector.format_ai_context(detected)
        user_message = build_analysis_prompt(detected, context_str)

        # Build a one-shot conversation: system instruction + user message.
        # We wrap them as ChatMessage so the existing AIService interface works.
        messages: list[ChatMessage] = [
            ChatMessage(role="user", text=user_message),
        ]

        try:
            try:
                raw = self._service.provider.reply(messages, Config.effective_model(app_state.ai_model), SYSTEM_PROMPT)  # type: ignore[call-arg]
            except TypeError:
                raw = self._service.provider.reply(messages, Config.effective_model(app_state.ai_model))  # type: ignore[misc]
        except AIServiceError as exc:
            logger.warning("Error analysis AI call failed: %s", exc)
            return ErrorAnalysis.unavailable(str(exc))
        except Exception as exc:
            logger.exception("Unexpected error in error analysis: %s", type(exc).__name__)
            return ErrorAnalysis.unavailable("Unexpected failure during analysis.")

        result = parse_error_analysis(raw)
        logger.info(
            "Error analysis complete: type=%s confidence=%.2f fallback=%s",
            result.error_type,
            result.confidence,
            result.is_fallback,
        )
        return result

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls) -> "ErrorAnalysisService":
        """Construct using the same provider logic as ``AIService.from_config()``."""
        ai_service = AIService.from_config()
        return cls(ai_service)


# ── Qt worker ─────────────────────────────────────────────────────────────────

class ErrorAnalysisWorker(QThread):
    """Off-thread wrapper around ``ErrorAnalysisService.analyse()``."""

    succeeded = Signal(object)   # emits ErrorAnalysis
    failed = Signal(str)

    def __init__(self, service: ErrorAnalysisService, detected: DetectedError) -> None:
        super().__init__()
        self._service = service
        self._detected = detected

    def run(self) -> None:
        try:
            result = self._service.analyse(self._detected)
        except Exception as exc:
            logger.exception("ErrorAnalysisWorker crashed: %s", type(exc).__name__)
            self.failed.emit("Error analysis could not be completed.")
            return
        self.succeeded.emit(result)


# ── Singleton ─────────────────────────────────────────────────────────────────

_service: ErrorAnalysisService | None = None


def get_error_analysis_service() -> ErrorAnalysisService:
    """Return (or create) the process-level singleton ``ErrorAnalysisService``."""
    global _service
    if _service is None:
        _service = ErrorAnalysisService.from_config()
    return _service


def reset_error_analysis_service() -> None:
    """Force recreation of the singleton (used after settings changes)."""
    global _service
    _service = None
