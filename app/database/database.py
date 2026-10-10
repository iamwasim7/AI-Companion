"""SQLite connection manager. Single-writer, thread-safe, no screenshots stored.

Tables (schema v1)::

    settings(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)
    conversations(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_at TEXT, updated_at TEXT)
    messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, role TEXT,
             text TEXT, is_error INTEGER, created_at TEXT)
    detected_errors(id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, error TEXT,
             explanation TEXT, solution TEXT, error_type TEXT, category TEXT,
             file_path TEXT, line_number INTEGER, confidence REAL, created_at TEXT)
    application_events(id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT,
             detail TEXT, created_at TEXT)

Privacy: only short text is stored. Screenshots are never persisted.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logger import get_logger

logger = get_logger("database")

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'General',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL DEFAULT 1,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    is_error INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS detected_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    language TEXT NOT NULL DEFAULT 'General',
    error TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    solution TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    line_number INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_errors_created ON detected_errors(created_at DESC);
CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_created ON application_events(created_at DESC);
"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DatabaseManager:
    """Thread-safe SQLite owner. Use :func:`get_database` in app code."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.commit()
        logger.info("Database ready at %s", self._path)

    @property
    def path(self) -> Path:
        return self._path

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, seq: list[tuple[Any, ...]]) -> None:
        with self._lock:
            self._conn.executemany(sql, seq)
            self._conn.commit()

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass


_database: DatabaseManager | None = None


def _default_path() -> Path:
    from app.core.config import Config

    return Config.DB_PATH


def get_database(db_path: Path | str | None = None) -> DatabaseManager:
    """Return the process singleton, creating it on first use."""
    global _database
    if _database is None:
        _database = DatabaseManager(db_path or _default_path())
    return _database


def reset_database(db_path: Path | str | None = None) -> DatabaseManager:
    """Close and recreate the singleton (tests use a temp path)."""
    global _database
    if _database is not None:
        try:
            _database.close()
        except Exception:
            pass
        _database = None
    return get_database(db_path)
