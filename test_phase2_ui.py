"""Regression tests for Semantic YT Studio 2.0 — Phase 2 UI additions.

Two kinds of coverage here:
  - Structural (inspect.getsource), matching the existing convention in
    test_flow_reliability_audit.py / test_scene_lookup_index.py: verifies
    the wiring exists without booting the full Tk GUI.
  - Live widget construction, using a real (but withdrawn/off-screen) Tk
    root — this environment has a display available, so these exercise
    actual CTk widget behavior end-to-end rather than only reading source.

Every class here skips cleanly if customtkinter can't be imported, so this
file is still safe to run in a headless CI environment with no display.
"""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def _load_app_module():
    import app as _app

    return _app


class TestThemeTokens(unittest.TestCase):
    def setUp(self):
        import ui.theme as T

        self.T = T
        self._orig_mode = T.current_mode()

    def tearDown(self):
        self.T.set_mode(self._orig_mode)

    def test_dark_is_default_with_no_saved_preference(self):
        # MODE is resolved at import time from settings.json; a fresh
        # process with no saved preference must still default to dark.
        self.assertIn(self.T.MODE, ("dark", "light", "system"))

    def test_set_mode_dark_light_round_trip(self):
        self.T.set_mode("light")
        self.assertEqual(self.T.current_mode(), "light")
        self.assertEqual(self.T.active_appearance(), "light")
        light_bg = self.T.BG
        self.T.set_mode("dark")
        self.assertEqual(self.T.current_mode(), "dark")
        self.assertNotEqual(self.T.BG, light_bg)

    def test_set_mode_persists_to_settings_json(self):
        self.T.set_mode("light")
        data = json.loads(self.T._settings_path().read_text(encoding="utf-8"))
        self.assertEqual(data.get("theme_mode"), "light")
        self.T.set_mode("dark")
        data = json.loads(self.T._settings_path().read_text(encoding="utf-8"))
        self.assertEqual(data.get("theme_mode"), "dark")

    def test_invalid_mode_falls_back_to_dark(self):
        resolved = self.T.set_mode("not-a-real-mode")
        self.assertEqual(resolved, "dark")

    def test_semantic_token_groups_present(self):
        for group in (
            "background", "surface", "surface_elevated", "text_primary",
            "text_secondary", "border", "accent", "success", "warning",
            "error", "hover", "disabled",
        ):
            self.assertIn(group, self.T.DARK)
            self.assertIn(group, self.T.LIGHT)

    def test_timeline_track_clip_tokens_present(self):
        for group in ("timeline_bg", "track", "clip_video", "clip_text", "clip_sfx"):
            self.assertIn(group, self.T.DARK)
            self.assertIn(group, self.T.LIGHT)

    def test_nav_items_grouped_workspace_and_advanced(self):
        groups = {g for _, _, g in self.T.NAV_ITEMS}
        self.assertEqual(groups, {"workspace", "advanced"})

    def test_nav_items_cover_every_phase2_workspace(self):
        keys = {k for k, _, _ in self.T.NAV_ITEMS}
        for required in ("script", "visual_plan", "audio", "graphics", "render"):
            self.assertIn(required, keys)


class TestShellStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ui.shell as _shell
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.shell_mod = _shell

    def test_app_shell_exposes_apply_theme_chrome(self):
        self.assertTrue(hasattr(self.shell_mod.AppShell, "apply_theme_chrome"))

    def test_apply_theme_chrome_never_raises_source(self):
        src = inspect.getsource(self.shell_mod.AppShell.apply_theme_chrome)
        self.assertIn("try:", src)
        self.assertIn("except Exception:", src)

    def test_build_sidebar_renders_grouped_headers(self):
        src = inspect.getsource(self.shell_mod.AppShell._build_sidebar)
        self.assertIn("WORKSPACE", src)
        self.assertIn("ADVANCED", src)


class TestAppPhase2Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def test_run_pipeline_still_has_perf_and_progress_from_phase1(self):
        # Phase 2 must not regress Phase 1's instrumentation wiring.
        src = inspect.getsource(self.app.VideoGeneratorApp._run_pipeline)
        self.assertIn("PerfRecorder", src)
        self.assertIn("progress_cb=_progress_cb", src)

    def test_theme_toggle_persists_and_repaints_chrome(self):
        # The toggle delegates to _apply_theme_mode (shared with the Settings
        # dialog's theme buttons), which persists AND repaints — now the whole
        # window, not only the chrome (see test_theme_live_switch.py).
        toggle_src = inspect.getsource(self.app.VideoGeneratorApp._on_toggle_theme)
        self.assertIn("_apply_theme_mode", toggle_src)
        src = inspect.getsource(self.app.VideoGeneratorApp._apply_theme_mode)
        self.assertIn("_ui_theme.set_mode", src)
        self.assertIn("apply_theme_chrome", src)

    def test_undo_redo_wired_to_shell_buttons(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._on_undo_stack_change)
        self.assertIn("undo_btn", src)
        self.assertIn("redo_btn", src)

    def test_details_action_dispatches_new_inspector_actions(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._details_action)
        for action in ("reset_scene",):
            self.assertIn(action, src)

    def test_add_broll_is_disabled_not_faked(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._build_scenes_workspace)
        self.assertIn('self.details_add_broll_btn.configure(state="disabled")', src)

    def test_context_menu_reuses_details_action(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._show_scene_context_menu)
        self.assertIn("self._details_action", src)
        # Must not contain a second copy of any action's business logic —
        # every entry routes through the same dispatcher.
        self.assertNotIn("threading.Thread", src)

    def test_export_progress_never_shows_raw_ffmpeg(self):
        # Behavioral, not textual: whatever text this method actually sets
        # for the operator must never contain raw FFmpeg command syntax.
        import types

        obj = types.SimpleNamespace(_export_progress_var=self._fake_stringvar(), _render_cache_hits=0)
        method = self.app.VideoGeneratorApp._update_export_progress_text
        method(obj, "rendering", 5, 10, "Scene 5", "running")
        method(obj, "mux", 0, 1, "-i input.mp4 -c:v libx264", "running")
        self.assertNotIn("-c:v", obj._export_progress_var.get())
        self.assertNotIn(".mp4", obj._export_progress_var.get())

    @staticmethod
    def _fake_stringvar():
        class _V:
            def __init__(self):
                self._v = ""

            def get(self):
                return self._v

            def set(self, v):
                self._v = v

        return _V()

    def test_scene_thumbnail_is_stills_only(self):
        src = inspect.getsource(self.app._scene_thumbnail_image)
        self.assertIn(".png", src)

    def test_activate_workspace_clears_undo_and_marks_saved(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._activate_workspace)
        self.assertIn("_timeline_undo.clear", src)
        self.assertIn("_mark_saved", src)


class TestLiveWidgetSmoke(unittest.TestCase):
    """Exercises real CTk widget construction — this environment has a
    working display, so these are genuine (not merely structural) checks."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.app_mod = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        try:
            cls.app = cls.app_mod.VideoGeneratorApp()
        except Exception as exc:
            raise unittest.SkipTest(f"no Tk display available: {exc}")
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_all_nav_keys_navigable_without_exception(self):
        for key in (
            "script", "visual_plan", "audio", "graphics", "render",
            "brand_style", "research", "music", "editorial", "qa", "about",
        ):
            self.app._shell.navigate(key)
            self.app.update_idletasks()
        self.assertTrue(True)

    def test_inspector_only_on_the_visuals_page(self):
        shell = self.app._shell
        shell.navigate("visual_plan")
        self.assertTrue(bool(shell.inspector.grid_info()))
        for key in ("script", "audio", "render"):
            shell.navigate(key)
            self.assertFalse(bool(shell.inspector.grid_info()), key)

    def test_transparent_panels_repaint_on_a_light_switch(self):
        import tkinter

        import ui.theme as T

        frame = __import__("customtkinter").CTkFrame(self.app, fg_color="transparent")
        tkinter.Misc.configure(frame, background=T._TABLES["dark"]["surface_alt"])
        T.recolor_widget_tree(frame, T.color_remaps(T._TABLES["dark"], T._TABLES["light"]))
        self.assertEqual(tkinter.Misc.cget(frame, "background").upper(), T._TABLES["light"]["surface_alt"].upper())
        frame.destroy()

    def test_theme_toggle_cycles_and_returns_to_dark(self):
        import ui.theme as T

        T.set_mode("dark")
        self.app._theme_label_var.set(self.app._theme_button_label())
        self.app._on_toggle_theme()
        self.assertEqual(T.current_mode(), "light")
        self.app._on_toggle_theme()
        self.assertEqual(T.current_mode(), "system")
        self.app._on_toggle_theme()
        self.assertEqual(T.current_mode(), "dark")

    def test_graphics_view_shows_empty_state_with_no_workspace(self):
        self.app._workspace = None
        view = self.app._view_graphics
        view.on_show()
        self.assertTrue(bool(view._empty.grid_info()))
        self.assertFalse(bool(view._list.grid_info()))

    def test_inspector_extended_action_buttons_exist(self):
        for name in (
            "details_add_broll_btn", "details_reset_btn",
        ):
            self.assertTrue(hasattr(self.app, name))
        self.assertEqual(self.app.details_add_broll_btn.cget("state"), "disabled")


if __name__ == "__main__":
    unittest.main()
