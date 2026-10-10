"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication

from app.core.config import Config
from app.core.events import bus
from app.core.logger import get_logger, setup_logging
from app.core.state import app_state
from app.ui.companion import FloatingCompanion
from app.ui.main_window import MainWindow


def _center_on_screen(window: MainWindow) -> None:
    """Move *window* to the centre of the primary screen."""
    screen: QScreen | None = QApplication.primaryScreen()
    if screen is None:
        return
    geom = screen.availableGeometry()
    x = geom.x() + (geom.width() - window.width()) // 2
    y = geom.y() + (geom.height() - window.height()) // 2
    window.move(x, y)


def main() -> int:
    setup_logging()
    logger = get_logger("main")
    logger.info("Starting %s v%s (AI_MODE=%s)", Config.APP_NAME, Config.APP_VERSION, Config.AI_MODE)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(Config.APP_NAME)
    app.setOrganizationName(Config.ORGANIZATION)

    window = MainWindow()
    companion = FloatingCompanion()

    # Phase 9: retention purge + startup event (best-effort, never blocks UI).
    try:
        from app.core.session import session_store

        removed = session_store.purge_expired()
        if removed:
            logger.info("Purged %d expired history record(s)", removed)
        from app.database.database import get_database
        from app.database.repositories import EventRepository

        EventRepository(get_database()).log("app.startup", f"{Config.APP_NAME} v{Config.APP_VERSION}")
    except Exception:
        logger.exception("Startup persistence step failed")

    def show_main() -> None:
        window.show_and_raise()

    def toggle_companion() -> None:
        if companion.isVisible():
            companion.hide()
            app_state.companion_visible = False
            logger.info("Companion hidden")
        else:
            companion.show()
            app_state.companion_visible = True
            logger.info("Companion shown")
        window.refresh_status()
        bus.emit("state.changed")  # refresh Dashboard chips, not just the status bar

    companion.open_main_requested.connect(show_main)
    companion.closed.connect(window.refresh_status)
    window.companion_toggle_requested.connect(toggle_companion)

    _center_on_screen(window)
    window.show()
    window.raise_()
    window.activateWindow()

    # On Windows, force the window to the foreground if launched from a console
    try:
        import ctypes
        hwnd = int(window.winId())
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

    if app_state.companion_visible:
        companion.show()
        # Place companion at the right edge of the main window
        companion.move(window.x() + window.width() - 40, window.y() + 80)

    logger.info("UI ready")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
