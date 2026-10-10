"""Chat bubbles with optional copyable code blocks."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_FENCE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)


def split_message_parts(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in _FENCE.finditer(text):
        if match.start() > cursor:
            stripped = text[cursor : match.start()].strip()
            if stripped:
                parts.append(("text", stripped))
        parts.append(("code", match.group(1).rstrip()))
        cursor = match.end()
    if cursor < len(text):
        remainder = text[cursor:].strip()
        if remainder:
            parts.append(("text", remainder))
    return parts or [("text", text)]


class CodeBlock(QFrame):
    def __init__(self, code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "code")
        self._code = code
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        label = QLabel("Code")
        label.setProperty("role", "muted")
        copy_btn = QPushButton("Copy")
        copy_btn.setProperty("role", "secondary")
        copy_btn.clicked.connect(self._copy)
        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(copy_btn)
        layout.addLayout(header)

        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(code)
        editor.setFont(QFont("Consolas", 11))
        line_count = max(1, code.count("\n") + 1)
        editor.setMinimumHeight(min(160, 28 + line_count * 18))
        editor.setMaximumHeight(220)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(editor)

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code)


class MessageBubble(QFrame):
    def __init__(self, role: str, text: str, *, is_error: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if is_error:
            self.setProperty("role", "bubble-error")
            caption = "Error"
        elif role == "user":
            self.setProperty("role", "bubble-user")
            caption = "You"
        else:
            self.setProperty("role", "bubble-assistant")
            caption = "Companion"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        title = QLabel(caption)
        title.setProperty("role", "muted")
        layout.addWidget(title)

        for kind, content in split_message_parts(text):
            if kind == "code":
                layout.addWidget(CodeBlock(content))
                continue
            body = QLabel(content)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(body)
