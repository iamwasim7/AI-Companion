"""Primary application window with sidebar navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QStatusBar, QVBoxLayout, QWidget

from app.core.config import Config
from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state
from app.ui.chat_window import ChatPage
from app.ui.dashboard import DashboardPage
from app.ui.history_page import HistoryPage
from app.ui.monitoring_page import MonitoringPage
from app.ui.settings_page import SettingsPage
from app.ui.styles import apply_theme

logger = get_logger("ui.main_window")
_NAV_ITEMS = (("dashboard", "Dashboard"), ("chat", "Chat"), ("monitoring", "Monitoring"), ("history", "History"), ("settings", "Settings"))


class MainWindow(QMainWindow):
    companion_toggle_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(Config.APP_NAME)
        self.resize(1024, 700)
        self.setMinimumSize(820, 560)
        # Phase 9: load persisted UI preferences before building pages.
        try:
            from app.services.settings_service import load_persisted_settings

            load_persisted_settings()
        except Exception:
            logger.exception("Failed to load persisted settings")
        apply_theme(self, app_state.theme)
        root = QWidget()
        root.setObjectName("centralRoot")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self._stack = QStackedWidget()
        self._pages = {"dashboard": DashboardPage(), "chat": ChatPage(), "monitoring": MonitoringPage(), "history": HistoryPage(), "settings": SettingsPage()}
        for key, _label in _NAV_ITEMS:
            self._stack.addWidget(self._pages[key])
        layout.addWidget(self._stack, 1)
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        bus.subscribe("navigate", self._on_navigate)
        bus.subscribe("state.changed", self._refresh_status)
        bus.subscribe("theme.changed", self._apply_current_theme)
        # Phase 7/8: ensure background services listen before any frames/events.
        # The monitor service is bootstrapped here (not lazily by a page) so
        # Start Monitoring always has a live subscriber.
        try:
            from app.monitoring.monitor_service import get_monitor_service
            from app.services.companion_service import get_companion_service
            from app.services.detection_pipeline import get_detection_pipeline
            from app.services.notification_service import get_notification_service

            get_monitor_service()
            get_detection_pipeline()
            get_notification_service()
            get_companion_service()
        except Exception:
            logger.exception("Background services failed to start")
        self._refresh_status()
        self.navigate("dashboard")
        logger.info("Main window initialized")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(16, 20, 16, 16)
        column.setSpacing(8)
        title = QLabel(Config.APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel(f"v{Config.APP_VERSION}")
        subtitle.setObjectName("appSubtitle")
        column.addWidget(title)
        column.addWidget(subtitle)
        column.addSpacing(16)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        for index, (key, label) in enumerate(_NAV_ITEMS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("role", "nav")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, page=key: self.navigate(page))
            self._nav_group.addButton(button, index)
            self._nav_buttons[key] = button
            column.addWidget(button)
        column.addStretch(1)
        companion_button = QPushButton("Show / hide companion")
        companion_button.setProperty("role", "secondary")
        companion_button.clicked.connect(self.companion_toggle_requested.emit)
        column.addWidget(companion_button)
        return sidebar

    def _on_navigate(self, page: str, **_payload: object) -> None:
        self.navigate(page)

    def navigate(self, page_key: str) -> None:
        keys = [item[0] for item in _NAV_ITEMS]
        if page_key not in keys:
            return
        self._stack.setCurrentIndex(keys.index(page_key))
        self._nav_buttons[page_key].setChecked(True)
        logger.info("Navigated to %s", page_key)

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _refresh_status(self, **_payload: object) -> None:
        ai = "AI: Mock" if Config.is_mock_mode() else "AI: Live"
        self._status.showMessage(f"{app_state.monitoring_label()}    ·    {ai}")

    def _apply_current_theme(self, **_payload: object) -> None:
        apply_theme(self, app_state.theme)

    def refresh_status(self) -> None:
        self._refresh_status()
