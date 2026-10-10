"""Phase 10 — Integration: detection → mock analysis → history → notification.

No network, no API key, temp SQLite file. Proves the Phase 7/8/9 wiring
works as one system, not just isolated units.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


def _temp_db() -> str:
    import os

    fd, path = tempfile.mkstemp(prefix="ai_companion_int_", suffix=".db")
    os.close(fd)
    return path


SAMPLE_TRACEBACK = (
    'Traceback (most recent call last):\n'
    '  File "main.py", line 12, in <module>\n'
    "    print(username)\n"
    "NameError: name 'username' is not defined"
)


class EndToEndMockFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.core.state import app_state

        self._old_retention = app_state.history_retention_days
        app_state.history_retention_days = 30
        self._path = _temp_db()
        from app.core.config import Config

        self._old_db_path = Config.DB_PATH
        Config.DB_PATH = Path(self._path)
        from app.database.database import reset_database
        from app.core.session import reset_session_store

        reset_database(self._path)
        self.store = reset_session_store(self._path)
        from app.services.notification_service import NotificationPolicy, NotificationService

        self.notifier = NotificationService(policy=NotificationPolicy(0, 0))
        self._bus_handlers: list[tuple[str, object]] = []

    def tearDown(self) -> None:
        from app.core.config import Config
        from app.core.events import bus
        from app.core.state import app_state
        from app.database.database import reset_database
        from app.core.session import reset_session_store
        from app.services import notification_service as ns_mod

        for event, handler in self._bus_handlers:
            try:
                bus.unsubscribe(event, handler)  # type: ignore[arg-type]
            except Exception:
                pass
        app_state.history_retention_days = self._old_retention
        Config.DB_PATH = self._old_db_path
        reset_database(self._old_db_path)
        reset_session_store(self._old_db_path)
        ns_mod._service = None
        try:
            Path(self._path).unlink(missing_ok=True)
        except Exception:
            pass

    def _capture(self, event: str, sink: list) -> None:
        from app.core.events import bus

        def _handler(**payload: object) -> None:
            sink.append(payload)

        bus.subscribe(event, _handler)
        self._bus_handlers.append((event, _handler))

    def test_full_flow_creates_history_and_notification(self) -> None:
        from app.ai.error_analysis_service import ErrorAnalysisService
        from app.core.ai_service import AIService, MockProvider
        from app.core.events import bus
        from app.detection.error_detector import get_error_detector

        analysis_done: list = []
        detection_seen: list = []
        self._capture("analysis.completed", analysis_done)
        self._capture("detection.updated", detection_seen)

        detected = get_error_detector().detect(SAMPLE_TRACEBACK)
        self.assertTrue(detected.has_error)
        bus.emit("detection.updated", detected=detected)

        service = ErrorAnalysisService(AIService(provider=MockProvider(), is_live=False))
        result = service.analyse(detected)
        self.assertEqual(result.error_type, "NameError")
        self.assertFalse(result.is_fallback)

        # Same persistence path as AnalysisPanel._on_succeeded.
        self.store.add_issue(
            language=detected.language,
            error=f"{result.error_type}: {result.problem}"[:300],
            explanation=result.explanation or result.problem,
            solution=result.solution,
            error_type=result.error_type,
            category=detected.category.value,
            file_path=detected.file_path,
            line_number=detected.line_number,
            confidence=result.confidence,
        )
        bus.emit("analysis.completed", result=result, detected=detected)

        self.assertTrue(detection_seen)
        self.assertEqual(len(self.store.issues), 1)  # fresh store starts empty; 1 new issue
        self.assertEqual(len(self.notifier.active), 1)
        self.assertIn("NameError", self.notifier.active[0].title)
        self.assertTrue(analysis_done)

    def test_general_context_produces_no_notification(self) -> None:
        from app.ai.error_analysis_service import ErrorAnalysisService
        from app.core.ai_service import AIService, MockProvider
        from app.core.events import bus
        from app.detection.error_detector import get_error_detector

        detected = get_error_detector().detect("def add(a, b):\n    return a + b")
        self.assertFalse(detected.has_error)
        service = ErrorAnalysisService(AIService(provider=MockProvider(), is_live=False))
        result = service.analyse(detected)
        bus.emit("analysis.completed", result=result, detected=detected)
        self.assertEqual(len(self.notifier.active), 0)

    def test_pipeline_analyse_text_entry(self) -> None:
        from app.services.detection_pipeline import DetectionPipeline

        seen: list = []
        self._capture("detection.updated", seen)
        self._capture("analysis.run", seen)
        pipeline = DetectionPipeline()
        try:
            detected = pipeline.analyse_text(SAMPLE_TRACEBACK)
        finally:
            # Unsubscribe the pipeline from global bus to avoid cross-test events.
            from app.core.events import bus as b2

            for handler in list(b2._subscribers.get("monitoring.frame_changed", [])):
                try:
                    b2.unsubscribe("monitoring.frame_changed", handler)
                except Exception:
                    pass
            for handler in list(b2._subscribers.get("monitoring.stop", [])):
                try:
                    b2.unsubscribe("monitoring.stop", handler)
                except Exception:
                    pass
        self.assertTrue(detected.has_error)
        self.assertTrue(seen)


if __name__ == "__main__":
    unittest.main()
