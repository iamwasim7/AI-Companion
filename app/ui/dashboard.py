"""Dashboard with status, mock recent activity, and quick actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.events import bus
from app.core.logger import get_logger
from app.core.session import session_store
from app.core.state import app_state
from app.ui.analysis_panel import AnalysisPanel
from app.ui.widgets.common import Card, PageHeader, StatusChip, labeled_row

logger = get_logger("ui.dashboard")


class DashboardPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        inner = QWidget()
        inner.setObjectName("scrollInner")
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(28, 24, 28, 24)
        self._layout.setSpacing(16)

        self._layout.addWidget(
            PageHeader(
                "Dashboard",
                "Status and recent activity.",
            )
        )

        self._ai_chip = StatusChip("AI", "info")
        self._monitor_chip = StatusChip("Monitoring", "off")
        self._companion_chip = StatusChip("Companion", "info")
        self._layout.addWidget(labeled_row(self._ai_chip, self._monitor_chip, self._companion_chip))

        actions = QHBoxLayout()
        start = QPushButton("Start monitoring")
        start.setProperty("role", "primary")
        start.clicked.connect(self._start_monitoring)
        chat = QPushButton("Open chat")
        chat.setProperty("role", "secondary")
        chat.clicked.connect(lambda: bus.emit("navigate", page="chat"))
        actions.addWidget(start)
        actions.addWidget(chat)
        actions.addStretch(1)
        self._layout.addLayout(actions)

        self._issues_card = Card()
        self._layout.addWidget(self._issues_card)
        self._notif_card = Card()
        self._layout.addWidget(self._notif_card)
        self._analysis_card = Card()
        self._analysis_panel = AnalysisPanel()
        self._analysis_card.body.addWidget(self._analysis_panel)
        self._layout.addWidget(self._analysis_card)
        self._chat_card = Card()
        self._layout.addWidget(self._chat_card)
        self._layout.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        bus.subscribe("state.changed", self.refresh)
        bus.subscribe("history.changed", self.refresh)
        bus.subscribe("chat.changed", self.refresh)
        bus.subscribe("notifications.changed", self.refresh)
        self.refresh()

    def refresh(self, **_payload: object) -> None:
        mock = Config.is_mock_mode()
        key_status = "Configured" if Config.api_key_status_label().lower() == "configured" else "Not Configured"
        if mock:
            ai_label = f"AI: Mock Mode · Key {key_status}"
        else:
            ai_label = f"AI: Live · Key {key_status}"
        self._ai_chip.setText(ai_label)
        self._ai_chip.set_tone("warn" if mock else "ok")
        self._monitor_chip.setText(app_state.monitoring_label())
        self._monitor_chip.set_tone("ok" if app_state.monitoring_enabled and not app_state.monitoring_paused else "off")
        self._companion_chip.setText(
            f"Companion: {app_state.companion_state.capitalize()} · "
            f"{'Visible' if app_state.companion_visible else 'Hidden'}"
        )
        self._companion_chip.set_tone("ok" if app_state.companion_visible else "off")
        self._fill_issues()
        self._fill_notifications()
        self._fill_conversations()

    def _clear_card(self, card: Card, title: str) -> None:
        while card.body.count():
            item = card.body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 700;")
        card.body.addWidget(heading)

    def _fill_issues(self) -> None:
        self._clear_card(self._issues_card, "Recent issues")
        if not session_store.issues:
            empty = QLabel("No detected issues yet.")
            empty.setProperty("role", "muted")
            self._issues_card.body.addWidget(empty)
            return
        for issue in session_store.issues[:4]:
            line = QLabel(f"{issue.language} · {issue.error}")
            line.setWordWrap(True)
            self._issues_card.body.addWidget(line)

    def _fill_notifications(self) -> None:
        from app.services.notification_service import get_notification_service

        self._clear_card(self._notif_card, "Notifications")
        try:
            active = list(get_notification_service().active)
        except Exception:
            active = []
        if not active:
            empty = QLabel("No alerts. When an error is analysed you will see View / Ask AI / Ignore actions here and on the companion.")
            empty.setWordWrap(True)
            empty.setProperty("role", "muted")
            self._notif_card.body.addWidget(empty)
            return
        for item in active[:3]:
            row = QHBoxLayout()
            label = QLabel(f"{item.title} — {item.body[:120]}")
            label.setWordWrap(True)
            row.addWidget(label, 1)
            view_btn = QPushButton("View")
            view_btn.setProperty("role", "secondary")
            view_btn.setMinimumHeight(28)
            view_btn.setFixedWidth(84)
            view_btn.clicked.connect(self._view_notification)
            dismiss_btn = QPushButton("Dismiss")
            dismiss_btn.setProperty("role", "secondary")
            dismiss_btn.setMinimumHeight(28)
            dismiss_btn.setFixedWidth(84)
            dismiss_btn.clicked.connect(lambda _c=False, nid=item.id: self._dismiss_notification(nid))
            row.addWidget(view_btn)
            row.addWidget(dismiss_btn)
            wrapper = QWidget()
            wrapper.setLayout(row)
            self._notif_card.body.addWidget(wrapper)

    def _view_notification(self) -> None:
        """Scroll the Dashboard to the AI Error Analysis card.

        The analysis for a detected error renders here, so View brings it
        into sight instead of navigating away and back.
        """
        try:
            self._scroll.ensureWidgetVisible(self._analysis_card)
        except Exception:
            logger.exception("Failed to scroll to analysis card")

    def _dismiss_notification(self, notification_id: int) -> None:
        try:
            from app.services.notification_service import get_notification_service

            get_notification_service().dismiss(notification_id)
        except Exception:
            logger.exception("Failed to dismiss notification")

    def _fill_conversations(self) -> None:
        self._clear_card(self._chat_card, "Recent conversations")
        previews = session_store.recent_user_previews()
        if not previews:
            empty = QLabel("No user messages yet. Open chat to start.")
            empty.setProperty("role", "muted")
            self._chat_card.body.addWidget(empty)
            return
        for message in previews:
            line = QLabel(message.text)
            line.setWordWrap(True)
            self._chat_card.body.addWidget(line)

    def _start_monitoring(self) -> None:
        bus.emit("monitoring.start")
        logger.info("Monitoring requested from dashboard")
        bus.emit("navigate", page="monitoring")

    def _simulate_detection(self) -> None:
        # Retained for headless smoke tests (tests/smoke_launch.py); there is
        # intentionally no visible button for this in the normal UI.
        from datetime import datetime

        from app.detection.error_detector import get_error_detector

        sample = (
            'Traceback (most recent call last):\n'
            '  File "main.py", line 12, in <module>\n'
            "    print(username)\n"
            "NameError: name 'username' is not defined"
        )
        detected = get_error_detector().detect(sample)
        app_state.last_detected_error = detected.display_title
        app_state.last_detected_category = detected.category.value
        app_state.last_detected_language = detected.language
        app_state.last_detected_at = datetime.now().strftime("%H:%M:%S")
        app_state.set_companion_state("ALERT")
        bus.emit("companion.state", state="ALERT")
        bus.emit("detection.updated", detected=detected)
        bus.emit("analysis.run", detected=detected)
        bus.emit("state.changed")
        logger.info("Simulated error detection for UI preview (Phase 7 pipeline)")
