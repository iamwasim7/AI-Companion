"""Repository layer — the ONLY place with raw SQL. UI imports SessionStore, never this."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.database.database import DatabaseManager, _now_iso


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now()


class SettingsRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def get(self, key: str, default: str = "") -> str:
        row = self._db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row else default

    def set(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, _now_iso()),
        )

    def all(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self._db.query("SELECT key, value FROM settings")}


class MessageRepository:
    DEFAULT_CONVERSATION_ID = 1

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self.ensure_default_conversation()

    def ensure_default_conversation(self) -> int:
        row = self._db.query_one("SELECT id FROM conversations WHERE id = 1")
        if row is None:
            now = _now_iso()
            self._db.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at) VALUES(1, 'General', ?, ?)",
                (now, now),
            )
        return 1

    def list_messages(self, limit: int = 500) -> list[dict]:
        rows = self._db.query(
            "SELECT id, role, text, is_error, created_at FROM messages "
            "WHERE conversation_id = 1 ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "text": row["text"],
                "is_error": bool(row["is_error"]),
                "created_at": _parse_dt(row["created_at"]),
            }
            for row in rows
        ]

    def add_message(self, role: str, text: str, is_error: bool = False) -> int:
        cur = self._db.execute(
            "INSERT INTO messages(conversation_id, role, text, is_error, created_at) VALUES(1, ?, ?, ?, ?)",
            (role, text, 1 if is_error else 0, _now_iso()),
        )
        return int(cur.lastrowid or 0)

    def clear(self) -> None:
        self._db.execute("DELETE FROM messages WHERE conversation_id = 1")


class ErrorRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def list_recent(self, limit: int = 200) -> list[dict]:
        rows = self._db.query(
            "SELECT id, language, error, explanation, solution, error_type, category, "
            "file_path, line_number, confidence, created_at FROM detected_errors "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_dict(row) for row in rows]

    def get(self, issue_id: int) -> dict | None:
        row = self._db.query_one(
            "SELECT id, language, error, explanation, solution, error_type, category, "
            "file_path, line_number, confidence, created_at FROM detected_errors WHERE id = ?",
            (issue_id,),
        )
        return self._row_to_dict(row) if row else None

    def add(
        self,
        language: str,
        error: str,
        explanation: str,
        solution: str,
        *,
        error_type: str = "",
        category: str = "",
        file_path: str = "",
        line_number: int | None = None,
        confidence: float = 0.0,
    ) -> int:
        cur = self._db.execute(
            "INSERT INTO detected_errors(language, error, explanation, solution, error_type, "
            "category, file_path, line_number, confidence, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                language[:60],
                error[:300],
                explanation[:2000],
                solution[:2000],
                error_type[:80],
                category[:40],
                file_path[:300],
                line_number,
                float(confidence),
                _now_iso(),
            ),
        )
        return int(cur.lastrowid or 0)

    def delete(self, issue_id: int) -> None:
        self._db.execute("DELETE FROM detected_errors WHERE id = ?", (issue_id,))

    def clear(self) -> None:
        self._db.execute("DELETE FROM detected_errors")

    def count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS n FROM detected_errors")
        return int(row["n"]) if row else 0

    def purge_older_than(self, days: int) -> int:
        """Delete errors older than *days*. Returns rows removed. Non-positive disables."""
        if days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        cur = self._db.execute("DELETE FROM detected_errors WHERE created_at < ?", (cutoff,))
        return int(cur.rowcount or 0)

    @staticmethod
    def _row_to_dict(row: object) -> dict:
        assert hasattr(row, "__getitem__")
        created = _parse_dt(row["created_at"])  # type: ignore[index]
        return {
            "id": int(row["id"]),  # type: ignore[index]
            "language": str(row["language"] or "General"),  # type: ignore[index]
            "error": str(row["error"] or ""),  # type: ignore[index]
            "explanation": str(row["explanation"] or ""),  # type: ignore[index]
            "solution": str(row["solution"] or ""),  # type: ignore[index]
            "error_type": str(row["error_type"] or ""),  # type: ignore[index]
            "category": str(row["category"] or ""),  # type: ignore[index]
            "file_path": str(row["file_path"] or ""),  # type: ignore[index]
            "line_number": row["line_number"],  # type: ignore[index]
            "confidence": float(row["confidence"] or 0.0),  # type: ignore[index]
            "created_at": created,
        }


class EventRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def log(self, event_type: str, detail: str = "") -> int:
        cur = self._db.execute(
            "INSERT INTO application_events(event_type, detail, created_at) VALUES(?, ?, ?)",
            (event_type[:80], detail[:1000], _now_iso()),
        )
        return int(cur.lastrowid or 0)

    def list_recent(self, limit: int = 100) -> list[dict]:
        rows = self._db.query(
            "SELECT id, event_type, detail, created_at FROM application_events "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "detail": row["detail"],
                "created_at": _parse_dt(row["created_at"]),
            }
            for row in rows
        ]
