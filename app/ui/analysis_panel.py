"""Analysis panel widget — shows structured AI error analysis results.

Displayed on the Dashboard whenever an error is detected (or on demand).
Fires an ``ErrorAnalysisWorker`` QThread; renders a rich card with confidence
indicator, explanation, cause/solution sections, and an optional code block.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ai.error_analysis_service import (
    ErrorAnalysisService,
    ErrorAnalysisWorker,
    reset_error_analysis_service,
    get_error_analysis_service,
)
from app.ai.response_parser import ErrorAnalysis
from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state
from app.detection.models import DetectedError, DetectionCategory
from app.ui.styles import DARK, THEMES
from app.ui.widgets.common import StatusChip

logger = get_logger("ui.analysis_panel")


def _current_palette() -> dict:
    """Return the palette for the active theme (falls back to dark)."""
    try:
        return THEMES.get(app_state.theme, DARK)
    except Exception:
        return DARK

# ── Tone mapping for detection categories ─────────────────────────────────────
_CATEGORY_TONE = {
    DetectionCategory.CONFIRMED_ERROR: "error",
    DetectionCategory.POSSIBLE_ERROR: "warn",
    DetectionCategory.GENERAL_CONTEXT: "info",
}


class _CodeBlock(QFrame):
    """Monospace code display with a theme-aware background."""

    def __init__(self, code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("codeBlock")
        self._code = code
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        header = QHBoxLayout()
        self._caption = QLabel("Corrected code")
        copy_btn = QPushButton("Copy")
        copy_btn.setProperty("role", "secondary")
        copy_btn.setMinimumHeight(26)
        copy_btn.clicked.connect(self._copy)
        header.addWidget(self._caption)
        header.addStretch(1)
        header.addWidget(copy_btn)
        layout.addLayout(header)
        self._label = QLabel(code)
        self._label.setObjectName("codeLabel")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        t = _current_palette()
        self.setStyleSheet(
            "QFrame#codeBlock {"
            f"  background:{t['input_bg']}; border:1px solid {t['border']};"
            "  border-radius:6px; padding:10px;"
            "}"
        )
        self._caption.setStyleSheet(f"color: {t['muted']}; font-size: 11px;")
        self._label.setStyleSheet(
            "QLabel#codeLabel { font-family: Consolas, 'Courier New', monospace;"
            f"  font-size: 12px; color: {t['text']}; }}"
        )

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code)


class _SectionLabel(QLabel):
    """Bold section heading inside the analysis card."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        t = _current_palette()
        self.setStyleSheet(f"font-weight: 600; color: {t['title']}; margin-top: 8px;")


class _BodyLabel(QLabel):
    """Wrapping body text for explanations and solutions."""

    def __init__(self, text: str, parent: QWidget | None = None, tone: str = "muted") -> None:
        super().__init__(text, parent)
        self._tone = tone
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        t = _current_palette()
        if self._tone == "strong":
            self.setStyleSheet(
                f"color: {t['title']}; font-weight: 500; font-size: 13px;"
            )
        elif self._tone == "warn":
            self.setStyleSheet(f"color: {t['warn_fg']}; font-size: 11px;")
        else:
            self.setStyleSheet(f"color: {t['muted']}; line-height: 1.5;")


# ── Main panel ────────────────────────────────────────────────────────────────

class AnalysisPanel(QWidget):
    """Collapsible card showing AI-generated error analysis.

    Usage
    -----
    * Call ``analyse(detected)`` to trigger a new analysis from code.
    * The panel subscribes to ``"analysis.run"`` bus events so other parts of
      the app can request analysis without importing this widget directly.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: ErrorAnalysisWorker | None = None
        self._last_detected: DetectedError | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header row ────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 8)

        self._title = QLabel("AI Error Analysis")
        header.addWidget(self._title, 1)

        self._confidence_chip = StatusChip("", "off")
        self._confidence_chip.hide()  # empty chip looks like a stray red box; show on first result
        header.addWidget(self._confidence_chip)

        self._analyse_btn = QPushButton("Analyse again")
        self._analyse_btn.setProperty("role", "secondary")
        self._analyse_btn.setMinimumHeight(28)
        self._analyse_btn.clicked.connect(self._reanalyse)
        self._analyse_btn.hide()  # nothing to re-analyse until the first result lands
        header.addWidget(self._analyse_btn)

        root.addLayout(header)

        # ── Status / loading label ────────────────────────────────────────────
        self._status_label = QLabel("No analysis yet. Detect an error to see AI-powered analysis here.")
        self._status_label.setProperty("role", "muted")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        # ── Separator ─────────────────────────────────────────────────────────
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(self._sep)

        # ── Result area ───────────────────────────────────────────────────────
        self._result_area = QWidget()
        self._result_layout = QVBoxLayout(self._result_area)
        self._result_layout.setContentsMargins(0, 8, 0, 0)
        self._result_layout.setSpacing(4)
        root.addWidget(self._result_area)
        self._result_area.hide()

        # ── Bus subscriptions ─────────────────────────────────────────────────
        bus.subscribe("analysis.run", self._on_analysis_run_event)
        bus.subscribe("state.changed", self._on_state_changed)
        bus.subscribe("theme.changed", self._on_theme_changed)
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        t = _current_palette()
        self._title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {t['title']};"
        )
        self._sep.setStyleSheet(f"color: {t['border']};")
        for i in range(self._result_layout.count()):
            item = self._result_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass

    def _on_theme_changed(self, **_kw: object) -> None:
        self._apply_theme_styles()

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse(self, detected: DetectedError) -> None:
        """Start an AI analysis of *detected*.  Safe to call from the UI thread."""
        if self._worker is not None:
            logger.info(
                "Analysis request dropped (busy): %s",
                detected.display_title if detected is not None else "-",
            )
            return  # Already running; the drop is now visible in logs.
        self._last_detected = detected
        self._set_loading(True)

        service = get_error_analysis_service()
        self._worker = ErrorAnalysisWorker(service, detected)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        # Update companion state
        app_state.set_companion_state("ANALYZING")
        bus.emit("companion.state", state="ANALYZING")
        logger.info("Error analysis started (category=%s)", detected.category.value)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _set_loading(self, loading: bool) -> None:
        self._analyse_btn.setEnabled(not loading)
        if loading:
            self._status_label.setText("Analysing with AI… please wait.")
            self._status_label.show()
            self._result_area.hide()
            self._confidence_chip.setText("")
            self._confidence_chip.set_tone("off")
            self._confidence_chip.hide()

    def _reanalyse(self) -> None:
        if self._last_detected is not None:
            # Reset singleton so settings changes take effect
            reset_error_analysis_service()
            self.analyse(self._last_detected)
        else:
            self._status_label.setText("Nothing to re-analyse yet. Trigger a detection first.")
            self._status_label.show()

    def _on_analysis_run_event(self, detected: DetectedError | None = None, **_kw: object) -> None:
        if detected is not None:
            self.analyse(detected)

    def _on_state_changed(self, **_kw: object) -> None:
        # If monitoring detects a new error while idle, auto-trigger analysis
        if (
            self._worker is None
            and app_state.last_detected_category
            in {DetectionCategory.CONFIRMED_ERROR.value, DetectionCategory.POSSIBLE_ERROR.value}
        ):
            pass  # Auto-trigger handled externally via bus "analysis.run"

    def _on_succeeded(self, result: ErrorAnalysis) -> None:
        self._render_result(result)
        # Persist to SQLite history (Phase 9).
        try:
            from app.core.session import session_store
            from app.database.database import get_database
            from app.database.repositories import EventRepository

            detected = self._last_detected
            language = detected.language if detected is not None else "General"
            error_label = (
                f"{result.error_type}: {result.problem}"
                if result.error_type and result.error_type not in {"Unknown", "N/A", "General"}
                else (detected.display_title if detected is not None else result.problem)
            )
            # History renders "{language} · {error}", so strip a duplicated
            # language prefix ("JavaScript · JavaScript Syntax Error").
            lang_prefix = f"{language} "
            if error_label.startswith(lang_prefix):
                error_label = error_label[len(lang_prefix):]
            session_store.add_issue(
                language=language,
                error=error_label[:300],
                explanation=result.explanation or result.problem,
                solution=result.solution or "See analysis panel for details.",
                error_type=result.error_type,
                category=detected.category.value if detected is not None else "",
                file_path=detected.file_path if detected is not None else "",
                line_number=detected.line_number if detected is not None else None,
                confidence=result.confidence,
            )
            try:
                EventRepository(get_database()).log(
                    "analysis.completed", f"{result.error_type} conf={result.confidence:.2f}"
                )
            except Exception:
                pass
        except Exception:
            logger.exception("Failed to persist analysis to history")
        bus.emit("analysis.completed", result=result, detected=self._last_detected)
        # Update companion
        if result.confidence >= 0.55:
            app_state.set_companion_state("RESPONDING")
            bus.emit("companion.state", state="RESPONDING")
        else:
            app_state.set_companion_state("IDLE")
            bus.emit("companion.state", state="IDLE")
        bus.emit("state.changed")
        QTimer.singleShot(2000, self._return_idle)
        logger.info("Analysis rendered: %s (confidence=%.2f)", result.error_type, result.confidence)

    def _on_failed(self, message: str) -> None:
        self._status_label.setText(f"Analysis failed: {message}")
        self._status_label.show()
        self._result_area.hide()
        self._confidence_chip.setText("Failed")
        self._confidence_chip.set_tone("error")
        self._confidence_chip.show()
        self._analyse_btn.show()  # retry is meaningful once an attempt exists
        app_state.set_companion_state("ERROR")
        bus.emit("companion.state", state="ERROR")
        bus.emit("state.changed")
        QTimer.singleShot(2000, self._return_idle)

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._analyse_btn.setEnabled(True)
        if worker is not None:
            worker.deleteLater()

    def _return_idle(self) -> None:
        if app_state.companion_state in {"RESPONDING", "ERROR", "ANALYZING"}:
            app_state.set_companion_state("IDLE")
            bus.emit("companion.state", state="IDLE")
            bus.emit("state.changed")

    def _clear_result_area(self) -> None:
        while self._result_layout.count():
            item = self._result_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_result(self, result: ErrorAnalysis) -> None:
        """Populate the result area with the parsed ErrorAnalysis."""
        self._clear_result_area()

        # Confidence chip
        self._confidence_chip.setText(
            f"{result.error_type} · {result.confidence_label}"
        )
        self._confidence_chip.set_tone(result.confidence_tone)
        self._confidence_chip.show()
        self._analyse_btn.show()  # a previous analysis now exists

        # Problem summary
        problem = _BodyLabel(result.problem, tone="strong")
        self._result_layout.addWidget(problem)

        # Explanation
        if result.explanation:
            self._result_layout.addWidget(_SectionLabel("Explanation"))
            self._result_layout.addWidget(_BodyLabel(result.explanation))

        # Cause
        if result.cause:
            self._result_layout.addWidget(_SectionLabel("Root Cause"))
            self._result_layout.addWidget(_BodyLabel(result.cause))

        # Solution
        if result.solution:
            self._result_layout.addWidget(_SectionLabel("How to Fix"))
            self._result_layout.addWidget(_BodyLabel(result.solution))

        # Corrected code block
        if result.corrected_code:
            self._result_layout.addWidget(_SectionLabel("Corrected Code"))
            self._result_layout.addWidget(_CodeBlock(result.corrected_code))

        # Fallback notice
        if result.is_fallback:
            note = _BodyLabel(
                "⚠ The AI replied in plain text. Showing best-effort rendering.",
                tone="warn",
            )
            self._result_layout.addWidget(note)

        self._status_label.hide()
        self._result_area.show()
