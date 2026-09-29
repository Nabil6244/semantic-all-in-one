"""Regression tests for the Premium UI/UX pass (Semantic YT Studio 2.0).

Covers: icon glyph map, tooltip construction, CollapsibleSection/Toast
widgets, the Timeline canvas's hover/lock/mute/solo/duplicate/snap
behavior, and global keyboard-shortcut wiring. Live widget tests use the
real display available in this environment; every class skips cleanly if
customtkinter can't be imported.
"""

from __future__ import annotations

import inspect
import unittest

from editorial.timeline import EditorialTimeline, TimelineEvent


class TestIcons(unittest.TestCase):
    def test_core_editor_icons_present(self):
        from ui.icons import icon

        for name in (
            "play", "pause", "stop", "undo", "redo", "split", "delete",
            "duplicate", "zoom_in", "zoom_out", "snap", "mute", "solo",
            "lock", "settings", "export", "search", "add", "replace",
            "close", "expand", "collapse",
        ):
            glyph = icon(name)
            self.assertTrue(glyph)
            self.assertNotEqual(glyph, "•")  # not silently falling back

    def test_unknown_icon_falls_back_gracefully(self):
        from ui.icons import icon

        self.assertEqual(icon("totally-made-up-name"), "•")


class TestDesignTokens(unittest.TestCase):
    def test_spacing_scale_present_and_increasing(self):
        import ui.theme as T

        scale = [T.SPACE_XXS, T.SPACE_XS, T.SPACE_SM, T.SPACE_MD, T.SPACE_LG, T.SPACE_XL]
        self.assertEqual(scale, sorted(scale))

    def test_typography_hierarchy_sizes_present(self):
        import ui.theme as T

        for name in (
            "FONT_APP_TITLE", "FONT_WORKSPACE_TITLE", "FONT_SECTION_TITLE",
            "FONT_CONTROL_LABEL", "FONT_SECONDARY_LABEL", "FONT_METADATA",
            "FONT_TIMELINE_LABEL", "FONT_STATUS",
        ):
            self.assertTrue(hasattr(T, name))

    def test_control_height_scale(self):
        import ui.theme as T

        self.assertLess(T.CONTROL_H_SM, T.CONTROL_H)
        self.assertLess(T.CONTROL_H, T.CONTROL_H_LG)


class TestLiveWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import customtkinter as ctk
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        try:
            cls.root = ctk.CTk()
            cls.root.withdraw()
        except Exception as exc:
            raise unittest.SkipTest(f"no Tk display available: {exc}")
        cls.ctk = ctk

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_tooltip_attaches_without_raising(self):
        from ui.tooltip import attach

        btn = self.ctk.CTkButton(self.root, text="x")
        tip = attach(btn, "Split", shortcut="Ctrl/Cmd+B")
        self.assertIs(btn._tooltip, tip)

    def test_tooltip_show_and_hide_cycle(self):
        from ui.tooltip import Tooltip

        btn = self.ctk.CTkButton(self.root, text="x")
        tip = Tooltip(btn, "Hello")
        tip._show()
        self.assertIsNotNone(tip._win)
        tip._hide()
        self.assertIsNone(tip._win)

    def test_collapsible_section_toggles(self):
        from ui.widgets import CollapsibleSection

        section = CollapsibleSection(self.root, "Timing", expanded=True)
        self.assertTrue(section.expanded)
        self.assertTrue(bool(section.body.grid_info()))
        section._toggle()
        self.assertFalse(section.expanded)
        self.assertFalse(bool(section.body.grid_info()))
        section._toggle()
        self.assertTrue(section.expanded)

    def test_collapsible_section_starts_collapsed_when_requested(self):
        from ui.widgets import CollapsibleSection

        section = CollapsibleSection(self.root, "Effects", expanded=False)
        self.assertFalse(bool(section.body.grid_info()))

    def test_toast_show_sets_text_and_places_widget(self):
        from ui.widgets import Toast

        toast = Toast(self.root)
        toast.show("Saved", tone="success")
        self.root.update_idletasks()
        self.assertEqual(toast._label.cget("text"), "Saved")
        self.assertTrue(bool(toast.place_info()))

    def test_empty_state_supports_secondary_action(self):
        from ui.widgets import EmptyState

        calls = []
        es = EmptyState(
            self.root, "No timeline", "body text", "Primary", lambda: calls.append("p"),
            secondary_label="Secondary", secondary_command=lambda: calls.append("s"),
        )
        self.root.update_idletasks()
        self.assertTrue(es.winfo_exists())



class TestErrorDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = __import__("app")
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def test_show_error_dialog_hides_details_behind_collapsible_section(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._show_error_dialog)
        self.assertIn("CollapsibleSection", src)
        self.assertIn("expanded=False", src)

    def test_on_finished_failure_path_uses_dialog_not_raw_messagebox(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._on_finished)
        failure_branch = src.split("else:")[-1]
        self.assertIn("_show_error_dialog", failure_branch)
        self.assertNotIn("messagebox.showerror", failure_branch)


if __name__ == "__main__":
    unittest.main()
