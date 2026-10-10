"""Avatar tests: registry, file resolution, persistence, selection UI."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class AvatarRegistryTests(unittest.TestCase):
    def test_registry_covers_all_choices(self) -> None:
        from app.ui.companion import AVATAR_CLASSIC, AVATAR_LABELS, AVATARS

        self.assertEqual(AVATAR_CLASSIC, "classic")
        self.assertEqual(
            AVATARS,
            ("classic", "cat_orange", "cat_black", "dog_golden", "turtle", "gecko"),
        )
        self.assertEqual(set(AVATAR_LABELS), set(AVATARS))

    def test_resolve_avatar_path(self) -> None:
        import tempfile
        from pathlib import Path

        from app.ui.companion import resolve_avatar_path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertIsNone(resolve_avatar_path("classic", base))
            self.assertIsNone(resolve_avatar_path("dragon", base))
            self.assertIsNone(resolve_avatar_path("cat_orange", base))
            (base / "cat_orange.png").write_bytes(b"fake-png")
            self.assertEqual(resolve_avatar_path("cat_orange", base), base / "cat_orange.png")

    def test_missing_files_fall_back_to_classic(self) -> None:
        import tempfile
        from pathlib import Path

        from app.ui.companion import AVATARS, resolve_avatar_path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)  # empty: none of the five PNGs exist
            for name in AVATARS:
                if name != "classic":
                    self.assertIsNone(resolve_avatar_path(name, base))


class AvatarPersistenceTests(unittest.TestCase):
    def test_avatar_survives_reload(self) -> None:
        from app.core.state import app_state
        from app.services.settings_service import load_persisted_settings, save_persisted_settings

        old_avatar = app_state.companion_avatar
        try:
            app_state.companion_avatar = "turtle"
            save_persisted_settings()
            app_state.companion_avatar = "classic"
            load_persisted_settings()
            self.assertEqual(app_state.companion_avatar, "turtle")
        finally:
            app_state.companion_avatar = old_avatar
            save_persisted_settings()

    def test_invalid_avatar_rejected_on_load(self) -> None:
        from app.core.state import app_state
        from app.database.database import get_database
        from app.database.repositories import SettingsRepository
        from app.services.settings_service import load_persisted_settings

        repo = SettingsRepository(get_database())
        previous = repo.all().get("companion_avatar", "")
        old_avatar = app_state.companion_avatar
        try:
            repo.set("companion_avatar", "dragon")
            app_state.companion_avatar = "classic"
            load_persisted_settings()
            self.assertEqual(app_state.companion_avatar, "classic")
        finally:
            repo.set("companion_avatar", previous)
            app_state.companion_avatar = old_avatar


class AvatarSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_settings_dropdown_lists_all_avatars(self) -> None:
        from PySide6.QtWidgets import QComboBox

        from app.ui.companion import AVATARS
        from app.ui.settings_page import SettingsPage

        page = SettingsPage()
        try:
            combos = page.findChildren(QComboBox)
            item_sets = [{c.itemText(i) for i in range(c.count())} for c in combos]
            labels = set()
            from app.ui.companion import AVATAR_LABELS

            labels = set(AVATAR_LABELS.values())
            self.assertTrue(any(labels <= items for items in item_sets))
            self.assertTrue(any(set(AVATARS) <= {c.itemData(i) for i in range(c.count())} for c in combos))
        finally:
            page.deleteLater()

    def test_companion_applies_avatar_event(self) -> None:
        from app.core.events import bus
        from app.core.state import app_state
        from app.ui.companion import FloatingCompanion

        old_avatar = app_state.companion_avatar
        app_state.companion_avatar = "classic"
        comp = FloatingCompanion()
        try:
            self.assertIsNone(comp._avatar_pixmap)  # classic paints, loads nothing
            bus.emit("companion.avatar", name="turtle")
            self.assertEqual(app_state.companion_avatar, "turtle")
            self.assertIsNotNone(comp._avatar_pixmap)  # shipped PNG loads
            self.assertFalse(comp._avatar_pixmap.isNull())
            bus.emit("companion.avatar", name="dragon")
            self.assertEqual(app_state.companion_avatar, "classic")
            self.assertIsNone(comp._avatar_pixmap)  # unknown falls back
        finally:
            app_state.companion_avatar = old_avatar
            comp.deleteLater()


class ResourceBaseTests(unittest.TestCase):
    """Bundled-asset lookup must survive PyInstaller one-dir layout."""

    def test_unfrozen_uses_project_root(self) -> None:
        from app.core import config as config_mod

        self.assertEqual(
            config_mod.resource_base(), config_mod.PROJECT_ROOT
        )

    def test_frozen_prefers_bundle_dir_with_assets(self) -> None:
        import sys
        import tempfile
        from pathlib import Path
        from unittest import mock

        from app.core import config as config_mod

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "_internal"
            (bundle / "assets").mkdir(parents=True)
            with (
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "_MEIPASS", str(bundle), create=True),
            ):
                self.assertEqual(config_mod.resource_base(), bundle)

    def test_frozen_falls_back_to_exe_dir(self) -> None:
        import sys
        import tempfile
        from pathlib import Path
        from unittest import mock

        from app.core import config as config_mod

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "_internal"  # no assets/ inside
            bundle.mkdir()
            with (
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "_MEIPASS", str(bundle), create=True),
            ):
                self.assertEqual(config_mod.resource_base(), config_mod.PROJECT_ROOT)

    def test_avatar_dir_points_at_companion_assets(self) -> None:
        from app.ui.companion import avatar_dir

        self.assertEqual(avatar_dir().name, "companion")
        self.assertEqual(avatar_dir().parent.name, "assets")

    def test_all_avatars_paint_without_crash(self) -> None:
        from app.core.state import app_state
        from app.ui.companion import AVATARS, FloatingCompanion

        old_avatar = app_state.companion_avatar
        old_state = app_state.companion_state
        try:
            for name in AVATARS:
                app_state.companion_avatar = name
                for state in ("IDLE", "ALERT", "ERROR"):
                    app_state.set_companion_state(state)
                    comp = FloatingCompanion()
                    try:
                        comp.resize(128, 128)
                        comp.show()
                        grabbed = comp.grab()
                        self.assertFalse(grabbed.isNull(), f"{name}/{state}")
                    finally:
                        comp.deleteLater()
        finally:
            app_state.companion_avatar = old_avatar
            app_state.set_companion_state(old_state)


if __name__ == "__main__":
    unittest.main()
