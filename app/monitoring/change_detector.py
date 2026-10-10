"""Lightweight local frame comparison. It deliberately retains no screenshots."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


_THRESHOLDS = {"low": 0.18, "medium": 0.10, "high": 0.045}


@dataclass(frozen=True)
class ChangeResult:
    changed: bool
    score: float


class ChangeDetector:
    """Compares a tiny grayscale signature, retaining only the last signature."""

    def __init__(self) -> None:
        self._previous: bytes | None = None

    def reset(self) -> None:
        self._previous = None

    def compare(self, frame: QImage, sensitivity: str) -> ChangeResult:
        reduced = frame.convertToFormat(QImage.Format.Format_Grayscale8).scaled(
            96,
            54,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        signature = bytes(reduced.constBits())
        if not signature:
            return ChangeResult(False, 0.0)
        previous = self._previous
        self._previous = signature
        if previous is None or len(previous) != len(signature):
            return ChangeResult(True, 1.0)
        score = sum(abs(current - prior) for current, prior in zip(signature, previous)) / (255 * len(signature))
        return ChangeResult(score >= _THRESHOLDS.get(sensitivity, _THRESHOLDS["medium"]), score)
