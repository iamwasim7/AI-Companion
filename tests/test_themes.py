"""Theme tests: palette completeness, stylesheet output, UI availability."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

EXPECTED_THEMES = {"dark", "light", "cursor", "midnight", "palenight", "vercel"}


class PaletteTests(unittest.TestCase):
    def test_all_palettes_share_key_set(self) -> None:
        from app.ui.styles import THEMES

        self.assertEqual(set(THEMES), EXPECTED_THEMES)
        key_sets = [set(palette) for palette in THEMES.values()]
        for keys in key_sets[1:]:
            self.assertEqual(keys, key_sets[0])

    def test_stylesheet_contains_palette_colors(self) -> None:
        from app.ui.styles import THEMES, build_stylesheet

        for name, palette in THEMES.items():
            css = build_stylesheet(name)
            self.assertTrue(css.strip())
            self.assertIn(palette["bg"], css)
            self.assertIn(palette["accent"], css)
            self.assertIn("Segoe UI", css)

    def test_unknown_theme_falls_back_to_dark(self) -> None:
        from app.ui.styles import DARK, build_stylesheet

        css = build_stylesheet("neon")
        self.assertIn(DARK["bg"], css)

    def test_list_items_use_readable_text_color(self) -> None:
        # Regression (vercel theme): history list items rendered dim
        # because QListWidget::item had no explicit color. Every theme
        # must paint items (and selected items) in readable tones.
        import re

        from app.ui.styles import THEMES, build_stylesheet

        for name in THEMES:
            css = build_stylesheet(name)
            self.assertRegex(
                css, r"QListWidget::item\s*\{[^}]*color\s*:",
                f"no item text color in {name}",
            )
            self.assertRegex(
                css, r"QListWidget::item:selected\s*\{[^}]*color\s*:",
                f"no selected-item text color in {name}",
            )


class ThemeApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_apply_each_theme_without_crash(self) -> None:
        from PySide6.QtWidgets import QWidget

        from app.ui.styles import THEMES, apply_theme

        for name in THEMES:
            widget = QWidget()
            apply_theme(widget, name)
            self.assertTrue(widget.styleSheet().strip())
            widget.deleteLater()

    def test_settings_lists_all_themes(self) -> None:
        from PySide6.QtWidgets import QComboBox

        from app.ui.settings_page import SettingsPage

        page = SettingsPage()
        try:
            combos = page.findChildren(QComboBox)
            item_sets = [
                {combo.itemText(i) for i in range(combo.count())}
                for combo in combos
            ]
            lowered_sets = [{t.lower() for t in items} for items in item_sets]
            self.assertTrue(
                any(EXPECTED_THEMES <= items for items in lowered_sets),
                "no theme dropdown lists all four themes",
            )
            # Display labels must be Title Case (Dark, Light, ...).
            for items in item_sets:
                if EXPECTED_THEMES <= {t.lower() for t in items}:
                    for text in items:
                        if text.lower() in EXPECTED_THEMES:
                            self.assertEqual(
                                text[0], text[0].upper(), f"theme label not capitalized: {text!r}"
                            )
        finally:
            page.deleteLater()

    def test_settings_dropdowns_use_title_case_labels(self) -> None:
        # Regression: AI mode / explanation style showed lowercase
        # ("mock", "beginner"). Labels must be Title Case while the
        # saved values stay lowercase.
        from PySide6.QtWidgets import QComboBox

        from app.core.state import app_state
        from app.ui.settings_page import SettingsPage

        old_behavior, old_theme = app_state.ai_behavior, app_state.theme
        try:
            app_state.ai_behavior = "concise"
            app_state.theme = "light"
            page = SettingsPage()
            try:
                combos = page.findChildren(QComboBox)
                texts = [{c.itemText(i) for i in range(c.count())} for c in combos]
                self.assertTrue(
                    any({"Mock", "Live"} <= t for t in texts),
                    "AI mode dropdown missing Title-Case Mock/Live",
                )
                self.assertTrue(
                    any({"Beginner", "Concise", "Detailed"} <= t for t in texts),
                    "behavior dropdown missing Title-Case options",
                )
                for combo in combos:
                    labels = [combo.itemText(i) for i in range(combo.count())]
                    if "Mock" in labels:
                        self.assertEqual(
                            [combo.itemData(i) for i in range(combo.count())],
                            ["mock", "live"],
                        )
                    if "Beginner" in labels:
                        self.assertEqual(
                            [combo.itemData(i) for i in range(combo.count())],
                            ["beginner", "concise", "detailed"],
                        )
                self.assertEqual(page._behavior.currentData(), "concise")
                self.assertEqual(page._theme.currentData(), "light")
                self.assertEqual(app_state.ai_behavior, "concise")
                self.assertEqual(app_state.theme, "light")
            finally:
                page.deleteLater()
        finally:
            app_state.ai_behavior, app_state.theme = old_behavior, old_theme


class AnalysisPanelThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_analysis_title_readable_in_all_themes(self) -> None:
        # Regression (light mode): "AI Error Analysis" used hardcoded
        # near-white #f0f6fc, invisible on white cards.
        from app.core.state import app_state
        from app.ui.analysis_panel import AnalysisPanel
        from app.ui.styles import THEMES

        old_theme = app_state.theme
        try:
            for name, palette in THEMES.items():
                app_state.theme = name
                panel = AnalysisPanel()
                try:
                    title_css = panel._title.styleSheet().lower()
                    self.assertIn(
                        palette["title"].lower(), title_css,
                        f"title missing theme title color in {name}",
                    )
                    self.assertNotEqual(
                        palette["title"].lower(), palette["card"].lower(),
                        f"title equals card bg in {name}",
                    )
                    if name == "light":
                        self.assertNotIn(
                            "#f0f6fc", title_css,
                            "hardcoded dark title color leaks into light mode",
                        )
                finally:
                    panel.deleteLater()
        finally:
            app_state.theme = old_theme

    def test_analysis_result_widgets_follow_theme(self) -> None:
        # Section/body/code widgets must use the active palette and
        # refresh on theme.changed (walk live layouts: offscreen Qt
        # never delivers deleteLater, so no findChildren).
        from app.ai.response_parser import ErrorAnalysis
        from app.core.events import bus
        from app.core.state import app_state
        from app.ui.analysis_panel import AnalysisPanel
        from app.ui.styles import THEMES

        old_theme = app_state.theme
        try:
            app_state.theme = "dark"
            panel = AnalysisPanel()
            try:
                result = ErrorAnalysis(
                    error_type="NameError",
                    problem="Undefined variable username.",
                    explanation="Some explanation.",
                    cause="Some cause.",
                    solution="Define username first.",
                    corrected_code="username = 'ada'",
                    confidence=0.9,
                    is_fallback=False,
                )
                panel._render_result(result)
                app_state.theme = "light"
                bus.emit("theme.changed")
                light = THEMES["light"]
                self.assertIn(light["title"].lower(), panel._title.styleSheet().lower())
                layout = panel._result_layout
                self.assertGreater(layout.count(), 3)
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    widget = item.widget() if item is not None else None
                    if widget is None:
                        continue
                    css = widget.styleSheet().lower()
                    if not css.strip():
                        continue
                    self.assertNotIn(
                        "#f0f6fc", css,
                        f"hardcoded dark color in light mode: {type(widget).__name__}",
                    )
                    self.assertNotIn(
                        "#c9d1d9", css,
                        f"hardcoded section color in light mode: {type(widget).__name__}",
                    )
            finally:
                panel.deleteLater()
        finally:
            app_state.theme = old_theme
            bus.emit("theme.changed")


if __name__ == "__main__":
    unittest.main()
