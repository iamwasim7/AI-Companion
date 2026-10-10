"""Dashboard notification card tests (offscreen Qt, no network)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class DashboardNotifTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_view_scrolls_to_analysis_and_buttons_sized(self) -> None:
        from unittest.mock import patch

        from PySide6.QtWidgets import QPushButton

        from app.services.notification_service import get_notification_service
        from app.ui.dashboard import DashboardPage

        svc = get_notification_service()
        created = svc.notify("T err", "Some body text", signature="dash-test-sig")
        self.assertIsNotNone(created)
        assert created is not None
        try:
            from PySide6.QtWidgets import QApplication, QPushButton

            page = DashboardPage()
            page.refresh()

            def laid_out_buttons():
                found: list = []
                layout = page._notif_card.body
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    widget = item.widget() if item is not None else None
                    if widget is not None:
                        found.extend(widget.findChildren(QPushButton))
                return found

            buttons = laid_out_buttons()
            texts = sorted(b.text() for b in buttons)
            self.assertEqual(texts, ["Dismiss", "View"])
            for button in buttons:
                self.assertGreaterEqual(button.minimumWidth(), 84)
                # Text must never be clipped: the button must be allowed to
                # reach at least its font-derived height (fixed heights
                # clipped descenders on scaled displays).
                self.assertGreaterEqual(
                    button.maximumHeight(), button.sizeHint().height()
                )
            view = next(b for b in buttons if b.text() == "View")
            with patch.object(
                page._scroll, "ensureWidgetVisible"
            ) as ensure_visible:
                view.click()
            ensure_visible.assert_called_once_with(page._analysis_card)
        finally:
            svc.dismiss(created.id)

    def test_main_window_bootstraps_monitor_service(self) -> None:
        # Regression: Start Monitoring must always have a live subscriber,
        # even though no page constructs the service anymore.
        from app.core.events import bus
        from app.ui.main_window import MainWindow

        window = MainWindow()
        try:
            starters = bus._subscribers.get("monitoring.start", [])
            self.assertTrue(
                starters,
                "no subscriber for monitoring.start after app boot",
            )
            window._pages["monitoring"]._toggle_monitoring()
            from app.core.state import app_state

            self.assertTrue(app_state.monitoring_enabled)
            window._pages["monitoring"]._toggle_monitoring()
            self.assertFalse(app_state.monitoring_enabled)
        finally:
            window.close()

    def test_companion_chip_follows_visibility(self) -> None:
        # Regression: hiding the companion must flip the chip text to
        # "Hidden" and the tone to red ("off", like the Monitoring chip).
        from app.core.state import app_state
        from app.ui.dashboard import DashboardPage

        page = DashboardPage()
        old_visible = app_state.companion_visible
        old_state = app_state.companion_state
        try:
            app_state.companion_visible = True
            app_state.set_companion_state("IDLE")
            page.refresh()
            self.assertEqual(page._companion_chip.text(), "Companion: Idle · Visible")
            self.assertEqual(page._companion_chip.property("tone"), "ok")
            app_state.companion_visible = False
            page.refresh()
            self.assertEqual(page._companion_chip.text(), "Companion: Idle · Hidden")
            self.assertEqual(page._companion_chip.property("tone"), "off")
        finally:
            app_state.companion_visible = old_visible
            app_state.set_companion_state(old_state)
            page.refresh()

    def test_status_chips_use_title_case(self) -> None:
        # All three status chips use Title Case consistently.
        from app.core.state import app_state
        from app.ui.dashboard import DashboardPage

        page = DashboardPage()
        old = (
            app_state.monitoring_enabled,
            app_state.monitoring_paused,
            app_state.companion_visible,
            app_state.companion_state,
        )
        try:
            app_state.monitoring_enabled = False
            app_state.monitoring_paused = False
            app_state.companion_visible = True
            app_state.set_companion_state("IDLE")
            page.refresh()
            self.assertEqual(page._monitor_chip.text(), "Monitoring: Off")
            self.assertEqual(page._companion_chip.text(), "Companion: Idle · Visible")
            self.assertTrue(page._ai_chip.text().startswith(("AI: Mock Mode", "AI: Live")))
            self.assertIn("Key ", page._ai_chip.text())
            app_state.monitoring_enabled = True
            app_state.monitoring_paused = True
            page.refresh()
            self.assertEqual(page._monitor_chip.text(), "Monitoring: Paused")
        finally:
            (
                app_state.monitoring_enabled,
                app_state.monitoring_paused,
                app_state.companion_visible,
                app_state.companion_state,
            ) = old
            page.refresh()

    def test_card_headings_match_analysis_title_weight(self) -> None:
        # Card headings ("Recent issues", ...) must use the same bold
        # weight (700) as the "AI Error Analysis" title — 600 rendered
        # as regular text on some systems.
        from PySide6.QtWidgets import QLabel

        from app.ui.dashboard import DashboardPage

        page = DashboardPage()
        page.refresh()
        # The analysis card carries the AnalysisPanel (titled separately);
        # the other three cards get plain headings from _clear_card.
        for card in (page._issues_card, page._notif_card, page._chat_card):
            heading = card.body.itemAt(0).widget()
            self.assertIsInstance(heading, QLabel)
            self.assertIn("700", heading.styleSheet())


if __name__ == "__main__":
    unittest.main()
