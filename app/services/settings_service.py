"""Phase 9 — Settings persistence: app_state <-> SQLite settings table.

API keys stay in ``.env`` and are never stored in SQLite (Master Spec §9).
Only UI preferences are persisted: theme, ai_model, ai_behavior,
history_retention_days (0 = keep forever), monitoring_interval_seconds,
detection_sensitivity, companion_size, companion_always_on_top,
companion_avatar.
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.core.state import app_state

logger = get_logger("services.settings")

_PERSISTED_KEYS = (
    "theme",
    "ai_model",
    "ai_behavior",
    "history_retention_days",
    "monitoring_interval_seconds",
    "detection_sensitivity",
    "companion_size",
    "companion_always_on_top",
    "companion_avatar",
)


def load_persisted_settings() -> None:
    """Override app_state defaults from SQLite (call once at startup)."""
    try:
        from app.database.database import get_database
        from app.database.repositories import SettingsRepository

        repo = SettingsRepository(get_database())
        stored = repo.all()
        if not stored:
            return
        if stored.get("theme") in {"dark", "light", "cursor", "midnight", "palenight", "vercel"}:
            app_state.theme = stored["theme"]
        if stored.get("ai_model"):
            app_state.ai_model = stored["ai_model"]
        if stored.get("ai_behavior") in {"beginner", "concise", "detailed"}:
            app_state.ai_behavior = stored["ai_behavior"]
        try:
            retention = int(stored.get("history_retention_days", ""))
            if 0 <= retention <= 365:
                app_state.history_retention_days = retention
        except (ValueError, TypeError):
            pass
        try:
            interval = int(stored.get("monitoring_interval_seconds", ""))
            if 1 <= interval <= 365:
                app_state.monitoring_interval_seconds = interval
        except (ValueError, TypeError):
            pass
        if stored.get("detection_sensitivity") in {"low", "medium", "high"}:
            app_state.detection_sensitivity = stored["detection_sensitivity"]
        try:
            size = int(stored.get("companion_size", ""))
            if 96 <= size <= 180:
                app_state.companion_size = size
        except (ValueError, TypeError):
            pass
        raw_top = stored.get("companion_always_on_top", "").strip().lower()
        if raw_top in {"1", "true", "yes", "on"}:
            app_state.companion_always_on_top = True
        elif raw_top in {"0", "false", "no", "off"}:
            app_state.companion_always_on_top = False
        from app.ui.companion import AVATARS

        if stored.get("companion_avatar") in AVATARS:
            app_state.companion_avatar = stored["companion_avatar"]
        logger.info("Loaded persisted settings (%d keys)", len(stored))
    except Exception:
        logger.exception("Failed to load persisted settings")


def save_persisted_settings() -> None:
    """Write current app_state preferences to SQLite (best-effort)."""
    try:
        from app.database.database import get_database
        from app.database.repositories import SettingsRepository

        repo = SettingsRepository(get_database())
        repo.set("theme", app_state.theme)
        repo.set("ai_model", app_state.ai_model)
        repo.set("ai_behavior", app_state.ai_behavior)
        repo.set("history_retention_days", str(app_state.history_retention_days))
        repo.set("monitoring_interval_seconds", str(app_state.monitoring_interval_seconds))
        repo.set("detection_sensitivity", app_state.detection_sensitivity)
        repo.set("companion_size", str(app_state.companion_size))
        repo.set("companion_always_on_top", "1" if app_state.companion_always_on_top else "0")
        repo.set("companion_avatar", app_state.companion_avatar)
    except Exception:
        logger.exception("Failed to save persisted settings")
