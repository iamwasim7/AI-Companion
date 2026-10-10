"""Phase 9 tests: SQLite repositories + persistent SessionStore (temp DB files)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


def _temp_db() -> str:
    fd, path = tempfile.mkstemp(prefix="ai_companion_test_", suffix=".db")
    import os

    os.close(fd)
    return path


class DatabaseLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.database.database import reset_database

        self._path = _temp_db()
        self.db = reset_database(self._path)

    def tearDown(self) -> None:
        from app.database.database import reset_database
        from app.core.config import Config

        reset_database(Config.DB_PATH)
        try:
            Path(self._path).unlink(missing_ok=True)
        except Exception:
            pass

    def test_settings_roundtrip(self) -> None:
        from app.database.repositories import SettingsRepository

        repo = SettingsRepository(self.db)
        self.assertEqual(repo.get("theme", "dark"), "dark")
        repo.set("theme", "light")
        self.assertEqual(repo.get("theme"), "light")
        repo.set("theme", "dark")
        self.assertEqual(repo.all()["theme"], "dark")

    def test_messages_crud(self) -> None:
        from app.database.repositories import MessageRepository

        repo = MessageRepository(self.db)
        self.assertEqual(repo.list_messages(), [])
        repo.add_message("user", "hello")
        repo.add_message("assistant", "hi", is_error=False)
        rows = repo.list_messages()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["role"], "user")
        repo.clear()
        self.assertEqual(repo.list_messages(), [])

    def test_errors_crud_and_delete(self) -> None:
        from app.database.repositories import ErrorRepository

        repo = ErrorRepository(self.db)
        row_id = repo.add("Python", "NameError: x", "means", "fix", error_type="NameError")
        self.assertGreater(row_id, 0)
        self.assertEqual(repo.count(), 1)
        fetched = repo.get(row_id)
        assert fetched is not None
        self.assertEqual(fetched["error_type"], "NameError")
        repo.delete(row_id)
        self.assertEqual(repo.count(), 0)
        self.assertIsNone(repo.get(row_id))

    def test_retention_purge(self) -> None:
        from app.database.repositories import ErrorRepository

        repo = ErrorRepository(self.db)
        repo.add("Python", "E1", "m", "s")
        old = (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")
        self.db.execute("UPDATE detected_errors SET created_at = ?", (old,))
        removed = repo.purge_older_than(30)
        self.assertEqual(removed, 1)
        self.assertEqual(repo.count(), 0)

    def test_retention_zero_disables(self) -> None:
        from app.database.repositories import ErrorRepository

        repo = ErrorRepository(self.db)
        repo.add("Python", "E1", "m", "s")
        self.assertEqual(repo.purge_older_than(0), 0)
        self.assertEqual(repo.count(), 1)

    def test_events_log(self) -> None:
        from app.database.repositories import EventRepository

        repo = EventRepository(self.db)
        repo.log("app.startup", "vtest")
        rows = repo.list_recent()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "app.startup")


class SessionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.core.state import app_state

        self._old_retention = app_state.history_retention_days
        app_state.history_retention_days = 30
        self._path = _temp_db()
        from app.database.database import reset_database
        from app.core.session import reset_session_store

        reset_database(self._path)
        self.store = reset_session_store(self._path)

    def tearDown(self) -> None:
        from app.core.state import app_state
        from app.core.config import Config
        from app.database.database import reset_database
        from app.core.session import reset_session_store

        app_state.history_retention_days = self._old_retention
        reset_database(Config.DB_PATH)
        reset_session_store(Config.DB_PATH)
        try:
            Path(self._path).unlink(missing_ok=True)
        except Exception:
            pass

    def test_messages_persist_across_reload(self) -> None:
        from app.core.session import reset_session_store

        self.store.add_message("user", "persist me")
        reloaded = reset_session_store(self._path)
        texts = [m.text for m in reloaded.messages]
        self.assertIn("persist me", texts)

    def test_issues_persist_and_delete(self) -> None:
        from app.core.session import reset_session_store

        issue = self.store.add_issue("Python", "E", "m", "s", error_type="NameError")
        reloaded = reset_session_store(self._path)
        self.assertIsNotNone(reloaded.get_issue(issue.id))
        reloaded.delete_issue(issue.id)
        again = reset_session_store(self._path)
        self.assertIsNone(again.get_issue(issue.id))

    def test_clear_all(self) -> None:
        self.store.add_message("user", "x")
        self.store.add_issue("Python", "E", "m", "s")
        self.store.clear_all_local_data()
        # Greeting message remains, issues cleared.
        self.assertEqual(self.store.issues, [])
        self.assertTrue(any("cleared" in m.text.lower() or "companion" in m.text.lower() for m in self.store.messages))

    def test_fresh_store_has_no_seed_issues(self) -> None:
        # No fake detections: a fresh database starts with empty history.
        # The welcome greeting lives in memory only (never stored as an issue).
        self.assertEqual(self.store.issues, [])
        self.assertTrue(any("companion" in m.text.lower() for m in self.store.messages))


class SettingsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._path = _temp_db()
        from app.database.database import reset_database

        reset_database(self._path)

    def tearDown(self) -> None:
        from app.core.config import Config
        from app.database.database import reset_database

        reset_database(Config.DB_PATH)
        try:
            Path(self._path).unlink(missing_ok=True)
        except Exception:
            pass

    def test_save_and_load_roundtrip(self) -> None:
        from app.core.state import app_state
        from app.services.settings_service import load_persisted_settings, save_persisted_settings

        old_theme, old_model = app_state.theme, app_state.ai_model
        try:
            app_state.theme = "light"
            app_state.ai_model = "gpt-4o"
            app_state.history_retention_days = 7
            save_persisted_settings()
            app_state.theme = "dark"
            app_state.ai_model = "gpt-4o-mini"
            app_state.history_retention_days = 30
            load_persisted_settings()
            self.assertEqual(app_state.theme, "light")
            self.assertEqual(app_state.ai_model, "gpt-4o")
            self.assertEqual(app_state.history_retention_days, 7)
        finally:
            app_state.theme = old_theme
            app_state.ai_model = old_model
            app_state.history_retention_days = 30

    def test_retention_zero_survives_reload(self) -> None:
        """BUG-1: 0 means 'keep forever' and must round-trip (was reset to 30)."""
        from app.core.state import app_state
        from app.services.settings_service import load_persisted_settings, save_persisted_settings

        old_retention = app_state.history_retention_days
        try:
            app_state.history_retention_days = 0
            save_persisted_settings()
            app_state.history_retention_days = 30
            load_persisted_settings()
            self.assertEqual(app_state.history_retention_days, 0)
        finally:
            app_state.history_retention_days = old_retention

    def test_companion_prefs_survive_reload(self) -> None:
        """BUG-3: companion size and always-on-top must round-trip."""
        from app.core.state import app_state
        from app.services.settings_service import load_persisted_settings, save_persisted_settings

        old_size, old_top = app_state.companion_size, app_state.companion_always_on_top
        try:
            app_state.companion_size = 150
            app_state.companion_always_on_top = False
            save_persisted_settings()
            app_state.companion_size = 128
            app_state.companion_always_on_top = True
            load_persisted_settings()
            self.assertEqual(app_state.companion_size, 150)
            self.assertFalse(app_state.companion_always_on_top)
        finally:
            app_state.companion_size, app_state.companion_always_on_top = old_size, old_top


if __name__ == "__main__":
    unittest.main()
