"""Chat UI backed by an off-thread mock or OpenAI provider."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.core.ai_service import AIService, AIServiceError
from app.core.ai_worker import AIRequestWorker
from app.core.config import Config
from app.core.events import bus
from app.core.logger import get_logger
from app.core.session import session_store
from app.core.state import app_state
from app.ui.widgets.chat_widgets import MessageBubble
from app.ui.widgets.common import PageHeader

logger = get_logger("ui.chat")


class ChatPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(12)
        header_row = QHBoxLayout()
        header_row.addWidget(PageHeader("Chat", "Mock mode runs locally. Live mode sends recent conversation text to the configured AI provider."), 1)
        clear_btn = QPushButton("Clear conversation")
        clear_btn.setProperty("role", "danger")
        clear_btn.clicked.connect(self.clear_conversation)
        header_row.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._inner.setObjectName("scrollInner")
        self._messages_layout = QVBoxLayout(self._inner)
        self._messages_layout.setContentsMargins(4, 4, 4, 4)
        self._messages_layout.setSpacing(10)
        self._messages_layout.addStretch(1)
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll, 1)
        self._error = QLabel("")
        self._error.setObjectName("errorBanner")
        self._error.hide()
        layout.addWidget(self._error)
        composer = QHBoxLayout()
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("Ask a follow-up question…")
        self._input.setFixedHeight(72)
        self._send = QPushButton("Send")
        self._send.setProperty("role", "primary")
        self._send.clicked.connect(self.send_current)
        composer.addWidget(self._input, 1)
        composer.addWidget(self._send, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(composer)
        self._loading: QLabel | None = None
        self._worker: AIRequestWorker | None = None
        self._rebuild()
        bus.subscribe("chat.changed", self._on_store_changed)
        bus.subscribe("chat.prefill", self._on_prefill)

    def _on_prefill(self, text: str = "", **_payload: object) -> None:
        if text:
            self._input.setPlainText(text[:800])
            self._input.setFocus()

    def _on_store_changed(self, **_payload: object) -> None:
        if self._loading is None:
            self._rebuild()

    def _rebuild(self) -> None:
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for message in session_store.messages:
            self._messages_layout.insertWidget(self._messages_layout.count() - 1, MessageBubble(message.role, message.text, is_error=message.is_error))
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_error(self, text: str | None) -> None:
        self._error.setText(text or "")
        self._error.setVisible(bool(text))

    def send_current(self) -> None:
        self.submit_user_message(self._input.toPlainText())

    def submit_user_message(self, text: str, delay_ms: int = 0) -> None:
        del delay_ms  # Preserves the Phase 2 smoke-test signature.
        message = text.strip()
        if not message or self._worker is not None:
            return
        self._set_error(None)
        self._input.clear()
        session_store.add_message("user", message)
        self._rebuild()
        self._send.setEnabled(False)
        self._loading = QLabel("Companion is thinking…")
        self._loading.setProperty("role", "muted")
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, self._loading)
        app_state.set_companion_state("THINKING")
        bus.emit("companion.state", state="THINKING")
        bus.emit("state.changed")
        try:
            service = AIService.from_config()
        except AIServiceError as exc:
            self._deliver_error(str(exc))
            return
        self._worker = AIRequestWorker(service, list(session_store.messages), Config.effective_model(app_state.ai_model))
        self._worker.succeeded.connect(self._deliver_reply)
        self._worker.failed.connect(self._deliver_error)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()
        logger.info("AI chat request queued (mode=%s)", "live" if service.is_live else "mock")

    def _finish_loading(self) -> None:
        if self._loading is not None:
            self._loading.deleteLater()
            self._loading = None

    def _deliver_reply(self, reply: str) -> None:
        self._finish_loading()
        session_store.add_message("assistant", reply)
        self._set_error(None)
        app_state.ai_connected = not Config.is_mock_mode()
        app_state.set_companion_state("RESPONDING")
        bus.emit("companion.state", state="RESPONDING")
        self._send.setEnabled(True)
        self._rebuild()
        bus.emit("state.changed")
        QTimer.singleShot(1600, self._return_idle)

    def _deliver_error(self, message: str) -> None:
        self._finish_loading()
        session_store.add_message("assistant", message, is_error=True)
        self._set_error(message)
        app_state.ai_connected = False
        app_state.set_companion_state("ERROR")
        bus.emit("companion.state", state="ERROR")
        self._send.setEnabled(True)
        self._rebuild()
        bus.emit("state.changed")
        QTimer.singleShot(1600, self._return_idle)
        logger.info("AI chat returned a safe error state")

    def _worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _return_idle(self) -> None:
        if app_state.companion_state in {"RESPONDING", "ERROR"}:
            app_state.set_companion_state("IDLE")
            bus.emit("companion.state", state="IDLE")
            bus.emit("state.changed")

    def clear_conversation(self) -> None:
        if self._worker is None:
            session_store.clear_messages()
            self._set_error(None)
            self._rebuild()
            logger.info("Conversation cleared")
