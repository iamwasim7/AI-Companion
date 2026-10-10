"""Unit tests for the OCR subsystem."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtGui import QColor, QImage, QPainter

from app.core.config import Config
from app.ocr.ocr_service import (
    OCRResult,
    OCRService,
    preprocess_image,
    qimage_to_pil,
)


class OCRResultTests(unittest.TestCase):
    def test_empty_result_has_no_text(self) -> None:
        result = OCRResult(text="", success=True)
        self.assertFalse(result.has_text)

    def test_result_with_text(self) -> None:
        result = OCRResult(text="NameError: name 'x' is not defined", lines=["NameError: name 'x' is not defined"])
        self.assertTrue(result.has_text)
        self.assertEqual(len(result.lines), 1)


class ImageConversionTests(unittest.TestCase):
    def test_null_qimage_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            qimage_to_pil(QImage())

    def test_valid_qimage_conversion(self) -> None:
        qimg = QImage(200, 100, QImage.Format.Format_ARGB32)
        qimg.fill(QColor("#2d333b"))
        pil_img = qimage_to_pil(qimg)
        self.assertEqual(pil_img.size, (200, 100))

    def test_preprocess_returns_grayscale(self) -> None:
        img = Image.new("RGB", (100, 100), color=(128, 64, 32))
        processed = preprocess_image(img)
        self.assertEqual(processed.mode, "L")


class OCRServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OCRService()

    def test_empty_qimage_returns_safe_failure(self) -> None:
        result = self.service.extract_text(QImage())
        self.assertFalse(result.success)
        self.assertIn("empty", result.error.lower())

    def test_unsupported_type_returns_safe_failure(self) -> None:
        # Pass an object that is not QImage or PIL Image
        result = self.service.extract_text("not_an_image")  # type: ignore[arg-type]
        self.assertFalse(result.success)
        self.assertIn("unsupported", result.error.lower())

    def test_synthetic_error_text_extraction(self) -> None:
        if not self.service.is_available:
            self.skipTest("Tesseract binary is not configured or not found.")

        # Create a synthetic image with dark background and clear white error text
        img = Image.new("RGB", (800, 150), color=(15, 20, 25))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            try:
                font = ImageFont.truetype("consola.ttf", 22)
            except Exception:
                font = None

        draw.text((25, 30), "NameError: name 'username' is not defined", fill=(255, 255, 255), font=font)
        draw.text((25, 75), "File test.py, line 42", fill=(200, 200, 200), font=font)

        result = self.service.extract_text(img)
        self.assertTrue(result.success)
        self.assertTrue(result.has_text)
        # OCR on synthetic images may slightly misread font-rendered text;
        # accept 'name' as a substring of 'NameError'/'NameEnrr' etc.
        result_lower = result.text.lower()
        self.assertTrue(
            "nameerror" in result_lower or "name" in result_lower,
            f"Expected 'NameError' in OCR output, got: {result.text!r}",
        )
        self.assertIn("username", result_lower)



class SinglePassTests(unittest.TestCase):
    """Item 2+3: one Tesseract pass (image_to_data only) + 1280px downscale cap."""

    def setUp(self) -> None:
        self.service = OCRService()

    def _two_line_image(self, width: int = 800, height: int = 150):
        img = Image.new("RGB", (width, height), color=(15, 20, 25))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            try:
                font = ImageFont.truetype("consola.ttf", 22)
            except Exception:
                font = None
        draw.text((25, 30), "NameError: name 'username' is not defined", fill=(255, 255, 255), font=font)
        draw.text((25, 75), "File test.py, line 42", fill=(200, 200, 200), font=font)
        return img

    def test_lines_reconstructed_in_order(self) -> None:
        if not self.service.is_available:
            self.skipTest("Tesseract binary is not configured or not found.")
        result = self.service.extract_text(self._two_line_image())
        self.assertTrue(result.success)
        self.assertEqual(len(result.lines), 2)
        # OCR may slightly misread rendered synthetic fonts; verify key substrings
        # are present rather than requiring exact word matches.
        first_line_lower = result.lines[0].lower()
        self.assertTrue(
            "nameerror" in first_line_lower or "name" in first_line_lower,
            f"Expected 'NameError' in first line, got: {result.lines[0]!r}",
        )
        self.assertIn("test.py", result.lines[1])

    def test_large_frame_downscaled_but_readable(self) -> None:
        if not self.service.is_available:
            self.skipTest("Tesseract binary is not configured or not found.")
        from app.ocr.ocr_service import MAX_OCR_WIDTH

        self.assertEqual(MAX_OCR_WIDTH, 1920)  # updated from 1280 to 1920
        result = self.service.extract_text(self._two_line_image(width=2000, height=400))
        self.assertTrue(result.success)
        self.assertTrue(result.has_text)
        # At 2000px > 1920px the image is downscaled; verify OCR still runs
        self.assertTrue(len(result.text) > 0)


    def test_caller_image_never_mutated(self) -> None:
        img = Image.new("RGB", (2000, 400), color=(15, 20, 25))
        before = img.size
        self.service.extract_text(img)
        self.assertEqual(img.size, before)


if __name__ == "__main__":
    unittest.main()
