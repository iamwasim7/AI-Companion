"""Context detection coordinator preparing concise inputs for AI analysis."""

from __future__ import annotations

from app.detection.error_detector import ErrorDetector, get_error_detector
from app.detection.models import DetectedError, DetectionCategory


def _has_readable_content(line: str) -> bool:
    """True when a line carries readable content (3+ alphanumeric chars).

    Drops symbol-only OCR junk such as stray caret runs, copyright marks,
    or rule lines. Letter-garbage from misread words passes by design --
    catching that needs a dictionary, deliberately out of scope here.
    """
    return sum(1 for ch in line if ch.isalnum()) >= 3


class ContextDetector:
    """Orchestrates detection and structures output for AI prompt preparation."""

    def __init__(self, detector: ErrorDetector | None = None) -> None:
        self._detector = detector or get_error_detector()

    def process_text(self, text: str) -> DetectedError:
        """Detect errors and format context from raw text."""
        return self._detector.detect(text)

    @staticmethod
    def nearby_error_lines(detected: DetectedError) -> list[str]:
        """Raw OCR lines around the error line, shared with the Ask-AI
        handoff. Used only when no clean ``relevant_code`` was extracted.
        Marked unverified so the model treats them as hints, not facts.
        Capped for cost discipline. Symbol-only junk lines (stray carets,
        copyright marks, rule lines) are dropped; letter-garbage from
        misread words cannot be caught cheaply and is left to the
        unverified-label hedging."""
        text_lines = [line for line in detected.raw_context.splitlines() if line.strip()]
        if not text_lines:
            return []
        anchor = -1
        if detected.error_type:
            lowered_type = detected.error_type.lower()
            for index, line in enumerate(text_lines):
                if lowered_type in line.lower():
                    anchor = index
                    break
        if anchor < 0:
            for index, line in enumerate(text_lines):
                if "error" in line.lower():
                    anchor = index
                    break
        if anchor < 0:
            anchor = 0
        window = text_lines[max(0, anchor - 3):anchor + 4]
        window = [line[:200] for line in window if _has_readable_content(line)]
        joined = "\n".join(window)
        return joined[:800].splitlines()

    @staticmethod
    def format_ai_context(detected: DetectedError) -> str:
        """Prepare a concise, structured context string for OpenAI error analysis."""
        lines: list[str] = []
        if detected.source_application != "Unknown":
            lines.append(f"Application: {detected.source_application}")
        if detected.language:
            lines.append(f"Language: {detected.language}")
        if detected.file_path:
            lines.append(f"File: {detected.file_path}")
        if detected.line_number is not None:
            lines.append(f"Line: {detected.line_number}")
        if detected.error_type:
            err_line = detected.error_type
            if detected.error_message:
                err_line += f": {detected.error_message}"
            lines.append(f"Error: {err_line}")
        if detected.relevant_code:
            lines.append(f"Relevant Code: {detected.relevant_code}")
        elif (detected.has_error or detected.error_type) and detected.raw_context.strip():
            # No clean code line was extracted (e.g. OCR garbled it) -- fall
            # back to raw lines around the error so the AI still sees
            # something instead of nothing. Explicitly unverified.
            nearby = ContextDetector.nearby_error_lines(detected)
            if nearby:
                lines.append("Nearby Screen Text (unverified OCR — hints only):")
                lines.extend(nearby)

        if not lines and detected.raw_context:
            return detected.raw_context[:500]

        return "\n".join(lines)


_context_detector: ContextDetector | None = None


def get_context_detector() -> ContextDetector:
    global _context_detector
    if _context_detector is None:
        _context_detector = ContextDetector()
    return _context_detector
