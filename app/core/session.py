"""Persistent session store (Phase 9). SQLite-backed, same UI-facing API as Phase 2.

UI modules must keep importing :data:`session_store` and must never run SQL.
All SQL lives in ``app.database.repositories``.

Retention: ``purge_expired()`` removes ``detected_errors`` older than
``app_state.history_retention_days``. Called on startup and after inserts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.core.events import bus
from app.core.logger import get_logger

logger = get_logger("core.session")

Role = Literal["user", "assistant", "system"]

_GREETING = (
    "Start a conversation with AI Companion. "
    "Ask a question whenever you're ready."
)


@dataclass
class ChatMessage:
    role: Role
    text: str
    created_at: datetime = field(default_factory=datetime.now)
    is_error: bool = False
    id: int = 0


@dataclass
class DetectedIssue:
    id: int
    language: str
    error: str
    explanation: str
    solution: str
    created_at: datetime = field(default_factory=datetime.now)
    error_type: str = ""
    category: str = ""
    file_path: str = ""
    line_number: int | None = None
    confidence: float = 0.0


class SessionStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        from app.database.database import get_database
        from app.database.repositories import ErrorRepository, MessageRepository

        self._db = get_database(db_path) if db_path else get_database()
        self._messages_repo = MessageRepository(self._db)
        self._errors_repo = ErrorRepository(self._db)
        self.messages: list[ChatMessage] = []
        self.issues: list[DetectedIssue] = []
        self.reload()
        # No seed data: a fresh install starts with genuinely empty history.
        # The welcome greeting below lives in memory only and is never stored
        # as a detection.

    # ── Loading ──────────────────────────────────────────────────────

    def reload(self) -> None:
        """Reload caches from SQLite. Applies retention purge first."""
        try:
            from app.core.state import app_state

            self._errors_repo.purge_older_than(int(app_state.history_retention_days or 0))
        except Exception:
            pass
        self.messages = [
            ChatMessage(
                role=row["role"],
                text=row["text"],
                created_at=row["created_at"],
                is_error=row["is_error"],
                id=row["id"],
            )
            for row in self._messages_repo.list_messages()
        ]
        if not self.messages:
            self.messages = [ChatMessage(role="assistant", text=_GREETING)]
        self.issues = [
            DetectedIssue(
                id=row["id"],
                language=row["language"],
                error=row["error"],
                explanation=row["explanation"],
                solution=row["solution"],
                created_at=row["created_at"],
                error_type=row.get("error_type", ""),
                category=row.get("category", ""),
                file_path=row.get("file_path", ""),
                line_number=row.get("line_number"),
                confidence=row.get("confidence", 0.0),
            )
            for row in self._errors_repo.list_recent()
        ]

    # ── Chat ─────────────────────────────────────────────────────────

    def add_message(self, role: Role, text: str, *, is_error: bool = False) -> ChatMessage:
        row_id = self._messages_repo.add_message(role, text, is_error)
        message = ChatMessage(role=role, text=text, is_error=is_error, id=row_id)
        self.messages.append(message)
        bus.emit("chat.changed")
        return message

    def clear_messages(self) -> None:
        self._messages_repo.clear()
        self.messages = []
        self.add_message("assistant", "Conversation cleared. Ask a new question whenever you are ready.")

    def recent_user_previews(self, limit: int = 3) -> list[ChatMessage]:
        users = [item for item in reversed(self.messages) if item.role == "user"]
        return users[:limit]

    # ── Issues ───────────────────────────────────────────────────────

    def add_issue(
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
    ) -> DetectedIssue:
        row_id = self._errors_repo.add(
            language,
            error,
            explanation,
            solution,
            error_type=error_type,
            category=category,
            file_path=file_path,
            line_number=line_number,
            confidence=confidence,
        )
        issue = DetectedIssue(
            id=row_id,
            language=language,
            error=error,
            explanation=explanation,
            solution=solution,
            error_type=error_type,
            category=category,
            file_path=file_path,
            line_number=line_number,
            confidence=confidence,
        )
        self.issues.insert(0, issue)
        try:
            from app.core.state import app_state

            removed = self._errors_repo.purge_older_than(int(app_state.history_retention_days or 0))
            if removed:
                self.reload()
        except Exception:
            pass
        bus.emit("history.changed")
        return issue

    def get_issue(self, issue_id: int) -> DetectedIssue | None:
        for issue in self.issues:
            if issue.id == issue_id:
                return issue
        row = self._errors_repo.get(issue_id)
        if row is None:
            return None
        return DetectedIssue(
            id=row["id"],
            language=row["language"],
            error=row["error"],
            explanation=row["explanation"],
            solution=row["solution"],
            created_at=row["created_at"],
            error_type=row.get("error_type", ""),
            category=row.get("category", ""),
            file_path=row.get("file_path", ""),
            line_number=row.get("line_number"),
            confidence=row.get("confidence", 0.0),
        )

    def delete_issue(self, issue_id: int) -> None:
        self._errors_repo.delete(issue_id)
        self.issues = [issue for issue in self.issues if issue.id != issue_id]
        bus.emit("history.changed")

    def clear_issues(self) -> None:
        self._errors_repo.clear()
        self.issues = []
        bus.emit("history.changed")

    def clear_all_local_data(self) -> None:
        self.clear_issues()
        self.clear_messages()

    def purge_expired(self) -> int:
        from app.core.state import app_state

        removed = self._errors_repo.purge_older_than(int(app_state.history_retention_days or 0))
        if removed:
            self.reload()
        return removed


session_store = SessionStore()


def reset_session_store(db_path: Path | str | None = None) -> SessionStore:
    """Recreate the process singleton (tests use a temp DB path)."""
    global session_store
    session_store = SessionStore(db_path)
    return session_store
