"""Phase 7 tests: pipeline helpers + structured error-analysis service (mock only)."""

from __future__ import annotations

import unittest

from app.ai.error_analysis_service import ErrorAnalysisService
from app.ai.prompts import SYSTEM_PROMPT, build_analysis_prompt
from app.ai.response_parser import parse_error_analysis
from app.core.ai_service import AIService, MockProvider
from app.core.session import ChatMessage
from app.detection.context_detector import ContextDetector
from app.detection.models import DetectedError, DetectionCategory
from app.services.detection_pipeline import (
    _signature_for,
    process_ocr_text,
)


class PipelineHelperTests(unittest.TestCase):
    def test_short_text_is_general_context(self) -> None:
        detected = process_ocr_text("hi")
        self.assertEqual(detected.category, DetectionCategory.GENERAL_CONTEXT)
        self.assertFalse(detected.has_error)

    def test_traceback_text_is_confirmed(self) -> None:
        text = (
            'Traceback (most recent call last):\n'
            '  File "main.py", line 12, in <module>\n'
            "    print(username)\n"
            "NameError: name 'username' is not defined"
        )
        detected = process_ocr_text(text)
        self.assertEqual(detected.category, DetectionCategory.CONFIRMED_ERROR)
        self.assertEqual(detected.error_type, "NameError")
        self.assertEqual(detected.file_path, "main.py")
        self.assertEqual(detected.line_number, 12)

    def test_signature_stable_and_distinct(self) -> None:
        a = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            error_type="NameError",
            error_message="name 'x' is not defined",
        )
        b = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            error_type="NameError",
            error_message="name 'x' is not defined",
        )
        c = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            error_type="TypeError",
            error_message="bad",
        )
        self.assertEqual(_signature_for(a), _signature_for(b))
        self.assertNotEqual(_signature_for(a), _signature_for(c))


class _FakeSignal:
    def __init__(self) -> None:
        self.handlers: list = []

    def connect(self, handler) -> None:
        self.handlers.append(handler)

    def fire(self) -> None:
        for handler in list(self.handlers):
            handler()


class _FakeOCRWorker:
    """Stand-in for OCRWorker: never spawns threads, records scheduling."""

    instances: list = []

    def __init__(self, frame) -> None:
        self.frame = frame
        self.started = False
        self.succeeded = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        _FakeOCRWorker.instances.append(self)

    def start(self) -> None:
        self.started = True

    def deleteLater(self) -> None:
        pass


def _solid_frame(width: int, height: int = 100):
    from PySide6.QtGui import QColor, QImage

    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#1e1e1e"))
    return img


class LatestWinsQueueTests(unittest.TestCase):
    """Item 4: busy worker parks only the newest frame (depth 1, never a queue)."""

    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        self._qt = QApplication.instance() or QApplication([])
        from unittest.mock import patch

        from app.core.events import bus
        from app.core.state import app_state
        from app.services import detection_pipeline as pipe_mod
        from app.services.detection_pipeline import DetectionPipeline

        self._bus = bus
        self._app_state = app_state
        self._saved_monitoring = (app_state.monitoring_enabled, app_state.monitoring_paused)
        self._saved_companion = app_state.companion_state
        app_state.monitoring_enabled = True
        app_state.monitoring_paused = False
        _FakeOCRWorker.instances.clear()
        self._patcher = patch.object(pipe_mod, "OCRWorker", _FakeOCRWorker)
        self._patcher.start()
        self.pipeline = DetectionPipeline()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(self._unsubscribe_pipeline)

    def tearDown(self) -> None:
        enabled, paused = self._saved_monitoring
        self._app_state.monitoring_enabled = enabled
        self._app_state.monitoring_paused = paused
        self._app_state.set_companion_state(self._saved_companion)

    def _unsubscribe_pipeline(self) -> None:
        try:
            self._bus.unsubscribe("monitoring.frame_changed", self.pipeline._on_frame_changed)
        except Exception:
            pass
        try:
            self._bus.unsubscribe("monitoring.stop", self.pipeline._on_monitoring_stopped)
        except Exception:
            pass

    def test_busy_worker_parks_newest_only(self) -> None:
        self.pipeline._on_frame_changed(frame=_solid_frame(200))
        self.assertEqual(len(_FakeOCRWorker.instances), 1)
        self.assertTrue(_FakeOCRWorker.instances[0].started)
        self.assertIsNone(self.pipeline._pending)
        self.pipeline._on_frame_changed(frame=_solid_frame(300))
        self.assertEqual(len(_FakeOCRWorker.instances), 1)  # no second worker
        self.assertEqual(self.pipeline._pending.width(), 300)
        self.pipeline._on_frame_changed(frame=_solid_frame(400))
        self.assertEqual(len(_FakeOCRWorker.instances), 1)
        self.assertEqual(self.pipeline._pending.width(), 400)  # latest wins

    def test_pending_consumed_on_finish_then_idle(self) -> None:
        self.pipeline._on_frame_changed(frame=_solid_frame(200))
        self.pipeline._on_frame_changed(frame=_solid_frame(400))
        _FakeOCRWorker.instances[0].finished.fire()
        self.assertEqual(len(_FakeOCRWorker.instances), 2)
        self.assertTrue(_FakeOCRWorker.instances[1].started)
        self.assertEqual(_FakeOCRWorker.instances[1].frame.width(), 400)
        self.assertIsNone(self.pipeline._pending)
        _FakeOCRWorker.instances[1].finished.fire()
        self.assertEqual(len(_FakeOCRWorker.instances), 2)  # nothing left to run
        self.assertIsNone(self.pipeline._worker)

    def test_pending_cleared_on_stop(self) -> None:
        self.pipeline._on_frame_changed(frame=_solid_frame(200))
        self.pipeline._on_frame_changed(frame=_solid_frame(300))
        self.pipeline._on_monitoring_stopped()
        self.assertIsNone(self.pipeline._pending)


class PromptTests(unittest.TestCase):
    def test_error_prompt_contains_schema_trigger(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="NameError",
            error_message="name 'username' is not defined",
            raw_context="NameError: name 'username' is not defined",
        )
        prompt = build_analysis_prompt(detected, "Error: NameError: name 'username' is not defined")
        self.assertIn("JSON schema", prompt)
        self.assertIn("NameError", prompt)

    def test_js_missing_quote_prompt_contains_code(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="JavaScript",
            error_type="SyntaxError",
            error_message="Invalid or unexpected token",
            file_path="testjs.js",
            line_number=1,
            relevant_code='console.log("Hello JS!)',
            raw_context="SyntaxError: Invalid or unexpected token",
        )
        prompt = build_analysis_prompt(detected, ContextDetector.format_ai_context(detected))
        self.assertIn('console.log("Hello JS!)', prompt)
        self.assertIn("Relevant Code:", prompt)
        self.assertIn("faulty", prompt)
        self.assertIn("corrected code", prompt)

    def test_python_nameerror_prompt_contains_code(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="NameError",
            error_message="name 'username' is not defined",
            file_path="main.py",
            line_number=12,
            relevant_code="print(username)",
            raw_context="NameError: name 'username' is not defined",
        )
        prompt = build_analysis_prompt(detected, ContextDetector.format_ai_context(detected))
        self.assertIn("Relevant Code: print(username)", prompt)
        self.assertIn("File: main.py", prompt)
        self.assertIn("Line: 12", prompt)

    def test_java_npe_prompt_contains_context(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Java",
            error_type="NullPointerException",
            error_message="",
            file_path="App.java",
            line_number=14,
            raw_context='Exception in thread "main" java.lang.NullPointerException',
        )
        prompt = build_analysis_prompt(detected, ContextDetector.format_ai_context(detected))
        self.assertIn("Language: Java", prompt)
        self.assertIn("NullPointerException", prompt)
        self.assertIn("App.java", prompt)

    def test_c_compiler_prompt_contains_context(self) -> None:
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="C",
            error_type="Compiler Error",
            error_message="implicit declaration of function 'foo'",
            file_path="main.c",
            line_number=5,
            relevant_code="foo(1);",
            raw_context="main.c:5:3: error: implicit declaration",
        )
        prompt = build_analysis_prompt(detected, ContextDetector.format_ai_context(detected))
        self.assertIn("Language: C", prompt)
        self.assertIn("Relevant Code: foo(1);", prompt)

    def test_incomplete_context_prompt_shape(self) -> None:
        # No code available: prompt must stay well-formed and must not
        # invent code -- the model is told to admit uncertainty instead.
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="JavaScript",
            error_type="SyntaxError",
            error_message="Invalid or unexpected token",
            raw_context="SyntaxError: Invalid or unexpected token",
        )
        prompt = build_analysis_prompt(detected, ContextDetector.format_ai_context(detected))
        self.assertIn("Error: SyntaxError: Invalid or unexpected token", prompt)
        self.assertNotIn("Relevant Code:", prompt)

    def test_system_prompt_demands_honest_confidence(self) -> None:
        self.assertNotIn('"confidence": 0.95', SYSTEM_PROMPT)
        self.assertIn("Never copy an example value", SYSTEM_PROMPT)
        self.assertIn("instead of inventing a cause", SYSTEM_PROMPT)

    def test_corrected_code_must_be_code_only(self) -> None:
        self.assertIn("ONLY the fixed source code", SYSTEM_PROMPT)
        self.assertIn("no markdown fences", SYSTEM_PROMPT)
        self.assertIn("no surrounding quotation marks", SYSTEM_PROMPT)
        self.assertIn('print("hi")', SYSTEM_PROMPT)

    def test_grounding_rule_quotes_faulty_token(self) -> None:
        self.assertIn("quote the exact faulty token", SYSTEM_PROMPT)

    def test_uncertainty_caps_confidence(self) -> None:
        self.assertIn("below 0.5", SYSTEM_PROMPT)


class ErrorAnalysisServiceTests(unittest.TestCase):
    def test_mock_analysis_returns_structured_result(self) -> None:
        service = ErrorAnalysisService(AIService(provider=MockProvider(), is_live=False))
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="Python",
            error_type="NameError",
            error_message="name 'username' is not defined",
            file_path="main.py",
            line_number=12,
            relevant_code="print(username)",
            raw_context="NameError: name 'username' is not defined",
        )
        result = service.analyse(detected)
        self.assertEqual(result.error_type, "NameError")
        self.assertGreaterEqual(result.confidence, 0.8)
        self.assertFalse(result.is_fallback)

    def test_structured_instructions_reach_provider(self) -> None:
        seen: dict = {}

        class RecordingProvider:
            def reply(self, messages, model, instructions=None):
                seen["instructions"] = instructions
                seen["text"] = messages[0].text if messages else ""
                return '{"problem": "p", "error_type": "NameError", "explanation": "e", "cause": "c", "solution": "s", "corrected_code": "", "confidence": 0.9}'

        service = ErrorAnalysisService(AIService(provider=RecordingProvider(), is_live=False))  # type: ignore[arg-type]
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            error_type="NameError",
            raw_context="NameError: x",
        )
        result = service.analyse(detected)
        self.assertIn("JSON", seen["instructions"] or "")
        self.assertEqual(result.error_type, "NameError")

    def test_parser_handles_plain_text(self) -> None:
        result = parse_error_analysis("Just a plain explanation without JSON.")
        self.assertTrue(result.is_fallback)
        self.assertIn("plain", result.explanation.lower())

    def test_chat_still_works_without_instructions(self) -> None:
        service = AIService(provider=MockProvider(), is_live=False)
        reply = service.reply([ChatMessage("user", "hello")], "model")
        self.assertTrue(reply)


class AnalysisChipTests(unittest.TestCase):
    """Confidence chip stays hidden until a result (or failure) gives it text."""

    def test_chip_hidden_until_result(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from app.ai.response_parser import ErrorAnalysis
        from app.ui.analysis_panel import AnalysisPanel

        panel = AnalysisPanel()
        self.assertTrue(panel._confidence_chip.isHidden())
        self.assertTrue(panel._analyse_btn.isHidden())
        self.assertIn("Detect an error to see AI-powered analysis here", panel._status_label.text())
        panel._render_result(ErrorAnalysis(problem="p", error_type="NameError", confidence=0.95))
        self.assertFalse(panel._confidence_chip.isHidden())
        self.assertFalse(panel._analyse_btn.isHidden())
        self.assertIn("NameError", panel._confidence_chip.text())


class HistoryLabelTests(unittest.TestCase):
    """Stored history labels must not duplicate the language prefix."""

    def test_language_prefix_stripped_from_label(self) -> None:
        from unittest.mock import patch

        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from app.ai.response_parser import ErrorAnalysis
        from app.detection.models import DetectedError, DetectionCategory
        from app.ui.analysis_panel import AnalysisPanel

        panel = AnalysisPanel()
        detected = DetectedError(
            category=DetectionCategory.CONFIRMED_ERROR,
            language="JavaScript",
            error_type="SyntaxError",
            error_message="Invalid or unexpected token",
            file_path="testjs.js",
            line_number=1,
            relevant_code='console.log("Hello JS!)',
            raw_context="SyntaxError: Invalid or unexpected token",
        )
        panel._last_detected = detected
        # Model echoed the full line as error_type (observed live shape).
        result = ErrorAnalysis(
            problem="Invalid token",
            error_type="JavaScript Syntax Error",
            explanation="E.",
            confidence=0.5,
        )
        with (
            patch("app.core.session.session_store") as mock_store,
            patch("app.database.database.get_database", side_effect=RuntimeError("no db")),
        ):
            panel._on_succeeded(result)
            _, kwargs = mock_store.add_issue.call_args
        self.assertEqual(kwargs["error"], "Syntax Error: Invalid token")
        self.assertFalse(kwargs["error"].startswith("JavaScript JavaScript"))


if __name__ == "__main__":
    unittest.main()
