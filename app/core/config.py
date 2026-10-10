"""Application configuration loaded from the environment.

Canonical AI env-var names (new):
    AI_PROVIDER   — "openai_compatible" | "openai_native"
    AI_API_KEY    — API key for the active provider
    AI_BASE_URL   — base URL for openai_compatible endpoints
    AI_MODEL      — model identifier (free-text)

Legacy names still accepted (backward compat for existing .env files):
    CUSTOM_API_KEY  → same as AI_API_KEY
    CUSTOM_BASE_URL → same as AI_BASE_URL
    CUSTOM_MODEL    → same as AI_MODEL
    OPENAI_API_KEY  → used when AI_PROVIDER=openai_native
    AI_PROVIDER=custom  → treated as openai_compatible
    AI_PROVIDER=openai  → treated as openai_native
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

import sys

if getattr(sys, "frozen", False):
    # PyInstaller build: keep DB/logs/.env next to the exe so they persist.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def resource_base() -> Path:
    """Directory that holds bundled read-only data (``assets/``).

    PyInstaller one-dir builds extract ``datas`` under ``sys._MEIPASS``
    (the ``_internal`` folder), *not* next to the exe — so frozen code
    must look there first. Falls back to the exe folder and finally the
    source tree, making the lookup robust across layouts.
    """
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle and (Path(bundle) / "assets").is_dir():
            return Path(bundle)
        return PROJECT_ROOT
    return PROJECT_ROOT


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_ai_env(canonical: str, *legacy: str, default: str = "") -> str:
    """Read *canonical* env var; fall back through *legacy* names in order."""
    val = os.getenv(canonical, "").strip()
    if val:
        return val
    for name in legacy:
        val = os.getenv(name, "").strip()
        if val:
            return val
    return default


def _normalize_provider(raw: str) -> str:
    """Map legacy provider names to canonical values."""
    raw = raw.strip().lower()
    if raw == "custom":
        return "openai_compatible"
    if raw == "openai":
        return "openai_native"
    # Already canonical or unknown — pass through as-is.
    return raw


def _resolve_tesseract_path() -> str:
    env_path = os.getenv("TESSERACT_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path
    which_path = shutil.which("tesseract")
    if which_path and os.path.isfile(which_path):
        return which_path
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def upsert_env_value(name: str, value: str) -> None:
    """Create or replace a single .env key without logging the value."""
    path = PROJECT_ROOT / ".env"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{name}="
    updated = False
    lines: list[str] = []
    for line in existing:
        if line.strip().startswith(prefix):
            lines.append(f"{name}={value}")
            updated = True
        else:
            lines.append(line)
    if not updated:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value
    Config.refresh()


class Config:
    """Static application configuration. Secrets are never logged or displayed."""

    APP_NAME = "AI Companion"
    APP_VERSION = "1.3.0"
    ORGANIZATION = "AI Companion"

    PROJECT_ROOT = PROJECT_ROOT
    ASSETS_DIR = resource_base() / "assets"
    LOG_DIR = PROJECT_ROOT / "logs"
    ENV_PATH = PROJECT_ROOT / ".env"
    DATA_DIR = PROJECT_ROOT / "data"
    DB_PATH = Path(os.getenv("AI_COMPANION_DB_PATH", str(PROJECT_ROOT / "data" / "ai_companion.db")))

    AI_MODE = os.getenv("AI_MODE", "mock").strip().lower() or "mock"

    # ── Canonical AI provider config ──────────────────────────────────────────
    # Read new canonical names; fall back to legacy names transparently.
    AI_PROVIDER: str = _normalize_provider(
        _read_ai_env("AI_PROVIDER", default="openai_compatible")
    )
    AI_BASE_URL: str = _read_ai_env("AI_BASE_URL", "CUSTOM_BASE_URL")
    AI_MODEL: str = _read_ai_env("AI_MODEL", "CUSTOM_MODEL")
    # Key presence only — the raw value is never stored as a class attribute.
    AI_API_KEY_SET: bool = bool(
        _read_ai_env("AI_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY")
    )

    # ── Legacy aliases (read-only shims for code that still uses old names) ───
    # Plain attributes mirroring the canonical fields, so existing code
    # referencing CUSTOM_BASE_URL / CUSTOM_MODEL doesn't break.
    # (They are synced in refresh(); keys are never stored as attributes.)
    CUSTOM_BASE_URL: str = AI_BASE_URL
    CUSTOM_MODEL: str = AI_MODEL
    CUSTOM_API_KEY_SET: bool = AI_API_KEY_SET

    # Keep OPENAI_* for code that still references them.
    OPENAI_API_KEY_SET: bool = bool(os.getenv("OPENAI_API_KEY", "").strip()) or bool(
        os.getenv("AI_API_KEY", "").strip()
    )
    OPENAI_TIMEOUT_SECONDS = 20.0
    OPENAI_MAX_RETRIES = 1
    AI_CONTEXT_MESSAGES = 12

    COMPANION_VISIBLE_DEFAULT = _env_bool("COMPANION_VISIBLE", True)
    COMPANION_ALWAYS_ON_TOP = True

    TESSERACT_PATH = _resolve_tesseract_path()

    # ── Runtime methods ───────────────────────────────────────────────────────

    @classmethod
    def refresh(cls) -> None:
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        cls.AI_MODE = os.getenv("AI_MODE", "mock").strip().lower() or "mock"
        cls.AI_PROVIDER = _normalize_provider(
            _read_ai_env("AI_PROVIDER", default="openai_compatible")
        )
        cls.AI_BASE_URL = _read_ai_env("AI_BASE_URL", "CUSTOM_BASE_URL")
        cls.AI_MODEL = _read_ai_env("AI_MODEL", "CUSTOM_MODEL")
        cls.AI_API_KEY_SET = bool(
            _read_ai_env("AI_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY")
        )
        # Sync legacy aliases.
        cls.CUSTOM_BASE_URL = cls.AI_BASE_URL
        cls.CUSTOM_MODEL = cls.AI_MODEL
        cls.CUSTOM_API_KEY_SET = cls.AI_API_KEY_SET
        cls.OPENAI_API_KEY_SET = bool(os.getenv("OPENAI_API_KEY", "").strip()) or bool(
            os.getenv("AI_API_KEY", "").strip()
        )
        cls.TESSERACT_PATH = _resolve_tesseract_path()

    @classmethod
    def get_ai_api_key(cls) -> str:
        """Return the active API key value.  Never log the return value."""
        return _read_ai_env("AI_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY")

    @classmethod
    def is_mock_mode(cls) -> bool:
        return cls.AI_MODE != "live"

    @classmethod
    def is_custom_provider(cls) -> bool:
        """Legacy predicate — True when provider is openai_compatible."""
        return cls.AI_PROVIDER == "openai_compatible"

    @classmethod
    def effective_model(cls, preferred: str = "") -> str:
        """Model actually sent to the API.

        Priority: canonical AI_MODEL env var > *preferred* argument > "".
        """
        if cls.AI_MODEL:
            return cls.AI_MODEL
        return preferred

    @classmethod
    def api_key_status_label(cls) -> str:
        return "Configured" if cls.AI_API_KEY_SET else "Not configured"

    @classmethod
    def is_ocr_available(cls) -> bool:
        return bool(cls.TESSERACT_PATH and os.path.isfile(cls.TESSERACT_PATH))

    @classmethod
    def ocr_status_label(cls) -> str:
        return "Available" if cls.is_ocr_available() else "Not configured"
