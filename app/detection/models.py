"""Data models for error detection and context extraction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DetectionCategory(str, Enum):
    """Categorization of detected screen text."""

    CONFIRMED_ERROR = "CONFIRMED ERROR"
    POSSIBLE_ERROR = "POSSIBLE ERROR"
    GENERAL_CONTEXT = "GENERAL CONTEXT"


@dataclass
class DetectedError:
    """Structured information extracted from screen or terminal text."""

    category: DetectionCategory = DetectionCategory.GENERAL_CONTEXT
    language: str = "General"
    error_type: str = ""
    error_message: str = ""
    file_path: str = ""
    line_number: int | None = None
    column: int | None = None
    relevant_code: str = ""
    full_traceback: str = ""
    confidence: float = 0.0
    source_application: str = "Unknown"
    raw_context: str = ""

    @property
    def has_error(self) -> bool:
        return self.category in (
            DetectionCategory.CONFIRMED_ERROR,
            DetectionCategory.POSSIBLE_ERROR,
        )

    @property
    def display_title(self) -> str:
        if self.error_type and self.language != "General":
            return f"{self.language} {self.error_type}"
        if self.error_type:
            return self.error_type
        if self.has_error:
            return f"{self.category.value} Detected"
        return "General Context"

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.language:
            lines.append(f"Language: {self.language}")
        if self.error_type:
            lines.append(f"Error Type: {self.error_type}")
        if self.error_message:
            lines.append(f"Message: {self.error_message}")
        if self.file_path:
            location = f"File: {self.file_path}"
            if self.line_number is not None:
                location += f", Line {self.line_number}"
            lines.append(location)
        if self.relevant_code:
            lines.append(f"Code: {self.relevant_code}")
        return lines
