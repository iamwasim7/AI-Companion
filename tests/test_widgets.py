"""Widget behavior tests (offscreen Qt, no network)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class NoWheelComboBoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_is_drop_in_qcombobox(self) -> None:
        from PySide6.QtWidgets import QComboBox

        from app.ui.widgets.common import NoWheelComboBox

        combo = NoWheelComboBox()
        try:
            self.assertIsInstance(combo, QComboBox)
            combo.addItems(["a", "b", "c"])
            combo.setCurrentIndex(0)
            combo.setCurrentIndex(2)  # programmatic + click selection still work
            self.assertEqual(combo.currentIndex(), 2)
        finally:
            combo.deleteLater()

    def test_wheel_leaves_selection_untouched(self) -> None:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtCore import QPoint

        from app.ui.widgets.common import NoWheelComboBox

        combo = NoWheelComboBox()
        try:
            combo.addItems(["dark", "light", "cursor"])
            combo.setCurrentIndex(0)
            event = QWheelEvent(
                QPointF(5, 5),
                QPointF(5, 5),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            combo.wheelEvent(event)
            self.assertEqual(combo.currentIndex(), 0)
            self.assertFalse(event.isAccepted())  # propagates to the scroll area
        finally:
            combo.deleteLater()

    def test_settings_and_monitoring_use_no_wheel_combos(self) -> None:
        from PySide6.QtWidgets import QComboBox

        from app.ui.monitoring_page import MonitoringPage
        from app.ui.settings_page import SettingsPage
        from app.ui.widgets.common import NoWheelComboBox

        for page in (SettingsPage(), MonitoringPage()):
            try:
                combos = page.findChildren(QComboBox)
                self.assertTrue(combos)
                for combo in combos:
                    self.assertIsInstance(
                        combo,
                        NoWheelComboBox,
                        f"plain QComboBox steals wheel scrolls: {combo}",
                    )
            finally:
                page.deleteLater()


if __name__ == "__main__":
    unittest.main()
