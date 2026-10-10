"""Lifecycle-managed, opt-in monitor that captures local frames at a bounded rate."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage

from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state
from app.monitoring.change_detector import ChangeDetector
from app.monitoring.screen_capture import ScreenCapture, ScreenCaptureError

logger = get_logger("monitoring.service")


class MonitorService(QObject):
    """Captures only after explicit start; pause/stop immediately release the timer."""

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._capture_tick)
        self._detector = ChangeDetector()
        bus.subscribe("monitoring.start", self.start)
        bus.subscribe("monitoring.stop", self.stop)
        bus.subscribe("monitoring.pause", self.pause)
        bus.subscribe("monitoring.resume", self.resume)
        bus.subscribe("monitoring.interval_changed", self._apply_interval)

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self, **_payload: object) -> None:
        if app_state.monitoring_enabled and not app_state.monitoring_paused:
            return
        app_state.monitoring_enabled = True
        app_state.monitoring_paused = False
        app_state.monitor_last_error = ""
        app_state.monitor_frames_captured = 0
        app_state.monitor_changes_detected = 0
        app_state.monitor_last_change_score = 0.0
        self._detector.reset()
        self._apply_interval()
        # Silent baseline: the first frame calibrates the change detector but
        # never triggers OCR. Otherwise monitoring would instantly "detect"
        # whatever is on screen at startup -- usually our own window.
        self._capture_tick(silent=True)
        logger.info("Monitoring started (local capture only, interval=%ss)", app_state.monitoring_interval_seconds)
        bus.emit("state.changed")

    def stop(self, **_payload: object) -> None:
        self._timer.stop()
        app_state.monitoring_enabled = False
        app_state.monitoring_paused = False
        self._detector.reset()
        logger.info("Monitoring stopped")
        bus.emit("state.changed")

    def pause(self, **_payload: object) -> None:
        if not app_state.monitoring_enabled:
            return
        self._timer.stop()
        app_state.monitoring_paused = True
        logger.info("Monitoring paused")
        bus.emit("state.changed")

    def resume(self, **_payload: object) -> None:
        if not app_state.monitoring_enabled:
            return
        app_state.monitoring_paused = False
        self._apply_interval()
        logger.info("Monitoring resumed")
        bus.emit("state.changed")

    def _apply_interval(self, **_payload: object) -> None:
        if app_state.monitoring_enabled and not app_state.monitoring_paused:
            self._timer.start(max(1, app_state.monitoring_interval_seconds) * 1000)

    def _capture_tick(self, *, silent: bool = False) -> None:
        if not app_state.monitoring_enabled or app_state.monitoring_paused:
            return
        try:
            frame = ScreenCapture.capture(app_state.capture_region)
        except ScreenCaptureError as exc:
            app_state.monitor_last_error = str(exc)
            logger.warning("Screen capture unavailable: %s", type(exc).__name__)
            bus.emit("monitoring.capture_error", message=str(exc))
            bus.emit("state.changed")
            return
        app_state.monitor_frames_captured += 1
        app_state.monitor_last_capture_at = datetime.now().strftime("%H:%M:%S")
        result = self._detector.compare(frame, app_state.detection_sensitivity)
        app_state.monitor_last_change_score = result.score
        if result.changed and not silent:
            app_state.monitor_changes_detected += 1
            bus.emit(
                "monitoring.frame_changed",
                frame=frame,
                score=result.score,
                frame_size=(frame.width(), frame.height()),
            )
        bus.emit("monitoring.frame_captured", frame_size=(frame.width(), frame.height()))
        bus.emit("state.changed")


_service: MonitorService | None = None


def get_monitor_service() -> MonitorService:
    global _service
    if _service is None:
        _service = MonitorService()
    return _service
