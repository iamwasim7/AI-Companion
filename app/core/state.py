"""Shared runtime state. Monitoring is always off until the user enables it."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import Config

COMPANION_STATES = ("IDLE", "THINKING", "ANALYZING", "ALERT", "RESPONDING", "ERROR")


@dataclass
class AppState:
    monitoring_enabled: bool = False
    monitoring_paused: bool = False
    monitoring_interval_seconds: int = 3
    detection_sensitivity: str = "medium"
    capture_region: str = "primary"
    store_screenshots: bool = False
    history_retention_days: int = 30
    monitor_frames_captured: int = 0
    monitor_changes_detected: int = 0
    monitor_last_change_score: float = 0.0
    monitor_last_capture_at: str = ""
    monitor_last_error: str = ""

    ocr_available: bool = field(default_factory=lambda: Config.is_ocr_available())
    ocr_last_extracted_length: int = 0
    ocr_last_confidence: float = 0.0
    ocr_last_error: str = ""

    last_detected_error: str = ""
    last_detected_category: str = "GENERAL CONTEXT"
    last_detected_language: str = "General"
    last_detected_at: str = ""

    companion_visible: bool = field(default_factory=lambda: Config.COMPANION_VISIBLE_DEFAULT)
    companion_always_on_top: bool = True
    companion_size: int = 128
    companion_avatar: str = "classic"
    companion_state: str = "IDLE"

    ai_connected: bool = False
    ai_model: str = ""
    ai_behavior: str = "beginner"
    theme: str = "dark"

    def monitoring_label(self) -> str:
        if not self.monitoring_enabled:
            return "Monitoring: Off"
        if self.monitoring_paused:
            return "Monitoring: Paused"
        return "Monitoring: On"

    def set_companion_state(self, state: str) -> None:
        if state in COMPANION_STATES:
            self.companion_state = state


app_state = AppState()