"""Persistent issue history (Phase 9, SQLite-backed)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.events import bus
from app.core.logger import get_logger
from app.core.session import session_store
from app.ui.widgets.common import PageHeader

logger = get_logger("ui.history")


class HistoryPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(PageHeader("History", "Detected errors persist locally in SQLite. Screenshots are never stored."))
        actions = QHBoxLayout()
        self._count = QLabel()
        self._count.setProperty("role", "muted")
        delete_btn = QPushButton("Delete selected")
        delete_btn.setProperty("role", "secondary")
        delete_btn.clicked.connect(self._delete_selected)
        clear = QPushButton("Clear history")
        clear.setProperty("role", "danger")
        clear.clicked.connect(session_store.clear_issues)
        actions.addWidget(self._count)
        actions.addStretch(1)
        actions.addWidget(delete_btn)
        actions.addWidget(clear)
        layout.addLayout(actions)
        columns = QHBoxLayout()
        self._list = QListWidget()
        self._list.setMinimumWidth(290)
        self._list.currentItemChanged.connect(self._select_issue)
        columns.addWidget(self._list, 1)
        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setPlaceholderText("Select an issue to read its explanation and suggested fix.")
        columns.addWidget(self._details, 2)
        layout.addLayout(columns, 1)
        bus.subscribe("history.changed", self.refresh)
        self.refresh()

    def refresh(self, **_payload: object) -> None:
        current_item = self._list.currentItem()
        previous = current_item.data(Qt.ItemDataRole.UserRole) if current_item else None
        self._list.blockSignals(True)
        self._list.clear()
        for issue in session_store.issues:
            item = QListWidgetItem(f"{issue.language} · {issue.error}")
            item.setData(Qt.ItemDataRole.UserRole, issue.id)
            item.setToolTip(issue.created_at.strftime("%d %b %Y, %H:%M"))
            self._list.addItem(item)
            if issue.id == previous:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._count.setText(f"{len(session_store.issues)} issue(s) stored locally")
        if self._list.count() and self._list.currentItem() is None:
            self._list.setCurrentRow(0)
        if not self._list.count():
            self._details.clear()

    def _delete_selected(self) -> None:
        current = self._list.currentItem()
        if current is None:
            return
        try:
            session_store.delete_issue(int(current.data(Qt.ItemDataRole.UserRole)))
            logger.info("Deleted history issue")
        except Exception:
            logger.exception("Failed to delete history issue")

    def _select_issue(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self._details.clear()
            return
        issue = session_store.get_issue(int(current.data(Qt.ItemDataRole.UserRole)))
        if issue is not None:
            self._details.setPlainText(f"{issue.language} issue\nDetected: {issue.created_at.strftime('%d %b %Y, %H:%M')}\n\nError\n{issue.error}\n\nWhat it means\n{issue.explanation}\n\nSuggested solution\n{issue.solution}")
