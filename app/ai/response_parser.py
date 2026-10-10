"""Parse the structured JSON response from the AI into an ErrorAnalysis dataclass.

Handles three real-world failure modes gracefully:
  1. Model wraps JSON in a markdown code fence  → strip fences first
  2. Model returns a partial / malformed JSON   → fill missing fields with defaults
  3. Model returns plain text instead of JSON   → wrap the text in ErrorAnalysis.from_plain_text()
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ErrorAnalysis:
    """Structured AI analysis of a detected error or screen context."""

    problem: str = "Could not determine the problem."
    error_type: str = "Unknown"
    explanation: str = ""
    cause: str = ""
    solution: str = ""
    corrected_code: str = ""
    confidence: float = 0.0
    # Set to True if we fell back to plain-text wrapping
    is_fallback: bool = False

    # ── Display helpers ───────────────────────────────────────────────────────

    @property
    def confidence_label(self) -> str:
        if self.confidence >= 0.85:
            return "High confidence"
        if self.confidence >= 0.55:
            return "Medium confidence"
        return "Low confidence"

    @property
    def confidence_tone(self) -> str:
        """Maps to StatusChip tone strings used in the UI."""
        if self.confidence >= 0.85:
            return "ok"
        if self.confidence >= 0.55:
            return "warn"
        return "off"

    def short_summary(self) -> str:
        """Single-line human-readable summary for display in compact views."""
        return self.problem or self.explanation[:120] or "Analysis unavailable."

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_plain_text(cls, text: str) -> "ErrorAnalysis":
        """Wrap a plain-text AI reply when JSON parsing fails entirely."""
        return cls(
            problem="See explanation below.",
            error_type="General",
            explanation=text.strip()[:800],
            cause="",
            solution="",
            corrected_code="",
            confidence=0.3,
            is_fallback=True,
        )

    @classmethod
    def unavailable(cls, reason: str = "") -> "ErrorAnalysis":
        """Sentinel returned when the AI is unreachable or the request fails."""
        return cls(
            problem=reason or "Analysis unavailable.",
            error_type="N/A",
            explanation="The AI service could not be reached. Try again or switch to mock mode.",
            confidence=0.0,
            is_fallback=True,
        )


# ── Parser ────────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that models sometimes add around JSON."""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


# Schema keys eligible for lenient salvage, in document order.
_SALVAGEABLE_FIELDS = (
    "problem",
    "error_type",
    "explanation",
    "cause",
    "solution",
    "corrected_code",
)


def _salvage_fields(text: str) -> ErrorAnalysis | None:
    """Best-effort field recovery when strict JSON parsing fails.

    Handles the common small-model failure of unescaped double quotes
    inside string values (e.g. ``"cause": "... 'print("h)'. ..."``): each
    known key's value runs to the last quote before the next key or the
    closing brace. Returns None unless real content was recovered, in
    which case the plain-text fallback stays as the last resort.
    """
    found: dict[str, str] = {}
    for key in _SALVAGEABLE_FIELDS:
        match = re.search(
            r'"' + key + r'"\s*:\s*"(?P<val>.*?)"\s*(?:,|\})',
            text,
            re.DOTALL,
        )
        if match:
            found[key] = match.group("val").strip()
    if not found.get("problem") and not found.get("explanation"):
        return None
    conf_match = re.search(r'"confidence"\s*:\s*(?P<val>[0-9.]+)', text)
    try:
        confidence = max(0.0, min(1.0, float(conf_match.group("val")))) if conf_match else 0.5
    except (TypeError, ValueError):
        confidence = 0.5
    return ErrorAnalysis(
        problem=found.get("problem", "See explanation below."),
        error_type=found.get("error_type", "Unknown").strip() or "Unknown",
        explanation=found.get("explanation", ""),
        cause=found.get("cause", ""),
        solution=found.get("solution", ""),
        corrected_code=found.get("corrected_code", ""),
        confidence=confidence,
        is_fallback=False,
    )


def parse_error_analysis(raw: str) -> ErrorAnalysis:
    """Convert the raw AI response string into an ErrorAnalysis.

    Never raises; always returns a usable object.
    """
    cleaned = _strip_fences(raw)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        # Not strict JSON: try field salvage before plain-text fallback.
        salvaged = _salvage_fields(cleaned)
        if salvaged is not None:
            return salvaged
        return ErrorAnalysis.from_plain_text(raw)

    if not isinstance(data, dict):
        return ErrorAnalysis.from_plain_text(raw)

    # Normalise confidence: clamp to [0, 1]
    raw_conf = data.get("confidence", 0.0)
    try:
        confidence = float(raw_conf)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return ErrorAnalysis(
        problem=str(data.get("problem", "")).strip(),
        error_type=str(data.get("error_type", "Unknown")).strip(),
        explanation=str(data.get("explanation", "")).strip(),
        cause=str(data.get("cause", "")).strip(),
        solution=str(data.get("solution", "")).strip(),
        corrected_code=str(data.get("corrected_code", "")).strip(),
        confidence=confidence,
        is_fallback=False,
    )
