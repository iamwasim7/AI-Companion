"""Settings UI; changes are session-only except explicitly saved configuration."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config, upsert_env_value
from app.core.events import bus
from app.core.session import session_store
from app.core.state import app_state
from app.ui.widgets.common import Card, NoWheelComboBox, PageHeader, StatusChip


# ── Off-thread Test Connection worker ─────────────────────────────────────────

class _TestConnectionWorker(QThread):
    """Run CompatibleProvider.test_connection() off the UI thread."""

    finished = Signal(bool, str)  # (success, message)

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def run(self) -> None:
        try:
            from app.core.ai_service import AIConfigurationError, CompatibleProvider

            provider = CompatibleProvider(self._api_key, self._base_url)
            ok, msg = provider.test_connection(self._model)
            self.finished.emit(ok, msg)
        except AIConfigurationError as exc:
            self.finished.emit(False, str(exc))
        except Exception:
            self.finished.emit(False, "Connection test could not be completed. Check your settings.")
        finally:
            # Clear references so the key doesn't linger in memory.
            self._api_key = ""


# ── Settings page ─────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("scrollInner")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(
            PageHeader(
                "Settings",
                "Appearance and controls apply immediately. "
                "API keys remain local and are never displayed or logged.",
            )
        )
        self._key_chip = StatusChip("API key", "off")
        layout.addWidget(self._key_chip)
        layout.addWidget(self._build_ai_card())
        layout.addWidget(self._build_companion_card())
        layout.addWidget(self._build_privacy_card())
        layout.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll)
        self._test_worker: _TestConnectionWorker | None = None
        self.refresh()

    # ── AI Configuration card ─────────────────────────────────────────────────

    def _build_ai_card(self) -> Card:
        card = Card()

        # ── Section title ──────────────────────────────────────────────────────
        title = QLabel("AI Configuration")
        title.setStyleSheet("font-weight: 600;")
        card.body.addWidget(title)

        form = QFormLayout()

        # AI mode (Title-Case labels; lowercase canonical values in itemData)
        self._mode = NoWheelComboBox()
        self._mode.addItem("Mock", "mock")
        self._mode.addItem("Live", "live")
        _mode_value = Config.AI_MODE if Config.AI_MODE in {"mock", "live"} else "mock"
        self._mode.setCurrentIndex(max(0, self._mode.findData(_mode_value)))
        self._mode.currentTextChanged.connect(self._on_mode)

        # Provider — user-friendly labels; saves canonical value
        self._provider = NoWheelComboBox()
        self._provider.addItems(["OpenAI-Compatible", "OpenAI Native"])
        self._provider.setCurrentIndex(
            0 if Config.AI_PROVIDER != "openai_native" else 1
        )
        self._provider.currentTextChanged.connect(self._on_provider)

        # Explanation style (Title-Case labels; lowercase canonical values)
        self._behavior = NoWheelComboBox()
        self._behavior.addItem("Beginner", "beginner")
        self._behavior.addItem("Concise", "concise")
        self._behavior.addItem("Detailed", "detailed")
        self._behavior.setCurrentIndex(
            max(0, self._behavior.findData(app_state.ai_behavior))
        )
        self._behavior.currentTextChanged.connect(self._on_behavior)

        form.addRow("AI mode", self._mode)
        form.addRow("Provider (live mode)", self._provider)
        form.addRow("Explanation style", self._behavior)
        card.body.addLayout(form)

        # ── Endpoint fields ────────────────────────────────────────────────────
        endpoint_form = QFormLayout()

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://integrate.api.nvidia.com/v1")
        self._base_url.setText(Config.AI_BASE_URL)
        self._base_url.editingFinished.connect(self._save_base_url)

        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("e.g. meta/llama-3.2-11b-vision-instruct")
        # Populate from canonical config first, fall back to in-memory state
        self._model_input.setText(Config.AI_MODEL or app_state.ai_model)
        self._model_input.editingFinished.connect(self._save_model)

        endpoint_form.addRow("Base URL", self._base_url)
        endpoint_form.addRow("Model", self._model_input)
        card.body.addLayout(endpoint_form)

        # ── API key row ────────────────────────────────────────────────────────
        key_row = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("API key (saved locally; never displayed or logged)")
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        save_key_btn = QPushButton("Save key")
        save_key_btn.setProperty("role", "secondary")
        save_key_btn.clicked.connect(self._save_key)
        key_row.addWidget(self._key_input, 1)
        key_row.addWidget(save_key_btn)
        card.body.addLayout(key_row)

        # ── Test Connection row ────────────────────────────────────────────────
        test_row = QHBoxLayout()
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.setProperty("role", "secondary")
        self._test_btn.clicked.connect(self._on_test_connection)
        self._conn_chip = StatusChip("Not tested", "info")
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._conn_chip)
        test_row.addStretch(1)
        card.body.addLayout(test_row)

        return card

    # ── Companion card ────────────────────────────────────────────────────────

    def _build_companion_card(self) -> Card:
        from app.ui.companion import AVATAR_LABELS, AVATARS

        card = Card()
        title = QLabel("Companion and appearance")
        title.setStyleSheet("font-weight: 600;")
        card.body.addWidget(title)
        form = QFormLayout()
        self._theme = NoWheelComboBox()
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")
        self._theme.addItem("Cursor", "cursor")
        self._theme.addItem("Midnight", "midnight")
        self._theme.addItem("Palenight", "palenight")
        self._theme.addItem("Vercel", "vercel")
        self._theme.setCurrentIndex(max(0, self._theme.findData(app_state.theme)))
        self._theme.currentTextChanged.connect(self._on_theme)
        self._avatar = NoWheelComboBox()
        for avatar_id in AVATARS:
            self._avatar.addItem(AVATAR_LABELS[avatar_id], avatar_id)
        current = app_state.companion_avatar if app_state.companion_avatar in AVATARS else "classic"
        self._avatar.setCurrentIndex(max(0, self._avatar.findData(current)))
        self._avatar.currentIndexChanged.connect(self._on_avatar)
        self._size = QSpinBox()
        self._size.setRange(96, 180)
        self._size.setValue(app_state.companion_size)
        self._size.valueChanged.connect(self._on_size)
        self._on_top = QCheckBox("Keep companion above other windows")
        self._on_top.setChecked(app_state.companion_always_on_top)
        self._on_top.toggled.connect(self._on_always_on_top)
        form.addRow("Theme", self._theme)
        form.addRow("Companion avatar", self._avatar)
        form.addRow("Companion size", self._size)
        form.addRow("", self._on_top)
        card.body.addLayout(form)
        return card

    # ── Privacy card ──────────────────────────────────────────────────────────

    def _build_privacy_card(self) -> Card:
        from app.core.config import Config

        card = Card()
        title = QLabel("Privacy & storage")
        title.setStyleSheet("font-weight: 600;")
        note = QLabel(
            "Chat and error history persist locally in SQLite. Screenshots are never stored. "
            "API keys stay in .env and are never written to the database."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        form = QFormLayout()
        self._retention = QSpinBox()
        self._retention.setRange(0, 365)
        self._retention.setValue(app_state.history_retention_days)
        self._retention.setSpecialValueText("Keep forever")
        self._retention.valueChanged.connect(self._on_retention)
        form.addRow("History retention (days, 0 = forever)", self._retention)
        try:
            db_label = QLabel(f"Database: {Config.DB_PATH}")
        except Exception:
            db_label = QLabel("Database: local SQLite")
        db_label.setWordWrap(True)
        db_label.setProperty("role", "muted")
        clear = QPushButton("Clear local chat + history")
        clear.setProperty("role", "danger")
        clear.clicked.connect(session_store.clear_all_local_data)
        card.body.addWidget(title)
        card.body.addWidget(note)
        card.body.addLayout(form)
        card.body.addWidget(db_label)
        card.body.addWidget(clear)
        return card

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _save_key(self) -> None:
        value = self._key_input.text().strip()
        if value:
            upsert_env_value("AI_API_KEY", value)
            self._key_input.clear()
            self._reset_ai_service()
            self.refresh()

    def _save_base_url(self) -> None:
        upsert_env_value("AI_BASE_URL", self._base_url.text().strip())
        self._reset_ai_service()
        self.refresh()

    def _save_model(self) -> None:
        model = self._model_input.text().strip()
        upsert_env_value("AI_MODEL", model)
        app_state.ai_model = model
        self._reset_ai_service()
        bus.emit("state.changed")

    def _on_mode(self, value: str) -> None:
        try:
            data = self._mode.currentData()
        except Exception:
            data = None
        canonical = str(data or value or "").strip().lower()
        if canonical not in {"mock", "live"}:
            canonical = "mock"
        upsert_env_value("AI_MODE", canonical)
        app_state.ai_connected = False
        self._reset_ai_service()
        bus.emit("state.changed")

    def _on_provider(self, label: str) -> None:
        value = "openai_native" if label == "OpenAI Native" else "openai_compatible"
        upsert_env_value("AI_PROVIDER", value)
        app_state.ai_connected = False
        self._reset_ai_service()
        bus.emit("state.changed")
        self.refresh()

    def _on_behavior(self, value: str) -> None:
        try:
            data = self._behavior.currentData()
        except Exception:
            data = None
        canonical = str(data or value or "").strip().lower()
        if canonical not in {"beginner", "concise", "detailed"}:
            return
        app_state.ai_behavior = canonical
        bus.emit("state.changed")
        self._persist()

    def _on_theme(self, value: str) -> None:
        try:
            data = self._theme.currentData()
        except Exception:
            data = None
        canonical = str(data or value or "").strip().lower()
        from app.ui.styles import THEMES

        if canonical not in THEMES:
            return
        app_state.theme = canonical
        bus.emit("theme.changed")
        self._persist()

    def _on_retention(self, value: int) -> None:
        from app.core.session import session_store as _store

        app_state.history_retention_days = value
        try:
            removed = _store.purge_expired()
            if removed:
                bus.emit("history.changed")
        except Exception:
            pass
        bus.emit("state.changed")
        self._persist()

    def _on_size(self, value: int) -> None:
        app_state.companion_size = value
        bus.emit("companion.resize", size=value)

    def _on_avatar(self, index: int) -> None:
        from app.ui.companion import AVATAR_CLASSIC, AVATARS

        name = self._avatar.itemData(index) or AVATAR_CLASSIC
        if name not in AVATARS:
            name = AVATAR_CLASSIC
        app_state.companion_avatar = name
        bus.emit("companion.avatar", name=name)
        bus.emit("state.changed")
        self._persist()

    def _on_always_on_top(self, value: bool) -> None:
        app_state.companion_always_on_top = value
        bus.emit("companion.topmost", enabled=value)

    # ── Test Connection ───────────────────────────────────────────────────────

    def _on_test_connection(self) -> None:
        """Start an off-thread connection test; never blocks the UI."""
        if self._test_worker and self._test_worker.isRunning():
            return  # Already in progress.

        # Determine the key to use: freshly typed key > saved key.
        typed_key = self._key_input.text().strip()
        api_key = typed_key or Config.get_ai_api_key()
        base_url = self._base_url.text().strip() or Config.AI_BASE_URL
        model = self._model_input.text().strip() or Config.AI_MODEL

        self._conn_chip.setText("Testing…")
        self._conn_chip.set_tone("info")
        self._test_btn.setEnabled(False)

        self._test_worker = _TestConnectionWorker(api_key, base_url, model)
        self._test_worker.finished.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, success: bool, message: str) -> None:
        self._test_btn.setEnabled(True)
        if success:
            self._conn_chip.setText("✓ Connected")
            self._conn_chip.set_tone("ok")
        else:
            display = message or "Connection failed."
            self._conn_chip.setText(f"✗ {display}")
            self._conn_chip.set_tone("off")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _reset_ai_service() -> None:
        """Force the singleton to recreate with the new configuration."""
        try:
            from app.ai.error_analysis_service import reset_error_analysis_service
            reset_error_analysis_service()
        except Exception:
            pass

    def _persist(self) -> None:
        try:
            from app.services.settings_service import save_persisted_settings
            save_persisted_settings()
        except Exception:
            pass

    def refresh(self) -> None:
        status = Config.api_key_status_label().lower()
        if Config.is_mock_mode():
            scope = "mock mode"
        elif Config.AI_PROVIDER == "openai_native":
            scope = "OpenAI Native"
        else:
            scope = "OpenAI-Compatible"
        configured = status == "configured"
        self._key_chip.setText(
            f"API key ({scope}): {status} locally"
            if configured
            else f"API key ({scope}): not configured"
        )
        self._key_chip.set_tone("ok" if configured else "off")