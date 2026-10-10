"""Application services: detection pipeline (Phase 7), notifications + companion (Phase 8)."""

from app.services.companion_service import get_companion_service
from app.services.detection_pipeline import get_detection_pipeline
from app.services.notification_service import get_notification_service
from app.services.settings_service import load_persisted_settings, save_persisted_settings

__all__ = [
    "get_companion_service",
    "get_detection_pipeline",
    "get_notification_service",
    "load_persisted_settings",
    "save_persisted_settings",
]
