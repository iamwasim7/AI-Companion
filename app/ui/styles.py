"""Shared stylesheets for dark, light, cursor, and midnight themes."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

DARK = {
    "bg": "#0f1419",
    "sidebar": "#161b22",
    "card": "#161b22",
    "hover": "#21262d",
    "border": "#30363d",
    "text": "#e6edf3",
    "muted": "#8b949e",
    "title": "#f0f6fc",
    "accent": "#388bfd",
    "accent_hover": "#4c9afc",
    "nav_checked": "#1f3a68",
    "ok_bg": "#163227",
    "ok_fg": "#56d364",
    "off_bg": "#3d1f24",
    "off_fg": "#ff7b72",
    "warn_bg": "#3d2f12",
    "warn_fg": "#e3b341",
    "user_bg": "#1f3a68",
    "input_bg": "#0d1117",
    "banner_on": "#163227",
    "banner_off": "#3d1f24",
}

LIGHT = {
    "bg": "#f6f8fa",
    "sidebar": "#ffffff",
    "card": "#ffffff",
    "hover": "#eaeef2",
    "border": "#d0d7de",
    "text": "#1f2328",
    "muted": "#656d76",
    "title": "#1f2328",
    "accent": "#0969da",
    "accent_hover": "#218bff",
    "nav_checked": "#ddf4ff",
    "ok_bg": "#dafbe1",
    "ok_fg": "#1a7f37",
    "off_bg": "#ffebe9",
    "off_fg": "#cf222e",
    "warn_bg": "#fff8c5",
    "warn_fg": "#9a6700",
    "user_bg": "#ddf4ff",
    "input_bg": "#ffffff",
    "banner_on": "#dafbe1",
    "banner_off": "#ffebe9",
}

CURSOR = {
    "bg": "#1e1e1e",
    "sidebar": "#181818",
    "card": "#252526",
    "hover": "#2a2d2e",
    "border": "#2d2d2d",
    "text": "#cccccc",
    "muted": "#858585",
    "title": "#e8e8e8",
    "accent": "#007acc",
    "accent_hover": "#0097fb",
    "nav_checked": "#04395e",
    "ok_bg": "#163227",
    "ok_fg": "#56d364",
    "off_bg": "#3d1f24",
    "off_fg": "#ff7b72",
    "warn_bg": "#3d2f12",
    "warn_fg": "#e3b341",
    "user_bg": "#04395e",
    "input_bg": "#3c3c3c",
    "banner_on": "#163227",
    "banner_off": "#3d1f24",
}

MIDNIGHT = {
    "bg": "#0a1428",
    "sidebar": "#0e1b33",
    "card": "#12233f",
    "hover": "#1a3054",
    "border": "#243b5e",
    "text": "#dbe7f5",
    "muted": "#7d93b2",
    "title": "#f2f7fd",
    "accent": "#4da3ff",
    "accent_hover": "#6db5ff",
    "nav_checked": "#16345f",
    "ok_bg": "#163227",
    "ok_fg": "#56d364",
    "off_bg": "#3d1f24",
    "off_fg": "#ff7b72",
    "warn_bg": "#3d2f12",
    "warn_fg": "#e3b341",
    "user_bg": "#16345f",
    "input_bg": "#081020",
    "banner_on": "#163227",
    "banner_off": "#3d1f24",
}

PALENIGHT = {
    "bg": "#292d3e",
    "sidebar": "#212334",
    "card": "#2b3044",
    "hover": "#353a52",
    "border": "#3c4058",
    "text": "#a6accd",
    "muted": "#676e95",
    "title": "#ffffff",
    "accent": "#c792ea",
    "accent_hover": "#d3a6ef",
    "nav_checked": "#3a3f58",
    "ok_bg": "#163227",
    "ok_fg": "#56d364",
    "off_bg": "#3d1f24",
    "off_fg": "#f07178",
    "warn_bg": "#3d2f12",
    "warn_fg": "#ffcb6b",
    "user_bg": "#3a3f58",
    "input_bg": "#212334",
    "banner_on": "#163227",
    "banner_off": "#3d1f24",
}

VERCEL = {
    "bg": "#000000",
    "sidebar": "#0a0a0a",
    "card": "#111111",
    "hover": "#1a1a1a",
    "border": "#333333",
    "text": "#ededed",
    "muted": "#888888",
    "title": "#ffffff",
    "accent": "#0070f3",
    "accent_hover": "#3291ff",
    "nav_checked": "#1f1f1f",
    "ok_bg": "#163227",
    "ok_fg": "#56d364",
    "off_bg": "#331111",
    "off_fg": "#ff7b72",
    "warn_bg": "#3d2f12",
    "warn_fg": "#e3b341",
    "user_bg": "#1a1a1a",
    "input_bg": "#000000",
    "banner_on": "#163227",
    "banner_off": "#331111",
}

THEMES = {
    "dark": DARK,
    "light": LIGHT,
    "cursor": CURSOR,
    "midnight": MIDNIGHT,
    "palenight": PALENIGHT,
    "vercel": VERCEL,
}


def build_stylesheet(theme: str) -> str:
    t = THEMES.get(theme, DARK)
    return f"""
QWidget {{
    color: {t["text"]};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

QMainWindow, QWidget#centralRoot, QDialog {{
    background-color: {t["bg"]};
}}

QWidget#sidebar {{
    background-color: {t["sidebar"]};
    border-right: 1px solid {t["border"]};
}}

QLabel#appTitle {{
    font-size: 16px;
    font-weight: 600;
    color: {t["title"]};
    padding: 4px 0 2px 0;
}}

QLabel#appSubtitle {{
    color: {t["muted"]};
    font-size: 11px;
}}

QPushButton[role="nav"] {{
    background: transparent;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 10px 12px;
    color: {t["text"]};
}}

QPushButton[role="nav"]:hover {{
    background-color: {t["hover"]};
}}

QPushButton[role="nav"]:checked {{
    background-color: {t["nav_checked"]};
    color: {t["title"]};
    font-weight: 600;
}}

QFrame[role="card"], QFrame#statusCard {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

QLabel#pageTitle {{
    font-size: 22px;
    font-weight: 600;
    color: {t["title"]};
}}

QLabel#pageHint, QLabel[role="muted"] {{
    color: {t["muted"]};
}}

QLabel[role="chip"][tone="ok"] {{
    background-color: {t["ok_bg"]};
    color: {t["ok_fg"]};
    border-radius: 999px;
    padding: 6px 10px;
}}

QLabel[role="chip"][tone="off"] {{
    background-color: {t["off_bg"]};
    color: {t["off_fg"]};
    border-radius: 999px;
    padding: 6px 10px;
}}

QLabel[role="chip"][tone="warn"] {{
    background-color: {t["warn_bg"]};
    color: {t["warn_fg"]};
    border-radius: 999px;
    padding: 6px 10px;
}}

QLabel[role="chip"][tone="info"] {{
    background-color: {t["hover"]};
    color: {t["text"]};
    border-radius: 999px;
    padding: 6px 10px;
}}

QLabel#monitoringBanner {{
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.6px;
    border-radius: 10px;
    padding: 14px;
    qproperty-alignment: AlignCenter;
}}

QLabel#monitoringBanner[active="true"] {{
    background-color: {t["banner_on"]};
    color: {t["ok_fg"]};
}}

QLabel#monitoringBanner[active="false"] {{
    background-color: {t["banner_off"]};
    color: {t["off_fg"]};
}}

QStatusBar {{
    background-color: {t["sidebar"]};
    border-top: 1px solid {t["border"]};
    color: {t["muted"]};
}}

QPushButton[role="primary"] {{
    background-color: {t["accent"]};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}}

QPushButton[role="primary"]:hover {{
    background-color: {t["accent_hover"]};
}}

QPushButton[role="primary"]:disabled {{
    background-color: {t["hover"]};
    color: {t["muted"]};
}}

QPushButton[role="secondary"], QPushButton[role="danger"] {{
    background-color: {t["hover"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 8px 14px;
}}

QPushButton[role="danger"] {{
    color: {t["off_fg"]};
}}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background-color: {t["input_bg"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    padding: 8px;
    color: {t["text"]};
    selection-background-color: {t["accent"]};
}}

QPlainTextEdit, QTextEdit {{
    padding: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {t["card"]};
    color: {t["text"]};
    selection-background-color: {t["nav_checked"]};
}}

QCheckBox {{
    spacing: 8px;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {t["hover"]};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: {t["accent"]};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QWidget#scrollInner {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {t["border"]};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QFrame[role="bubble-user"] {{
    background-color: {t["user_bg"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

QFrame[role="bubble-assistant"] {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: 12px;
}}

QFrame[role="bubble-error"] {{
    background-color: {t["off_bg"]};
    border: 1px solid {t["off_fg"]};
    border-radius: 12px;
}}

QFrame[role="code"] {{
    background-color: {t["input_bg"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QLabel#errorBanner {{
    background-color: {t["off_bg"]};
    color: {t["off_fg"]};
    border-radius: 8px;
    padding: 8px 10px;
}}

QListWidget {{
    background-color: {t["card"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
    padding: 6px;
    outline: none;
}}

QListWidget::item {{
    color: {t["text"]};
    padding: 8px;
    border-radius: 8px;
}}

QListWidget::item:selected {{
    background-color: {t["nav_checked"]};
    color: {t["title"]};
}}

QGroupBox {{
    border: 1px solid {t["border"]};
    border-radius: 12px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background-color: {t["card"]};
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {t["title"]};
}}
"""


def apply_theme(target: QApplication | QWidget, theme: str) -> None:
    target.setStyleSheet(build_stylesheet(theme))
