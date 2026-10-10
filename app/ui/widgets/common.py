"""Small shared UI building blocks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def polish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class StatusChip(QLabel):
    def __init__(self, text: str, tone: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "chip")
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        polish(self)


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setObjectName("statusCard")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(8)


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel scrolling.

    Prevents accidental value changes when the user scrolls a page with the
    cursor resting over a dropdown; the ignored event propagates to the
    parent scroll area instead. Values change only via click/dropdown
    selection or keyboard.
    """

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class PageHeader(QWidget):
    def __init__(self, title: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        body = QLabel(hint)
        body.setObjectName("pageHint")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)


class MonitoringBanner(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monitoringBanner")
        self.sync_from_state()

    def sync_from_state(self) -> None:
        from app.core.state import app_state

        on = app_state.monitoring_enabled and not app_state.monitoring_paused
        self.setProperty("active", "true" if on else "false")
        self.setText(app_state.monitoring_label())
        polish(self)


def labeled_row(*widgets: QWidget) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    layout.addStretch(1)
    return row
