"""Phase 7 — Detection pipeline: screen change → OCR → detection → AI analysis.

Cost-conscious flow (per Master Spec §10):

    monitoring.frame_changed (local, rate-limited)
        ↓
    OCR off UI thread (local Tesseract, in-memory only)
        ↓
    ErrorDetector + ContextDetector (local, free)
        ↓
    has_error? — NO → update state, no API call
                 YES → dedup/cooldown check → bus "analysis.run" → OpenAI (one-shot)

Privacy: frames are never written to disk and never sent to OpenAI.
Only the concise text context from ``ContextDetector.format_ai_context``
is sent, and only after a local error signal.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage

from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state
from app.detection.context_detector import ContextDetector
from app.detection.error_detector import get_error_detector
from app.detection.models import DetectedError, DetectionCategory

logger = get_logger("services.pipeline")

# Cost/UX guards — keep API calls rare.
ANALYSIS_COOLDOWN_SECONDS = 20.0
MIN_OCR_TEXT_LENGTH = 12
MAX_CONTEXT_CHARS = 2000


def process_ocr_text(text: str) -> DetectedError:
    """Pure helper: run local detection on OCR text (testable without Qt)."""
    cleaned = (text or "").strip()
    if len(cleaned) < MIN_OCR_TEXT_LENGTH:
        return DetectedError(
            category=DetectionCategory.GENERAL_CONTEXT,
            raw_context=cleaned,
        )
    clipped = cleaned[:MAX_CONTEXT_CHARS]
    return get_error_detector().detect(clipped)


def _signature_for(detected: DetectedError) -> str:
    """Stable dedup key so the same on-screen error doesn't spam the API."""
    basis = f"{detected.error_type}|{detected.error_message}|{detected.file_path}|{detected.line_number}"
    return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()[:16]


@dataclass
class PipelineStats:
    ocr_runs: int = 0
    detections: int = 0
    analyses_triggered: int = 0
    analyses_skipped_cooldown: int = 0
    analyses_skipped_duplicate: int = 0


class OCRWorker(QThread):
    """Off-UI-thread OCR + local detection for a single frame."""

    succeeded = Signal(object, object)  # (OCR text str, DetectedError)
    failed = Signal(str)

    def __init__(self, frame: QImage) -> None:
        super().__init__()
        # QImage is implicitly shared — detach so the capture thread can continue.
        self._frame = frame.copy() if not frame.isNull() else QImage()

    def run(self) -> None:
        try:
            from app.ocr.ocr_service import get_ocr_service

            ocr = get_ocr_service()
            if not ocr.is_available:
                self.failed.emit("OCR unavailable: Tesseract binary not configured.")
                return
            result = ocr.extract_text(self._frame)
            if not result.success:
                self.failed.emit(result.error or "OCR processing failed.")
                return
            detected = process_ocr_text(result.text)
            self.succeeded.emit(result.text, detected)
        except Exception as exc:  # Never crash the monitor thread.
            logger.exception("OCRWorker crashed: %s", type(exc).__name__)
            try:
                self.failed.emit("OCR processing failed unexpectedly.")
            except Exception:
                pass


class DetectionPipeline(QObject):
    """Subscribes to monitor events and triggers AI analysis only when useful."""

    def __init__(self) -> None:
        super().__init__()
        self._worker: OCRWorker | None = None
        self._pending: QImage | None = None  # latest-wins slot, depth 1 (never a queue)
        self._last_analysis_at: float = 0.0
        self._last_signature: str = ""
        self._last_signature_at: float = 0.0
        self.stats = PipelineStats()
        self._detector = ContextDetector()
        bus.subscribe("monitoring.frame_changed", self._on_frame_changed)
        bus.subscribe("monitoring.stop", self._on_monitoring_stopped)
        logger.info("Detection pipeline ready (cooldown=%ss)", ANALYSIS_COOLDOWN_SECONDS)

    # ── Event entry ──────────────────────────────────────────────────────

    def _start_ocr_worker(self, frame: QImage) -> None:
        """Start one OCR job. Caller owns scheduling; always runs on UI thread."""
        self.stats.ocr_runs += 1
        app_state.set_companion_state("ANALYZING")
        bus.emit("companion.state", state="ANALYZING")
        worker = OCRWorker(frame)
        worker.succeeded.connect(self._on_ocr_succeeded)
        worker.failed.connect(self._on_ocr_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()
        logger.debug("OCR job started from screen change")

    def _on_frame_changed(self, frame: QImage | None = None, **_payload: object) -> None:
        if not app_state.monitoring_enabled or app_state.monitoring_paused:
            return
        if frame is None or frame.isNull():
            return
        if self._worker is not None:
            # Latest wins: keep only the newest pending frame, drop older ones.
            # Bounded by construction (single slot) — never an unbounded queue.
            self._pending = frame.copy()
            return
        now = time.monotonic()
        if now - self._last_analysis_at < 2.0 and self._last_analysis_at > 0:
            # Tiny guard against back-to-back frames; full cooldown applies to API calls.
            pass
        self._start_ocr_worker(frame)

    def _on_monitoring_stopped(self, **_payload: object) -> None:
        self._pending = None  # Never process a stale frame from a previous run.
        if app_state.companion_state == "ANALYZING":
            app_state.set_companion_state("IDLE")
            bus.emit("companion.state", state="IDLE")

    # ── OCR results ──────────────────────────────────────────────────────

    def _on_ocr_succeeded(self, text: object, detected: object) -> None:
        from datetime import datetime

        assert isinstance(detected, DetectedError)
        ocr_text = str(text or "")
        app_state.ocr_last_extracted_length = len(ocr_text.strip())
        app_state.ocr_last_error = ""
        app_state.last_detected_error = detected.display_title
        app_state.last_detected_category = detected.category.value
        app_state.last_detected_language = detected.language
        app_state.last_detected_at = datetime.now().strftime("%H:%M:%S")
        self.stats.detections += 1

        logger.info(
            "Detection: category=%s lang=%s error=%s",
            detected.category.value,
            detected.language,
            detected.error_type or "-",
        )
        bus.emit("detection.updated", detected=detected)
        bus.emit("state.changed")

        if not detected.has_error:
            self._return_companion_idle()
            return

        # Dedup: same error signature seen recently → skip API call.
        now = time.monotonic()
        signature = _signature_for(detected)
        if signature == self._last_signature and (now - self._last_signature_at) < ANALYSIS_COOLDOWN_SECONDS * 3:
            self.stats.analyses_skipped_duplicate += 1
            logger.info("Skipping duplicate analysis (signature=%s)", signature)
            bus.emit("analysis.skipped", detected=detected, reason="duplicate")
            self._return_companion_idle()
            return
        # Cooldown: don't hammer the API on every keystroke.
        if (now - self._last_analysis_at) < ANALYSIS_COOLDOWN_SECONDS:
            self.stats.analyses_skipped_cooldown += 1
            logger.info("Skipping analysis due to cooldown")
            bus.emit("analysis.skipped", detected=detected, reason="cooldown")
            self._return_companion_idle()
            return

        self._last_analysis_at = now
        self._last_signature = signature
        self._last_signature_at = now
        self.stats.analyses_triggered += 1
        app_state.set_companion_state("ALERT")
        bus.emit("companion.state", state="ALERT")
        bus.emit("analysis.run", detected=detected)
        bus.emit("state.changed")
        logger.info("Analysis triggered: %s", detected.display_title)

    def _on_ocr_failed(self, message: str) -> None:
        app_state.ocr_last_error = message
        logger.warning("OCR step failed: %s", message[:120])
        bus.emit("state.changed")
        self._return_companion_idle()

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        # Finished runs on the worker thread; the slot executes on the UI
        # thread (receiver affinity), so touching _pending here is safe.
        pending, self._pending = self._pending, None
        if pending is not None and not pending.isNull():
            if app_state.monitoring_enabled and not app_state.monitoring_paused:
                self._start_ocr_worker(pending)
            else:
                logger.debug("Discarding pending frame: monitoring no longer active")

    def _return_companion_idle(self) -> None:
        # The AnalysisPanel owns the companion state once analysis starts.
        # Here we only reset when we did NOT trigger analysis.
        if app_state.companion_state == "ANALYZING":
            app_state.set_companion_state("IDLE")
            bus.emit("companion.state", state="IDLE")
            bus.emit("state.changed")

    # ── Manual entry (UI "Analyse screen now" / tests) ──────────────────

    def analyse_text(self, text: str) -> DetectedError:
        """Run detection on arbitrary text and trigger analysis if it's an error."""
        detected = process_ocr_text(text)
        from datetime import datetime

        app_state.last_detected_error = detected.display_title
        app_state.last_detected_category = detected.category.value
        app_state.last_detected_language = detected.language
        app_state.last_detected_at = datetime.now().strftime("%H:%M:%S")
        bus.emit("detection.updated", detected=detected)
        if detected.has_error:
            bus.emit("analysis.run", detected=detected)
        bus.emit("state.changed")
        return detected


_pipeline: DetectionPipeline | None = None


def get_detection_pipeline() -> DetectionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DetectionPipeline()
    return _pipeline


def reset_detection_pipeline() -> None:
    global _pipeline
    _pipeline = None
