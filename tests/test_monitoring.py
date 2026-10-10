"""Local monitoring tests. They create in-memory images and never capture a display."""

from __future__ import annotations

import unittest

from PySide6.QtGui import QColor, QImage

from app.monitoring.change_detector import ChangeDetector


def image_with_color(color: str) -> QImage:
    image = QImage(160, 90, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


class ChangeDetectorTests(unittest.TestCase):
    def test_first_frame_is_a_change(self) -> None:
        detector = ChangeDetector()
        self.assertTrue(detector.compare(image_with_color("#000000"), "medium").changed)

    def test_same_frame_has_no_change(self) -> None:
        detector = ChangeDetector()
        detector.compare(image_with_color("#000000"), "medium")
        result = detector.compare(image_with_color("#000000"), "medium")
        self.assertFalse(result.changed)
        self.assertEqual(result.score, 0.0)

    def test_large_change_is_detected(self) -> None:
        detector = ChangeDetector()
        detector.compare(image_with_color("#000000"), "low")
        result = detector.compare(image_with_color("#ffffff"), "low")
        self.assertTrue(result.changed)
        self.assertGreater(result.score, 0.9)

    def test_reset_makes_next_frame_new(self) -> None:
        detector = ChangeDetector()
        detector.compare(image_with_color("#000000"), "medium")
        detector.reset()
        self.assertTrue(detector.compare(image_with_color("#000000"), "medium").changed)


if __name__ == "__main__":
    unittest.main()
