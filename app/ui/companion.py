"""Floating, stateful companion with Phase 8 notification popup.

* Draggable cat avatar, click opens the main window (unchanged).
* Red badge counts active notifications (bus ``notifications.changed``).
* Popup card near the companion shows the latest alert with actions:
  View analysis / Ask AI / Ignore / Dismiss (Master Spec §26).
* View → open main window on Dashboard; Ask AI → open Chat with a
  prefilled follow-up; Ignore → suppress this error signature;
  Dismiss → clear the popup.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QMouseEvent, QPainter, QPaintEvent, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.core.config import Config
from app.core.events import bus
from app.core.logger import get_logger
from app.core.state import app_state

logger = get_logger("ui.companion")

_STATE_COLORS = {"IDLE": "#8b949e", "THINKING": "#58a6ff", "ANALYZING": "#a371f7", "ALERT": "#e3b341", "RESPONDING": "#56d364", "ERROR": "#ff7b72"}

AVATAR_CLASSIC = "classic"
AVATARS: tuple[str, ...] = ("classic", "cat_orange", "cat_black", "dog_golden", "turtle", "gecko")
AVATAR_LABELS: dict[str, str] = {
    "classic": "Classic",
    "cat_orange": "Orange Cat",
    "cat_black": "Black Cat",
    "dog_golden": "Golden Dog",
    "turtle": "Turtle",
    "gecko": "Gecko",
}


def avatar_dir() -> Path:
    """Folder holding optional companion PNGs (may be empty)."""
    return Config.ASSETS_DIR / "companion"


def resolve_avatar_path(name: str, base_dir: Path | None = None) -> Path | None:
    """Return the PNG path for *name*, or None for classic/missing/invalid.

    Pure filesystem check — safe to call anywhere, including tests.
    """
    if name == AVATAR_CLASSIC or name not in AVATARS:
        return None
    candidate = (base_dir or avatar_dir()) / f"{name}.png"
    return candidate if candidate.is_file() else None


def build_ask_prefill(notification: object) -> str:
    """Compose the Ask-AI chat prefill for a notification.

    Pure function (no Qt): summary plus the detected code context when the
    notification carries it, so Chat receives what the analysis saw. When no
    clean code line exists, falls back to nearby raw OCR lines (same shared
    helper as the analysis context path), explicitly marked unverified.
    Returns "" when there is nothing worth prefilling.
    """
    summary = (
        getattr(notification, "result_summary", "")
        or getattr(notification, "body", "")
        or ""
    ).strip()
    detected = getattr(notification, "detected", None)
    code = (getattr(detected, "relevant_code", "") or "").strip() if detected is not None else ""
    if not summary and not code:
        return ""
    parts = [f"Explain this error in simple terms:\n{summary}" if summary else "Explain this error in simple terms:"]
    if code:
        location = ""
        if detected is not None:
            file_path = (getattr(detected, "file_path", "") or "").strip()
            line_number = getattr(detected, "line_number", None)
            if file_path:
                location = file_path
                if line_number is not None:
                    location += f", line {line_number}"
        header = f"Code{f' ({location})' if location else ''}:"
        parts.append(f"{header}\n{code[:300]}")
    else:
        # No clean code line (e.g. OCR garbled it): reuse the shared
        # nearby-lines fallback so Chat still gets something to work with.
        nearby = _prefill_nearby_lines(detected)
        if nearby:
            parts.append("Nearby screen text (unverified OCR — hints only):\n" + "\n".join(nearby))
    return "\n".join(parts)[:800]


def _prefill_nearby_lines(detected: object) -> list[str]:
    """Best-effort raw lines for the prefill; never raises."""
    try:
        if detected is None:
            return []
        from app.detection.context_detector import ContextDetector

        return ContextDetector.nearby_error_lines(detected)  # type: ignore[arg-type]
    except Exception:
        return []


class NotificationPopup(QWidget):
    """Small always-on-top card anchored near the companion."""

    view_requested = Signal()
    ask_requested = Signal()
    dismiss_requested = Signal()
    ignore_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Companion — Alert")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(320)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("statusCard")
        card.setStyleSheet(
            "QWidget#statusCard { background-color: #161b22; border: 1px solid #e3b341; border-radius: 12px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        self._title = QLabel("Notification")
        self._title.setStyleSheet("font-weight: 700; color: #f0f6fc;")
        self._title.setWordWrap(True)
        self._body = QLabel("")
        self._body.setWordWrap(True)
        self._body.setStyleSheet("color: #8b949e;")
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._title)
        layout.addWidget(self._body)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._view_btn = QPushButton("View")
        self._view_btn.setProperty("role", "primary")
        self._view_btn.clicked.connect(self.view_requested.emit)
        self._ask_btn = QPushButton("Ask AI")
        self._ask_btn.setProperty("role", "secondary")
        self._ask_btn.clicked.connect(self.ask_requested.emit)
        self._ignore_btn = QPushButton("Ignore")
        self._ignore_btn.setProperty("role", "secondary")
        self._ignore_btn.clicked.connect(self.ignore_requested.emit)
        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setProperty("role", "secondary")
        self._dismiss_btn.clicked.connect(self.dismiss_requested.emit)
        for btn in (self._view_btn, self._ask_btn, self._ignore_btn, self._dismiss_btn):
            btn.setMinimumHeight(28)
            row.addWidget(btn)
        layout.addLayout(row)
        outer.addWidget(card)

    def show_notification(self, title: str, body: str) -> None:
        self._title.setText(title)
        self._body.setText(body)
        self.show()
        self.raise_()


class FloatingCompanion(QWidget):
    """Draggable visual status indicator. Click it to reveal the main window."""

    open_main_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Companion")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_offset = QPoint()
        self._dragging = False
        self._unread = 0
        self._current_notification_id: int | None = None
        self._popup = NotificationPopup()
        self._popup.view_requested.connect(self._on_view)
        self._popup.ask_requested.connect(self._on_ask)
        self._popup.dismiss_requested.connect(self._on_dismiss)
        self._popup.ignore_requested.connect(self._on_ignore)
        self._apply_size(app_state.companion_size)
        self._avatar_pixmap: QPixmap | None = None
        self._load_avatar()
        bus.subscribe("companion.state", self._state_changed)
        bus.subscribe("companion.state.silent", self._state_changed)
        bus.subscribe("companion.resize", self._resize_changed)
        bus.subscribe("companion.topmost", self._topmost_changed)
        bus.subscribe("companion.avatar", self._avatar_changed)
        bus.subscribe("notification.show", self._on_notification_show)
        bus.subscribe("notifications.changed", self._on_notifications_changed)
        logger.info("Companion created (state=%s)", app_state.companion_state)

    def _apply_size(self, size: int) -> None:
        self.setFixedSize(size, size)

    def _state_changed(self, state: str, **_payload: object) -> None:
        app_state.set_companion_state(state)
        self.update()

    def _resize_changed(self, size: int, **_payload: object) -> None:
        self._apply_size(size)

    def _topmost_changed(self, enabled: bool, **_payload: object) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def _load_avatar(self) -> None:
        """Load the selected PNG avatar; fall back to the painted classic."""
        name = app_state.companion_avatar if app_state.companion_avatar in AVATARS else AVATAR_CLASSIC
        path = resolve_avatar_path(name)
        pixmap = QPixmap(str(path)) if path is not None else QPixmap()
        if pixmap.isNull():
            if path is not None:
                logger.warning("Avatar image unreadable, using classic: %s", path)
            self._avatar_pixmap = None
        else:
            self._avatar_pixmap = pixmap

    def _avatar_changed(self, name: str = AVATAR_CLASSIC, **_payload: object) -> None:
        app_state.companion_avatar = name if name in AVATARS else AVATAR_CLASSIC
        self._load_avatar()
        self.update()

    # ── Notifications ────────────────────────────────────────────────

    def _on_notification_show(self, notification: object = None, **_payload: object) -> None:
        try:
            title = getattr(notification, "title", "Notification") or "Notification"
            body = getattr(notification, "body", "") or ""
            self._current_notification_id = getattr(notification, "id", None)
            self._popup.show_notification(str(title), str(body))
            # Anchor popup just left of the companion so it never covers work.
            pos = self.pos()
            self._popup.move(max(0, pos.x() - 340), pos.y())
        except Exception:
            logger.exception("Failed to show companion popup")

    def _on_notifications_changed(self, **_payload: object) -> None:
        try:
            from app.services.notification_service import get_notification_service

            self._unread = len(get_notification_service().active)
        except Exception:
            self._unread = 0
        self.update()
        if self._unread == 0 and self._popup.isVisible():
            self._popup.hide()

    def _on_view(self) -> None:
        self._popup.hide()
        bus.emit("navigate", page="dashboard")
        self.open_main_requested.emit()

    def _on_ask(self) -> None:
        notification_id = self._current_notification_id
        prefill = ""
        try:
            from app.services.notification_service import get_notification_service

            for item in get_notification_service().active:
                if item.id == notification_id:
                    prefill = build_ask_prefill(item)
                    break
        except Exception:
            prefill = ""
        self._popup.hide()
        if prefill:
            bus.emit("chat.prefill", text=prefill)
        bus.emit("navigate", page="chat")
        self.open_main_requested.emit()

    def _on_dismiss(self) -> None:
        self._popup.hide()
        if self._current_notification_id is not None:
            try:
                from app.services.notification_service import get_notification_service

                get_notification_service().dismiss(self._current_notification_id)
            except Exception:
                pass
            self._current_notification_id = None

    def _on_ignore(self) -> None:
        self._popup.hide()
        if self._current_notification_id is not None:
            try:
                from app.services.notification_service import get_notification_service

                get_notification_service().ignore(self._current_notification_id)
            except Exception:
                pass
            self._current_notification_id = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._dragging = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if not self._dragging:
                self.open_main_requested.emit()
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self._popup.hide()
        except Exception:
            pass
        app_state.companion_visible = False
        self.closed.emit()
        bus.emit("state.changed")  # refresh Dashboard chips, not just the status bar
        super().closeEvent(event)

    def _paint_image_avatar(self, painter: QPainter, pixmap: QPixmap, size: int, scale: float) -> None:
        """Draw a PNG avatar in a rounded frame (no ring) plus a dark pill
        behind the state label so text reads over any artwork."""
        radius = round(20 * scale)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
        painter.save()
        painter.setClipPath(clip)
        scaled = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.restore()
        label = app_state.companion_state
        pill_w = painter.fontMetrics().horizontalAdvance(label) + round(20 * scale)
        pill_h = round(20 * scale)
        pill_x = (size - pill_w) / 2
        pill_y = size - round(15 * scale) - pill_h
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 175))
        painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), round(8 * scale), round(8 * scale))

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        size = self.width()
        scale = size / 128
        def point(x: int, y: int) -> QPoint:
            return QPoint(round(x * scale), round(y * scale))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(_STATE_COLORS.get(app_state.companion_state, "#8b949e"))
        avatar = self._avatar_pixmap
        use_image = avatar is not None and not avatar.isNull()
        if use_image:
            self._paint_image_avatar(painter, avatar, size, scale)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2d333b"))
            painter.drawEllipse(round(8 * scale), round(16 * scale), round(112 * scale), round(104 * scale))
            painter.setBrush(QColor("#3d444d"))
            painter.drawPolygon([point(28, 36), point(44, 8), point(58, 36)])
            painter.drawPolygon([point(70, 36), point(84, 8), point(100, 36)])
            painter.setBrush(QColor("#f0f6fc"))
            painter.drawEllipse(round(40 * scale), round(52 * scale), round(16 * scale), round(20 * scale))
            painter.drawEllipse(round(72 * scale), round(52 * scale), round(16 * scale), round(20 * scale))
            painter.setBrush(QColor("#0f1419"))
            painter.drawEllipse(round(45 * scale), round(60 * scale), round(7 * scale), round(9 * scale))
            painter.drawEllipse(round(77 * scale), round(60 * scale), round(7 * scale), round(9 * scale))
            painter.setPen(QPen(color, max(2, round(2 * scale))))
            if app_state.companion_state == "ERROR":
                painter.drawLine(point(55, 80), point(73, 94)); painter.drawLine(point(73, 80), point(55, 94))
            elif app_state.companion_state == "THINKING":
                painter.drawText(self.rect().adjusted(0, round(70 * scale), 0, 0), Qt.AlignmentFlag.AlignHCenter, "···")
            else:
                painter.drawArc(round(52 * scale), round(78 * scale), round(24 * scale), round(16 * scale), 200 * 16, 140 * 16)
        # White label over the dark pill for image avatars; state-colored
        # label on the painted classic background as before.
        painter.setPen(QColor("#ffffff") if use_image else color)
        painter.drawText(self.rect().adjusted(0, round(96 * scale), 0, -round(4 * scale)), Qt.AlignmentFlag.AlignHCenter, app_state.companion_state)
        # Unread badge (Phase 8).
        if self._unread > 0:
            badge_r = round(14 * scale)
            cx = round(108 * scale)
            cy = round(24 * scale)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#f85149"))
            painter.drawEllipse(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                painter.fontMetrics().boundingRect(f"{min(self._unread, 9)}").translated(cx - 5, cy + 5),
                Qt.AlignmentFlag.AlignCenter,
                f"{min(self._unread, 9)}{'+' if self._unread > 9 else ''}",
            )
