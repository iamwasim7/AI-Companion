"""OCR subsystem for extracting text and code from captured screen frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import os

from PIL import Image, ImageEnhance
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from app.core.config import Config
from app.core.logger import get_logger

logger = get_logger("ocr.service")

# Latency guard: full-screen frames are downscaled to this max width before
# OCR (aspect ratio preserved). Set to 1920 so that standard 1080p screenshots
# (≤1920px wide) are never downscaled — preserving colon/quote pixels in small
# terminal fonts. On 4K displays (3840px), it halves rather than thirds the
# resolution compared to the previous 1280 limit.
MAX_OCR_WIDTH = 1920


@dataclass
class OCRResult:
    """Structured output returned from OCR analysis."""

    text: str = ""
    lines: list[str] = field(default_factory=list)
    confidence: float = 0.0
    success: bool = True
    error: str = ""

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())


def qimage_to_pil(qimage: QImage) -> Image.Image:
    """Convert a PySide6 QImage into a PIL Image safely in memory."""
    if qimage.isNull():
        raise ValueError("Cannot convert a null or empty QImage to PIL Image.")
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    qimage.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return Image.open(BytesIO(data)).copy()


def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess image to maximize OCR accuracy on code and error text.

    For dark-themed terminals (average luminosity < 110/255), applies a
    conservative contrast boost (1.5x) to sharpen light text on dark backgrounds.
    The original image object is never mutated; all operations return new images.
    Light-themed windows (avg >= 110) receive only grayscale conversion, exactly
    as before.
    """
    gray = image.convert("L") if image.mode != "L" else image
    # Detect dark background: average pixel value well below mid-grey.
    # Dark terminals typically average 20–60; light VS Code windows average 200+.
    pixel_count = gray.width * gray.height
    if pixel_count > 0:
        try:
            avg = sum(gray.getdata()) / pixel_count
        except Exception:
            avg = 128  # fallback: assume light background
        if avg < 110:
            gray = ImageEnhance.Contrast(gray).enhance(1.5)
    return gray



class OCRService:
    """Provides local OCR text extraction using Tesseract."""

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        self._tesseract_cmd = tesseract_cmd or Config.TESSERACT_PATH
        self._configured = False
        self._init_pytesseract()

    def _init_pytesseract(self) -> None:
        try:
            import pytesseract

            if self._tesseract_cmd and os.path.isfile(self._tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
                self._configured = True
            elif Config.TESSERACT_PATH and os.path.isfile(Config.TESSERACT_PATH):
                self._tesseract_cmd = Config.TESSERACT_PATH
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
                self._configured = True
            else:
                self._configured = False
        except ImportError:
            self._configured = False
            logger.warning("pytesseract library is not installed.")

    @property
    def is_available(self) -> bool:
        if not self._configured:
            self._init_pytesseract()
        return self._configured

    def extract_text(
        self,
        image: QImage | Image.Image,
        *,
        preprocess: bool = True,
    ) -> OCRResult:
        """Extract visible text from a QImage or PIL Image safely."""
        try:
            if isinstance(image, QImage):
                if image.isNull():
                    return OCRResult(success=False, error="Input QImage is empty.")
                pil_img = qimage_to_pil(image)
            elif isinstance(image, Image.Image):
                pil_img = image
            else:
                return OCRResult(success=False, error=f"Unsupported image type: {type(image)}")
        except Exception as exc:
            logger.error("Failed to prepare image for OCR: %s", exc)
            return OCRResult(success=False, error=f"Image conversion error: {exc}")

        if not self.is_available:
            msg = "Tesseract OCR binary not found. Configure TESSERACT_PATH in .env or Settings."
            logger.warning(msg)
            return OCRResult(success=False, error=msg)

        if pil_img.width > MAX_OCR_WIDTH:
            # resize() returns a new image; the caller's object is never mutated.
            scale = MAX_OCR_WIDTH / pil_img.width
            new_size = (MAX_OCR_WIDTH, max(1, round(pil_img.height * scale)))
            pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

        try:
            import pytesseract

            target_img = preprocess_image(pil_img) if preprocess else pil_img
            # Single Tesseract pass: image_to_data yields both words (for text
            # reconstruction) and confidences. A second image_to_string call
            # would double OCR latency for identical output.
            data = pytesseract.image_to_data(target_img, output_type=pytesseract.Output.DICT)
            texts = data.get("text", [])
            count = len(texts)
            blocks = data.get("block_num", [0] * count)
            pars = data.get("par_num", [0] * count)
            lines_no = data.get("line_num", [0] * count)
            confs_raw = data.get("conf", [])

            ordered_lines: dict[tuple[int, int, int], list[str]] = {}
            for index in range(count):
                word = (texts[index] or "").strip()
                if not word:
                    continue
                key = (int(blocks[index]), int(pars[index]), int(lines_no[index]))
                ordered_lines.setdefault(key, []).append(word)
            non_empty_lines = [" ".join(words).strip() for words in ordered_lines.values()]
            non_empty_lines = [line for line in non_empty_lines if line]
            clean_text = "\n".join(non_empty_lines)

            confidence = 0.0
            confs = [
                float(c)
                for c in confs_raw
                if str(c).replace(".", "", 1).isdigit() and float(c) > 0
            ]
            if confs:
                confidence = round(sum(confs) / len(confs), 2)

            return OCRResult(
                text=clean_text,
                lines=non_empty_lines,
                confidence=confidence,
                success=True,
                error="",
            )
        except Exception as exc:
            err_name = type(exc).__name__
            logger.error("OCR extraction failed (%s): %s", err_name, exc)
            return OCRResult(
                success=False,
                error=f"OCR processing failed: {exc}",
            )


_ocr_service: OCRService | None = None


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
