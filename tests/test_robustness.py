"""Phase 10 — Robustness: API failures, parser edges, OCR/monitor/DB error paths.

No network calls. Monitor/Companion tests use the offscreen Qt platform.
"""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ProviderFailureTests(unittest.TestCase):
    def test_empty_key_is_configuration_error(self) -> None:
        from app.core.ai_service import AIConfigurationError, OpenAIProvider

        with self.assertRaises(AIConfigurationError):
            OpenAIProvider("   ")

    def test_error_mapping_covers_sdk_names(self) -> None:
        from app.core.ai_service import (
            AIAuthenticationError,
            AIConnectionError,
            AIRateLimitError,
            AIServiceError,
            AITimeoutError,
            OpenAIProvider,
        )

        cases = {
            "AuthenticationError": AIAuthenticationError,
            "RateLimitError": AIRateLimitError,
            "APITimeoutError": AITimeoutError,
            "APIConnectionError": AIConnectionError,
            "APIConnectionTimeoutError": AIConnectionError,
            "SomethingElse": AIServiceError,
        }
        for name, expected in cases.items():
            err = type(name, (Exception,), {})()
            mapped = OpenAIProvider._map_error(err)
            self.assertIsInstance(mapped, expected, f"mapping for {name}")

    def test_mock_empty_message_is_safe_error(self) -> None:
        from app.core.ai_service import AIService, AIServiceError
        from app.core.session import ChatMessage

        service = AIService.from_config()
        if service.is_live:
            self.skipTest("Live mode enabled; skipping mock-only assertion.")
        with self.assertRaises(AIServiceError):
            service.reply([ChatMessage("user", "   ")], "model")

    def test_analysis_unavailable_on_provider_failure(self) -> None:
        from app.ai.error_analysis_service import ErrorAnalysisService
        from app.core.ai_service import AIService, AIServiceError
        from app.core.session import ChatMessage
        from app.detection.models import DetectedError, DetectionCategory

        class Boom:
            def reply(self, messages, model, instructions=None):
                raise AIServiceError("down")

        service = ErrorAnalysisService(AIService(provider=Boom(), is_live=False))  # type: ignore[arg-type]
        result = service.analyse(
            DetectedError(category=DetectionCategory.CONFIRMED_ERROR, raw_context="NameError: x")
        )
        self.assertTrue(result.is_fallback)
        self.assertEqual(result.confidence, 0.0)
        _ = ChatMessage("user", "x")


class ParserEdgeTests(unittest.TestCase):
    def test_fenced_json_parses(self) -> None:
        from app.ai.response_parser import parse_error_analysis

        raw = '```json\n{"problem": "p", "error_type": "NameError", "explanation": "e", "cause": "c", "solution": "s", "corrected_code": "x = 1", "confidence": 0.9}\n```'
        result = parse_error_analysis(raw)
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.error_type, "NameError")
        self.assertEqual(result.corrected_code, "x = 1")

    def test_partial_json_fills_defaults(self) -> None:
        from app.ai.response_parser import parse_error_analysis

        result = parse_error_analysis('{"error_type": "TypeError"}')
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.error_type, "TypeError")
        self.assertEqual(result.problem, "")

    def test_broken_json_salvages_problem(self) -> None:
        # Truncated but field-shaped JSON now salvages instead of falling back.
        from app.ai.response_parser import parse_error_analysis

        result = parse_error_analysis('{"problem": "oops", ')
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.problem, "oops")

    def test_salvage_unescaped_quotes_recovers_fields(self) -> None:
        # Live failure shape: valid-looking JSON with raw quotes inside
        # values (small-model output) must salvage, not fall back.
        from app.ai.response_parser import parse_error_analysis

        raw = (
            '{\n"problem": "Missing quote.",\n'
            '"error_type": "SyntaxError",\n'
            '"explanation": "E.",\n'
            '"cause": "Line has \'print("x) wrong.",\n'
            '"solution": "S.",\n'
            '"corrected_code": "",\n'
            '"confidence": 0.8\n}'
        )
        result = parse_error_analysis(raw)
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.error_type, "SyntaxError")
        self.assertIn("print(", result.cause)
        self.assertEqual(result.confidence, 0.8)

    def test_salvage_missing_confidence_defaults_mid(self) -> None:
        from app.ai.response_parser import parse_error_analysis

        raw = '{"problem": "P.", "explanation": "E."}'
        self.assertTrue(__import__("json").loads(raw))  # sanity: strict path untouched
        raw2 = '{"problem": "P.", "explanation": "E.", "confidence": }'
        result = parse_error_analysis(raw2)
        self.assertFalse(result.is_fallback)
        self.assertEqual(result.confidence, 0.5)

    def test_salvage_garbage_still_falls_back(self) -> None:
        from app.ai.response_parser import parse_error_analysis

        result = parse_error_analysis("Error 404 happened here, no json at all")
        self.assertTrue(result.is_fallback)

    def test_non_dict_json_falls_back(self) -> None:
        from app.ai.response_parser import parse_error_analysis

        result = parse_error_analysis("[1, 2, 3]")
        self.assertTrue(result.is_fallback)

    def test_confidence_clamped(self) -> None:
        from app.ai.response_parser import parse_error_analysis

        high = parse_error_analysis('{"problem": "p", "confidence": 5}')
        self.assertEqual(high.confidence, 1.0)
        low = parse_error_analysis('{"problem": "p", "confidence": -3}')
        self.assertEqual(low.confidence, 0.0)
        bad = parse_error_analysis('{"problem": "p", "confidence": "nonsense"}')
        self.assertEqual(bad.confidence, 0.0)

    def test_confidence_labels(self) -> None:
        from app.ai.response_parser import ErrorAnalysis

        self.assertEqual(ErrorAnalysis(confidence=0.9).confidence_label, "High confidence")
        self.assertEqual(ErrorAnalysis(confidence=0.6).confidence_tone, "warn")
        self.assertEqual(ErrorAnalysis(confidence=0.1).confidence_label, "Low confidence")
        self.assertTrue(ErrorAnalysis.unavailable("x").is_fallback)


class OCRFailureTests(unittest.TestCase):
    def test_missing_binary_reports_unavailable(self) -> None:
        from unittest.mock import patch

        from PySide6.QtGui import QColor, QImage

        from app.ocr.ocr_service import OCRService

        with patch("app.ocr.ocr_service.Config.TESSERACT_PATH", ""):
            service = OCRService(tesseract_cmd="/nonexistent/tesseract")
            self.assertFalse(service.is_available)
            img = QImage(100, 40, QImage.Format.Format_ARGB32)
            img.fill(QColor("#ffffff"))
            result = service.extract_text(img)
            self.assertFalse(result.success)
            self.assertIn("Tesseract", result.error)

    def test_null_and_bad_inputs_are_safe(self) -> None:
        from PySide6.QtGui import QImage

        from app.ocr.ocr_service import OCRService, preprocess_image, qimage_to_pil

        service = OCRService(tesseract_cmd="/nonexistent/tesseract")
        self.assertFalse(service.extract_text(QImage()).success)
        self.assertFalse(service.extract_text(object()).success)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            qimage_to_pil(QImage())
        from PIL import Image

        gray = preprocess_image(Image.new("RGB", (10, 10)))
        self.assertEqual(gray.mode, "L")


class MonitorLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from app.core.state import app_state

        self._saved = (
            app_state.monitoring_enabled,
            app_state.monitoring_paused,
            app_state.capture_region,
        )
        app_state.monitoring_enabled = False
        app_state.monitoring_paused = False

    def tearDown(self) -> None:
        from app.core.state import app_state
        from app.monitoring import monitor_service as ms_mod
        from app.monitoring.screen_capture import ScreenCapture

        app_state.monitoring_enabled, app_state.monitoring_paused, app_state.capture_region = self._saved
        if hasattr(self, "_orig_capture"):
            ScreenCapture.capture = self._orig_capture  # type: ignore[method-assign]
        if ms_mod._service is not None:
            try:
                ms_mod._service.stop()
            except Exception:
                pass
            ms_mod._service = None

    def _solid_image(self, color: str = "#112233"):
        from PySide6.QtGui import QColor, QImage

        img = QImage(160, 90, QImage.Format.Format_ARGB32)
        img.fill(QColor(color))
        return img

    def test_start_pause_resume_stop(self) -> None:
        from app.monitoring.monitor_service import get_monitor_service
        from app.monitoring.screen_capture import ScreenCapture

        self._orig_capture = ScreenCapture.capture
        ScreenCapture.capture = classmethod(lambda cls, key: self._solid_image())  # type: ignore[method-assign]
        service = get_monitor_service()
        service.start()
        self.assertTrue(service.is_running)
        service.pause()
        self.assertFalse(service.is_running)
        service.resume()
        self.assertTrue(service.is_running)
        service.stop()
        self.assertFalse(service.is_running)

    def test_capture_error_is_surfaced_not_raised(self) -> None:
        from app.core.state import app_state
        from app.monitoring.monitor_service import get_monitor_service
        from app.monitoring.screen_capture import ScreenCapture, ScreenCaptureError

        self._orig_capture = ScreenCapture.capture

        def _boom(cls, key: str):  # noqa: ANN001, ANN202
            raise ScreenCaptureError("no display in test")

        ScreenCapture.capture = classmethod(_boom)  # type: ignore[method-assign]
        service = get_monitor_service()
        service.start()  # must not raise
        self.assertTrue(app_state.monitor_last_error)
        service.stop()

    def test_start_silent_baseline_then_live(self) -> None:
        from app.core.events import bus
        from app.core.state import app_state
        from app.monitoring.monitor_service import get_monitor_service
        from app.monitoring.screen_capture import ScreenCapture

        self._orig_capture = ScreenCapture.capture
        ScreenCapture.capture = classmethod(lambda cls, key: self._solid_image("#112233"))  # type: ignore[method-assign]
        seen: list = []

        def _record(**payload: object) -> None:
            seen.append(payload)

        bus.subscribe("monitoring.frame_changed", _record)
        try:
            service = get_monitor_service()
            app_state.monitoring_enabled = False
            app_state.monitoring_paused = False
            service.start()  # silent baseline: captures, primes detector, emits nothing
            self.assertEqual(seen, [])
            self.assertGreaterEqual(app_state.monitor_frames_captured, 1)
            service._capture_tick()  # identical frame -> no change -> still nothing
            self.assertEqual(seen, [])
            ScreenCapture.capture = classmethod(lambda cls, key: self._solid_image("#ffffff"))  # type: ignore[method-assign]
            service._capture_tick()  # real change -> emits normally
            self.assertEqual(len(seen), 1)
            service.stop()
        finally:
            try:
                bus.unsubscribe("monitoring.frame_changed", _record)
            except Exception:
                pass


class CompanionAndSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_companion_force_idle(self) -> None:
        from app.core.state import app_state
        from app.services.companion_service import get_companion_service
        from app.services.companion_service import reset_companion_service

        service = get_companion_service()
        try:
            app_state.set_companion_state("RESPONDING")
            service.force_idle("test")
            self.assertEqual(app_state.companion_state, "IDLE")
        finally:
            reset_companion_service()

    def test_settings_rejects_invalid_values(self) -> None:
        import tempfile
        from pathlib import Path

        from app.core.state import app_state

        fd, path = tempfile.mkstemp(prefix="ai_companion_cfg_", suffix=".db")
        import os

        os.close(fd)
        from app.database.database import reset_database
        from app.database.repositories import SettingsRepository
        from app.services.settings_service import load_persisted_settings

        old = (app_state.theme, app_state.ai_model, app_state.history_retention_days)
        try:
            reset_database(path)
            repo = SettingsRepository(reset_database(path))
            repo.set("theme", "neon")
            repo.set("ai_model", "")
            repo.set("history_retention_days", "9999")
            load_persisted_settings()
            self.assertEqual(app_state.theme, old[0])
            self.assertEqual(app_state.history_retention_days, old[2])
        finally:
            from app.core.config import Config

            app_state.theme, app_state.ai_model, app_state.history_retention_days = old
            reset_database(Config.DB_PATH)
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

    def test_database_survives_reopen(self) -> None:
        import tempfile
        from pathlib import Path

        fd, path = tempfile.mkstemp(prefix="ai_companion_reopen_", suffix=".db")
        import os

        os.close(fd)
        try:
            from app.database.database import reset_database
            from app.database.repositories import ErrorRepository

            reset_database(path)
            ErrorRepository(reset_database(path)).add("Python", "E", "m", "s")
            from app.core.config import Config

            reset_database(path)
            self.assertEqual(ErrorRepository(reset_database(path)).count(), 1)
            reset_database(Config.DB_PATH)
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
