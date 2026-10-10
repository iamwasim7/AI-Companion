"""Headless smoke test: construct the UI and exercise key Phase 7/8/9 paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.logger import setup_logging
from app.core.config import Config
from app.ui.companion import FloatingCompanion
from app.ui.main_window import MainWindow


def main() -> int:
    # Never make a paid or network request from the UI smoke test.
    Config.AI_MODE = "mock"
    setup_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    companion = FloatingCompanion()
    window.show()
    companion.show()
    window.navigate("chat")
    chat = window._pages["chat"]
    chat.submit_user_message("Explain a Python NameError", delay_ms=1)
    window.navigate("monitoring")
    window._pages["monitoring"].set_enabled(True)
    window.navigate("history")
    window.navigate("settings")
    window.navigate("dashboard")
    # Phase 8/9: simulate a detection (mock analysis runs off-thread),
    # prefill chat via companion Ask-AI path, and touch history selection.
    dashboard = window._pages["dashboard"]
    dashboard._simulate_detection()
    chat._on_prefill(text="Smoke prefill: explain NameError")
    assert chat._input.toPlainText().startswith("Smoke prefill")
    history = window._pages["history"]
    history.refresh()
    if history._list.count():
        history._list.setCurrentRow(0)
    QTimer.singleShot(2500, app.quit)  # allow mock analysis + notification to land
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
