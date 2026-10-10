"""Safe, in-memory capture wrappers around Qt's desktop screen API."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QGuiApplication, QImage, QScreen


@dataclass(frozen=True)
class ScreenDescriptor:
    key: str
    label: str
    width: int
    height: int


class ScreenCaptureError(RuntimeError):
    pass


class ScreenCapture:
    """Captures a selected display to memory only; it never writes image files."""

    @staticmethod
    def available_screens() -> list[ScreenDescriptor]:
        app = QGuiApplication.instance()
        if app is None:
            return []
        primary = app.primaryScreen()
        descriptors: list[ScreenDescriptor] = []
        for index, screen in enumerate(app.screens(), start=1):
            geometry = screen.geometry()
            is_primary = screen is primary
            key = "primary" if is_primary else f"screen:{screen.name()}:{index}"
            prefix = "Primary display" if is_primary else f"Display {index}"
            label = f"{prefix} — {geometry.width()} × {geometry.height()}"
            descriptors.append(ScreenDescriptor(key, label, geometry.width(), geometry.height()))
        return descriptors

    @staticmethod
    def _screen_for_key(key: str) -> QScreen:
        app = QGuiApplication.instance()
        if app is None:
            raise ScreenCaptureError("Screen capture is unavailable before the application starts.")
        if key in {"", "full_screen", "primary"}:
            screen = app.primaryScreen()
            if screen is None:
                raise ScreenCaptureError("No display is available for capture.")
            return screen
        for index, screen in enumerate(app.screens(), start=1):
            if key == f"screen:{screen.name()}:{index}":
                return screen
        raise ScreenCaptureError("The selected display is no longer available.")

    @classmethod
    def capture(cls, screen_key: str) -> QImage:
        screen = cls._screen_for_key(screen_key)
        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            raise ScreenCaptureError("The selected display could not be captured.")
        image = pixmap.toImage()
        if image.isNull():
            raise ScreenCaptureError("The selected display returned an empty frame.")
        return image
