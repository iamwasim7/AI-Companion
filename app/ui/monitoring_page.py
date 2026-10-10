"""Opt-in local screen-monitoring controls and live capture status."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from app.core.config import Config
from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state
from app.monitoring.screen_capture import ScreenCapture
from app.ui.widgets.common import Card, MonitoringBanner, NoWheelComboBox, PageHeader, StatusChip, polish

logger = get_logger("ui.monitoring")


class MonitoringPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(PageHeader("Monitoring", "Screen capture is opt-in, local-only, and rate-limited. Significant changes run local Tesseract OCR + error detection; only concise error context is sent to AI, never screenshots."))
        self._banner = MonitoringBanner()
        layout.addWidget(self._banner)
        buttons = QHBoxLayout()
        self._toggle = QPushButton(); self._toggle.setProperty("role", "primary"); self._toggle.clicked.connect(self._toggle_monitoring)
        self._pause = QPushButton(); self._pause.setProperty("role", "secondary"); self._pause.clicked.connect(self._toggle_pause)
        self._ocr_chip = StatusChip("OCR: checking", "info")
        buttons.addWidget(self._toggle); buttons.addWidget(self._pause); buttons.addWidget(self._ocr_chip); buttons.addStretch(1)
        layout.addLayout(buttons)
        card = Card()
        card.body.addWidget(QLabel("Capture rate"))
        self._interval_value = QLabel()
        self._interval = QSlider(Qt.Orientation.Horizontal)
        self._interval.setRange(1, 10); self._interval.setValue(app_state.monitoring_interval_seconds); self._interval.valueChanged.connect(self._on_interval)
        card.body.addWidget(self._interval); card.body.addWidget(self._interval_value)
        card.body.addWidget(QLabel("Change sensitivity"))
        self._sensitivity = NoWheelComboBox(); self._sensitivity.addItems(["low", "medium", "high"]); self._sensitivity.setCurrentText(app_state.detection_sensitivity); self._sensitivity.currentTextChanged.connect(self._on_sensitivity)
        card.body.addWidget(self._sensitivity)
        card.body.addWidget(QLabel("Display to capture"))
        self._region = NoWheelComboBox(); self._region.currentIndexChanged.connect(self._on_region)
        card.body.addWidget(self._region)
        layout.addWidget(card)
        self._activity = QLabel(); self._activity.setWordWrap(True); self._activity.setProperty("role", "muted")
        layout.addWidget(self._activity)
        self._error = QLabel(); self._error.setObjectName("errorBanner"); self._error.hide(); layout.addWidget(self._error)
        privacy = QLabel("Privacy: capture starts only after you choose Start monitoring. Frames are held in memory only for local change comparison, are never written to disk, and are never sent to OpenAI. Only short extracted error text goes to AI after local detection.")
        privacy.setWordWrap(True); privacy.setProperty("role", "muted")
        layout.addWidget(privacy); layout.addStretch(1)
        self._populate_screens()
        bus.subscribe("state.changed", self.refresh)
        bus.subscribe("monitoring.capture_error", self._on_capture_error)
        self.refresh()

    def _populate_screens(self) -> None:
        self._region.blockSignals(True)
        self._region.clear()
        for descriptor in ScreenCapture.available_screens():
            self._region.addItem(descriptor.label, descriptor.key)
        index = self._region.findData(app_state.capture_region)
        self._region.setCurrentIndex(index if index >= 0 else 0)
        if self._region.currentIndex() >= 0:
            app_state.capture_region = str(self._region.currentData())
        self._region.blockSignals(False)

    def refresh(self, **_payload: object) -> None:
        enabled, paused = app_state.monitoring_enabled, app_state.monitoring_paused
        self._banner.sync_from_state()
        self._toggle.setText("Stop monitoring" if enabled else "Start monitoring")
        self._pause.setEnabled(enabled); self._pause.setText("Resume" if paused else "Pause")
        self._interval_value.setText(f"Every {app_state.monitoring_interval_seconds} second(s) · one local frame maximum per interval")
        captured = f"Frames in this run: {app_state.monitor_frames_captured}. Significant changes: {app_state.monitor_changes_detected}."
        if app_state.monitor_last_capture_at:
            captured += f" Last capture: {app_state.monitor_last_capture_at}. Score: {app_state.monitor_last_change_score:.3f}."
        self._activity.setText(captured)
        self._error.setVisible(bool(app_state.monitor_last_error))
        self._error.setText(app_state.monitor_last_error)
        self._ocr_chip.setText(f"OCR: {Config.ocr_status_label()}")
        self._ocr_chip.set_tone("ok" if Config.is_ocr_available() else "warn")
        polish(self._banner)

    def _toggle_monitoring(self) -> None:
        bus.emit("monitoring.stop" if app_state.monitoring_enabled else "monitoring.start")

    def _toggle_pause(self) -> None:
        if app_state.monitoring_enabled:
            bus.emit("monitoring.resume" if app_state.monitoring_paused else "monitoring.pause")

    def set_enabled(self, enabled: bool) -> None:
        bus.emit("monitoring.start" if enabled else "monitoring.stop")

    def _on_interval(self, value: int) -> None:
        app_state.monitoring_interval_seconds = value
        bus.emit("monitoring.interval_changed")
        bus.emit("state.changed")
        try:
            from app.services.settings_service import save_persisted_settings

            save_persisted_settings()
        except Exception:
            pass

    def _on_sensitivity(self, value: str) -> None:
        app_state.detection_sensitivity = value
        bus.emit("state.changed")
        try:
            from app.services.settings_service import save_persisted_settings

            save_persisted_settings()
        except Exception:
            pass

    def _on_region(self) -> None:
        if self._region.currentIndex() >= 0:
            app_state.capture_region = str(self._region.currentData())
            bus.emit("state.changed")

    def _on_capture_error(self, message: str, **_payload: object) -> None:
        logger.warning("Capture UI error shown: %s", type(message).__name__)
        self.refresh()
