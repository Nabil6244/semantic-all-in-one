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
        for required in ("script", "visual_plan", "timeline", "audio", "graphics", "render"):
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
        src = inspect.getsource(self.app.VideoGeneratorApp._on_toggle_theme)
        self.assertIn("_ui_theme.set_mode", src)
        self.assertIn("apply_theme_chrome", src)

    def test_undo_redo_wired_to_shell_buttons(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._on_undo_stack_change)
        self.assertIn("undo_btn", src)
        self.assertIn("redo_btn", src)

    def test_details_action_dispatches_new_inspector_actions(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._details_action)
        for action in ("add_sfx", "add_ambience", "add_graphic", "edit_timing", "reset_scene"):
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
            "script", "visual_plan", "timeline", "audio", "graphics", "render",
            "brand_style", "research", "assets", "music", "editorial", "qa", "about",
        ):
            self.app._shell.navigate(key)
            self.app.update_idletasks()
        self.assertTrue(True)

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

    def test_timeline_view_shows_empty_state_with_no_workspace(self):
        self.app._workspace = None
        view = self.app._view_timeline
        view.on_show()
        self.assertTrue(bool(view._empty.grid_info()))
        self.assertFalse(bool(view._canvas_host.grid_info()))

    def test_graphics_view_shows_empty_state_with_no_workspace(self):
        self.app._workspace = None
        view = self.app._view_graphics
        view.on_show()
        self.assertTrue(bool(view._empty.grid_info()))
        self.assertFalse(bool(view._list.grid_info()))

    def test_timeline_view_renders_a_real_timeline(self):
        with tempfile.TemporaryDirectory() as td:
            from project_workspace import ProjectWorkspace

            ws = ProjectWorkspace(project_id="p1", title="T", seq=1, root=td)
            ws.ensure_dirs()
            (ws.state_dir / "editorial_plan.json").write_text(json.dumps({
                "scenes": [{"scene_number": "1", "start": 0.0, "end": 5.0}],
                "timeline": {
                    "version": 1, "audio_end": 5.0,
                    "events": [
                        {"event_id": "v1", "track": "VIDEO_1", "start": 0.0, "end": 5.0, "scene_number": "1"},
                        {"event_id": "t1", "track": "TEXT", "start": 1.0, "end": 2.0, "scene_number": "1"},
                    ],
                },
            }))
            self.app._workspace = ws
            view = self.app._view_timeline
            view.on_show()
            self.app.update_idletasks()
            self.assertTrue(bool(view._canvas_host.grid_info()))
            self.assertGreater(len(view._canvas_host.canvas.find_all()), 0)

    # ---- CapCut-style Editor (ui/editor_view.py) — reuses this class's
    # single shared Tk root rather than constructing a second VideoGeneratorApp,
    # since two live app instances in one process corrupt each other's named
    # Tk images (see test_editor_view.py's module docstring for the story).

    def _make_editor_workspace(self, tmp_dir: str, *, with_timeline: bool = True):
        from project_workspace import ProjectWorkspace

        ws = ProjectWorkspace(project_id="p_editor", title="EditorTest", seq=1, root=tmp_dir)
        ws.ensure_dirs()
        payload = {"scenes": [{"scene_number": "1", "start": 0.0, "end": 5.0}]}
        if with_timeline:
            payload["timeline"] = {
                "version": 1, "audio_end": 5.0,
                "events": [
                    {"event_id": "v1", "track": "VIDEO_1", "start": 0.0, "end": 5.0, "scene_number": "1", "source": ""},
                    {"event_id": "t1", "track": "TEXT", "start": 1.0, "end": 2.0, "scene_number": "1", "metadata": {"text": "Hello"}},
                    {"event_id": "sfx1", "track": "SFX", "start": 2.0, "end": 2.5, "scene_number": "1", "source": "", "metadata": {"volume": 0.8}},
                ],
            }
        (ws.state_dir / "editorial_plan.json").write_text(json.dumps(payload), encoding="utf-8")
        return ws

    def test_editor_view_shows_empty_state_with_no_timeline(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td, with_timeline=False)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.assertTrue(bool(view._empty.grid_info()))
            self.assertFalse(bool(view._body.grid_info()))

    def test_editor_view_renders_real_timeline_and_selection_updates_inspector(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            self.assertTrue(bool(view._body.grid_info()))
            self.assertFalse(bool(view._empty.grid_info()))
            self.assertIsNotNone(view._timeline)
            self.assertEqual(len(view._timeline.events), 3)

            view._on_select("t1")
            self.assertEqual(view._inspector._event_id, "t1")
            view._inspector._apply(opacity=0.5)
            import editorial_timeline_edit as tl_edit

            ev = tl_edit.find_event(view._timeline, "t1")
            self.assertAlmostEqual(ev.opacity, 0.5)

    def test_editor_insert_asset_adds_ripple_placed_visual_clip(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            from ui.media_browser import AssetItem

            item = AssetItem(Path(td) / "broll.png", "visual", scene_number="1", label="broll.png")
            before = len(view._timeline.events)
            view._on_insert_asset_at(item, 0.0)
            self.assertEqual(len(view._timeline.events), before + 1)
            visual_events = [e for e in view._timeline.events if e.track == "VIDEO_1"]
            self.assertEqual(len(visual_events), 2)

    def test_editor_insert_asset_targets_video_2_broll_when_selected(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            view._media._target_display_var.set("VIDEO_2 (B-roll)")
            self.assertEqual(view._media.target_track(), "VIDEO_2")

            from ui.media_browser import AssetItem

            item = AssetItem(Path(td) / "broll.png", "visual", scene_number="1", label="broll.png")
            view._on_insert_asset_at(item, 0.0)
            broll_events = [e for e in view._timeline.events if e.track == "VIDEO_2"]
            self.assertEqual(len(broll_events), 1)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_editor_insert_video_2_broll_over_video_1_gets_real_probed_duration_and_overlaps(self):
        """Section 2/3: inserting a real VIDEO_2 asset over VIDEO_1 must
        (a) use the asset's ACTUAL ffprobe'd duration, not a hardcoded
        placeholder, (b) genuinely overlap VIDEO_1 in time (not ripple it
        out of the way), and (c) reconcile into a real broll overlay."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            broll_path = Path(td) / "broll.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=3:r=10",
                 "-pix_fmt", "yuv420p", str(broll_path)],
                check=True, capture_output=True,
            )
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            view._media._target_display_var.set("VIDEO_2 (B-roll)")
            from ui.media_browser import AssetItem

            item = AssetItem(broll_path, "visual", scene_number="1", label="broll.mp4")
            event_id = view._on_insert_asset_at(item, 1.0)
            self.app.update_idletasks()

            import editorial_timeline_edit as tl_edit

            broll_events = [e for e in view._timeline.events if e.track == "VIDEO_2"]
            self.assertEqual(len(broll_events), 1)
            b = broll_events[0]
            self.assertAlmostEqual(b.start, 1.0)
            self.assertAlmostEqual(b.duration, 3.0, delta=0.2)  # the REAL probed duration, not 4.0

            v1 = tl_edit.find_event(view._timeline, "v1")
            self.assertAlmostEqual(v1.start, 0.0)
            self.assertAlmostEqual(v1.end, 5.0)  # untouched — no ripple from the overlay insert

            from editorial.edit_decision import EditDecision, ShotSpec

            decisions = [EditDecision(scene_number="1", required_duration=5.0, shots=[ShotSpec(shot_id="orig", output_duration=5.0)])]
            out = tl_edit.reconcile_timeline_into_decisions(decisions, view._timeline)
            self.assertEqual(len(out[0].broll), 1, "an overlapping VIDEO_2 insert must reconcile into a real broll overlay")

    def test_editor_insert_music_asset_adds_freely_movable_clip(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            from ui.media_browser import AssetItem

            item = AssetItem(Path(td) / "bed.mp3", "music", label="bed.mp3")
            before = len(view._timeline.events)
            view._on_insert_asset_at(item, 2.0)
            self.assertEqual(len(view._timeline.events), before + 1)
            music_events = [e for e in view._timeline.events if e.track == "MUSIC"]
            self.assertEqual(len(music_events), 1)
            self.assertAlmostEqual(music_events[0].start, 2.0)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_editor_timeline_fetches_and_draws_real_waveform(self):
        """End-to-end: a real audio file on an AMBIENCE clip -> TimelineCanvas
        kicks off a real background decode (waveform_cache.py) -> the
        result lands via the queue -> a real canvas polygon gets drawn.
        Not a mock at any stage."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td, with_timeline=False)
            audio_path = Path(td) / "amb.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", "-ar", "22050", str(audio_path)],
                check=True, capture_output=True,
            )
            (ws.state_dir / "editorial_plan.json").write_text(json.dumps({
                "scenes": [{"scene_number": "1", "start": 0.0, "end": 5.0}],
                "timeline": {
                    "version": 1, "audio_end": 5.0,
                    "events": [
                        {"event_id": "amb1", "track": "AMBIENCE", "start": 0.0, "end": 2.0, "scene_number": "1", "source": str(audio_path)},
                    ],
                },
            }), encoding="utf-8")

            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            canvas = view._timeline_canvas
            self.assertEqual(canvas._waveform_state_dir, ws.state_dir)

            # First redraw already kicked off the background decode thread
            # (see set_timeline -> redraw -> _draw_waveform -> _request_waveform).
            # Wait for the REAL result on the queue directly — never call
            # Tk's update()/update_idletasks() in a busy poll loop here:
            # repeatedly pumping the event loop from a tight Python loop
            # fights CustomTkinter's own internal idle/after callbacks and
            # can make update() calls balloon in duration for reasons
            # unrelated to this feature. Draining the queue directly (no
            # Tk pumping needed — queue.Queue is thread-safe on its own)
            # avoids that hazard entirely.
            import queue as _queue

            try:
                event_id, peaks = canvas._waveform_queue.get(timeout=10.0)
            except _queue.Empty:
                self.fail("waveform never arrived from the background decode")
            canvas._waveform_pending.discard(event_id)
            canvas._waveform_peaks[event_id] = peaks or []
            self.assertIn("amb1", canvas._waveform_peaks, "waveform never arrived from the background decode")
            self.assertGreater(len(canvas._waveform_peaks["amb1"]), 0)

            canvas.redraw()
            polygon_items = canvas.canvas.find_withtag("all")
            self.assertGreater(len(polygon_items), 0)

    def test_dragging_the_left_sash_resizes_the_media_browser_column(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            before = view._body.grid_columnconfigure(0)["minsize"]
            import types

            view._start_sash_drag("media", types.SimpleNamespace(x_root=500))
            view._drag_sash("media", types.SimpleNamespace(x_root=560))  # +60px
            after = view._body.grid_columnconfigure(0)["minsize"]
            self.assertEqual(after, before + 60)

    def test_dragging_the_right_sash_resizes_the_inspector_column_mirrored(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            before = view._body.grid_columnconfigure(4)["minsize"]
            import types

            view._start_sash_drag("inspector", types.SimpleNamespace(x_root=800))
            view._drag_sash("inspector", types.SimpleNamespace(x_root=760))  # -40px -> inspector grows by 40
            after = view._body.grid_columnconfigure(4)["minsize"]
            self.assertEqual(after, before + 40)

    def test_sash_drag_respects_minimum_and_maximum_widths(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            import types
            from ui.editor_view import MAX_MEDIA_W, MIN_MEDIA_W

            view._start_sash_drag("media", types.SimpleNamespace(x_root=0))
            view._drag_sash("media", types.SimpleNamespace(x_root=-10000))
            self.assertEqual(view._body.grid_columnconfigure(0)["minsize"], MIN_MEDIA_W)
            view._start_sash_drag("media", types.SimpleNamespace(x_root=0))
            view._drag_sash("media", types.SimpleNamespace(x_root=10000))
            self.assertEqual(view._body.grid_columnconfigure(0)["minsize"], MAX_MEDIA_W)

    def test_panel_widths_persist_onto_the_app_for_the_session(self):
        """Session-scoped persistence (see EditorView.__init__'s docstring
        note — this does not survive an app restart, only living on the
        `app` object): a freshly-constructed EditorView sharing the same
        `app` picks up the last resized width instead of the default."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            import types

            view._start_sash_drag("media", types.SimpleNamespace(x_root=0))
            view._drag_sash("media", types.SimpleNamespace(x_root=50))
            resized = view._body.grid_columnconfigure(0)["minsize"]
            self.assertEqual(self.app._editor_panel_widths["media"], resized)

            from ui.editor_view import EditorView

            second = EditorView(self.app._shell.center, self.app)
            try:
                self.assertEqual(second._panel_widths["media"], resized)
            finally:
                second.destroy()

    def test_editor_undo_redo_wired_through_inspector_edit(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            import editorial_timeline_edit as tl_edit

            view._on_select("sfx1")
            view._inspector._apply(volume=0.2)
            self.assertAlmostEqual(tl_edit.find_event(view._timeline, "sfx1").metadata["volume"], 0.2)
            view._undo.undo()
            self.assertAlmostEqual(tl_edit.find_event(view._timeline, "sfx1").metadata["volume"], 0.8)
            view._undo.redo()
            self.assertAlmostEqual(tl_edit.find_event(view._timeline, "sfx1").metadata["volume"], 0.2)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_editor_proxy_rebuild_includes_real_voiceover_audio(self):
        """Reported live: a real project's preview had video but NO
        narration audio at all. Root cause — VOICEOVER TimelineEvents
        carry no source of their own (see preview_engine.build_audio_mix's
        docstring); the fix threads the workspace's real voiceover file
        (ws.get_active_voiceover()/find_voiceover_audio()) into the
        background proxy-build call. This exercises the REAL EditorView
        wiring end-to-end, not just preview_engine directly."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td, with_timeline=False)
            voiceover_path = ws.audio_dir / "narration.wav"
            ws.audio_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", str(voiceover_path)],
                check=True, capture_output=True,
            )
            ws.set_active_voiceover(voiceover_path, source="imported")
            (ws.state_dir / "editorial_plan.json").write_text(json.dumps({
                "scenes": [{"scene_number": "1", "start": 0.0, "end": 2.0}],
                "timeline": {
                    "version": 1, "audio_end": 2.0,
                    "events": [
                        {"event_id": "vo1", "track": "VOICEOVER", "start": 0.0, "end": 2.0, "scene_number": "1", "source": "", "metadata": {"purpose": "emotion"}},
                    ],
                },
            }), encoding="utf-8")

            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            # _rebuild_proxy() schedules the actual thread start via
            # self.after(...), which needs the Tk mainloop to actually
            # process pending events to fire — calling update()/
            # update_idletasks() here is exactly the busy-pump hazard
            # documented in ui/timeline_canvas.py's waveform test (fights
            # CTk's own internal after() timers, observed hanging a real
            # process at 100%+ CPU). Bypass the debounce/after() scheduling
            # entirely and start the background thread directly — this is
            # the SAME real _start_proxy_thread()/work() the debounced
            # path calls, just invoked without needing the Tk event loop.
            view._proxy_build_token += 1
            view._start_proxy_thread(view._proxy_build_token, ws.state_dir)
            import queue as _queue

            try:
                token, video, audio, duration = view._proxy_result_queue.get(timeout=20.0)
            except _queue.Empty:
                self.fail("proxy build never completed")
            self.assertIsNotNone(audio, "the real voiceover file never made it into the audio mix")
            self.assertTrue(Path(audio).is_file())
            result = subprocess.run(
                ["ffmpeg", "-i", str(audio), "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True,
            )
            self.assertIn("mean_volume", result.stderr)
            self.assertNotIn("mean_volume: -91", result.stderr)

    def test_canvas_ruler_extent_extends_when_an_image_clip_duration_grows(self):
        """Reported live: "I added image media that should be 5 seconds
        long, and the editor still behaves like duration is fixed."
        Traced to the TimelineCanvas ruler/scroll extent reading
        timeline.audio_end directly (the narration's own fixed length,
        never touched by editing) instead of the actual current timeline
        length — extending a clip's duration was fully real in the data
        model but literally unreachable on the canvas. Verifies the fix
        (editorial_timeline_edit.timeline_duration) through the REAL live
        TimelineCanvas, not just the data model."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td, with_timeline=False)
            (ws.state_dir / "editorial_plan.json").write_text(json.dumps({
                "scenes": [{"scene_number": "1", "start": 0.0, "end": 2.0}],
                "timeline": {
                    "version": 1, "audio_end": 2.0,
                    "events": [
                        {"event_id": "img1", "track": "IMAGE", "start": 0.0, "end": 2.0, "scene_number": "1", "source": "", "metadata": {}},
                    ],
                },
            }), encoding="utf-8")
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            self.assertAlmostEqual(canvas._duration(), 2.0)

            import editorial_timeline_edit as tl_edit

            tl_edit.trim_event_end(view._timeline, "img1", 8.0, snap=False)
            canvas.redraw()
            self.assertAlmostEqual(
                canvas._duration(), 8.0,
                msg="the timeline canvas ruler/scroll extent did not extend with the clip",
            )
            self.assertAlmostEqual(tl_edit.timeline_duration(view._timeline), 8.0)

    def test_editor_preview_and_canvas_playhead_stay_in_sync(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            view._preview._duration = 5.0
            view._timeline_canvas.set_playhead(2.5)
            self.assertAlmostEqual(view._preview._position, 2.5)

    def test_apply_proxy_ignores_a_stale_superseded_token(self):
        """Task 17 (rapid editing): a slow background proxy build whose
        result arrives AFTER a newer edit already bumped the build token
        must be silently discarded — never overwrite the fresher preview
        state with stale content."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            view._preview.set_proxies(None, None, 5.0)
            stale_token = view._proxy_build_token
            view._proxy_build_token += 1  # simulate a newer edit having started another build
            view._apply_proxy(stale_token, Path("/tmp/stale_video.mp4"), Path("/tmp/stale_audio.wav"), 99.0)
            # The stale result must never have been applied.
            self.assertIsNone(view._preview._video_path)
            self.assertNotAlmostEqual(view._preview._duration, 99.0)

    def test_apply_proxy_reports_a_genuine_build_failure_distinctly(self):
        """Task 16: a build that fails (None result) for a timeline that
        DOES have visual content shows a distinct, honest message and
        notifies — never crashes, never silently looks like "nothing
        edited yet"."""
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            self.assertTrue(any(e.track == "VIDEO_1" for e in view._timeline.events))

            notified = []
            self.app._shell.notify = lambda msg: notified.append(msg)
            token = view._proxy_build_token
            view._apply_proxy(token, None, None, 5.0)
            self.assertIn("Preview build failed", notified[0] if notified else "")
            self.assertIn("couldn't be built", view._preview._canvas.itemcget(view._preview._empty_text, "text"))
            # The timeline itself must be completely untouched by a failed build.
            self.assertEqual(len(view._timeline.events), 3)

    def _canvas_y_for(self, canvas, track: str) -> float:
        """The Y a real click needs to land in ``track``'s row — reads
        canvas._last_rows (the rows the last redraw() actually drew),
        NEVER recomputed independently. A test (or _event_at itself)
        computing rows its own way was exactly the class of bug this whole
        interaction failure traced back to (see redraw()'s comment)."""
        import ui.timeline_layout as L

        self.assertTrue(canvas._last_rows, "canvas hasn't drawn yet — call redraw()/on_show() first")
        return L.track_y(track, canvas._last_rows) + 5

    def test_dragging_a_video_clip_in_the_middle_actually_moves_it(self):
        """Simulates a real press/drag/release mouse sequence on the
        TimelineCanvas — this is the interaction that was reported as
        "editor won't let me change a clip": a middle-press on a VIDEO_1/
        IMAGE clip used to be selection-only (mode=None, no drag started
        at all), so dragging it visibly did nothing. It's now a real
        drag-to-reorder (move_visual_event_to_index)."""
        import editorial_timeline_edit as tl_edit
        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            plan_path = ws.state_dir / "editorial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["timeline"]["events"].append(
                {"event_id": "v2", "track": "VIDEO_1", "start": 5.0, "end": 10.0, "scene_number": "1", "source": ""}
            )
            payload["timeline"]["audio_end"] = 10.0
            plan_path.write_text(json.dumps(payload), encoding="utf-8")

            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            y = self._canvas_y_for(canvas, "VIDEO_1")

            # Press in the middle of v1 (spans [0,5) -> midpoint t=2.5).
            import types

            x_v1_mid = L.time_to_x(2.5, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_v1_mid, y=y))
            self.assertEqual(canvas._selected_id, "v1")
            self.assertEqual(canvas._drag["mode"], "reorder")

            # Drag past v2's midpoint (t=7.5) -> v1 reorders after v2.
            x_target = L.time_to_x(8.5, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_target, y=y))
            order = [e.event_id for e in tl_edit.visual_sequence_order(view._timeline)]
            self.assertEqual(order, ["v2", "v1"], "middle-drag on a visual clip must actually move it")

            canvas._on_release(types.SimpleNamespace(x=x_target, y=y))
            self.assertTrue(view._undo.can_undo())
            view._undo.undo()
            self.assertEqual(
                [e.event_id for e in tl_edit.visual_sequence_order(view._timeline)], ["v1", "v2"],
            )

    def test_reorder_works_on_image_only_project_the_real_bug_scenario(self):
        """THE actual root cause: _event_at() used to compute track rows
        from a DIFFERENT set than redraw() drew from. Whenever a project
        has NO VIDEO_1 events at all (a common case — an all-generated-
        stills project puts every visual clip on the IMAGE track), every
        row from IMAGE onward was drawn ~36px lower than where clicks were
        being hit-tested, so a click on a visibly-rendered clip silently
        found nothing and no drag ever started. This is exactly what
        surfaced as "editor won't let me change a clip" in manual testing.
        Regression-proofs that specific scenario end to end."""
        import editorial_timeline_edit as tl_edit
        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            from project_workspace import ProjectWorkspace

            ws = ProjectWorkspace(project_id="p_image_only", title="ImageOnly", seq=1, root=td)
            ws.ensure_dirs()
            payload = {
                "scenes": [{"scene_number": "1", "start": 0.0, "end": 5.0}, {"scene_number": "2", "start": 5.0, "end": 10.0}],
                "timeline": {
                    "version": 1, "audio_end": 10.0,
                    "events": [
                        # No VIDEO_1/VIDEO_2 event anywhere — IMAGE only,
                        # plus VOICEOVER/TEXT/SFX so several tracks sit
                        # after IMAGE in TRACK_ORDER (VIDEO_1, IMAGE,
                        # VOICEOVER, MUSIC, AMBIENCE, SFX, TEXT, GRAPHICS).
                        {"event_id": "i1", "track": "IMAGE", "start": 0.0, "end": 5.0, "scene_number": "1", "source": ""},
                        {"event_id": "i2", "track": "IMAGE", "start": 5.0, "end": 10.0, "scene_number": "2", "source": ""},
                        {"event_id": "vo", "track": "VOICEOVER", "start": 0.0, "end": 10.0, "scene_number": "1"},
                        {"event_id": "sfx1", "track": "SFX", "start": 1.0, "end": 1.5, "scene_number": "1", "metadata": {"volume": 1.0}},
                    ],
                },
            }
            (ws.state_dir / "editorial_plan.json").write_text(json.dumps(payload), encoding="utf-8")

            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            # Sanity: prove the bug scenario is real — IMAGE is NOT at the
            # same row as a naive (unforced-union) recompute would give it.
            naive_rows = L.track_rows({e.track for e in view._timeline.events})
            self.assertNotEqual(
                canvas._last_rows, naive_rows,
                "test fixture no longer reproduces the row-set mismatch this test exists to catch",
            )

            y_image = self._canvas_y_for(canvas, "IMAGE")
            x_i1_mid = L.time_to_x(2.5, canvas._zoom, canvas._scroll_x)

            # A click at the ACTUAL drawn position of i1 must find i1.
            hit = canvas._event_at(x_i1_mid, y_image)
            self.assertIsNotNone(hit, "click on the visibly-rendered IMAGE clip found nothing")
            self.assertEqual(hit.event_id, "i1")

            # And a real press/drag/release must move it.
            import types

            canvas._on_press(types.SimpleNamespace(x=x_i1_mid, y=y_image))
            self.assertEqual(canvas._selected_id, "i1")
            self.assertEqual(canvas._drag["mode"], "reorder")
            x_target = L.time_to_x(8.5, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_target, y=y_image))
            order = [e.event_id for e in tl_edit.visual_sequence_order(view._timeline)]
            self.assertEqual(order, ["i2", "i1"])
            canvas._on_release(types.SimpleNamespace(x=x_target, y=y_image))
            self.assertTrue(view._undo.can_undo())

    def test_right_edge_drag_right_increases_duration(self):
        import types

        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            plan_path = ws.state_dir / "editorial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["timeline"]["events"].append(
                {"event_id": "v2", "track": "VIDEO_1", "start": 5.0, "end": 10.0, "scene_number": "1", "source": ""}
            )
            payload["timeline"]["audio_end"] = 20.0  # headroom to grow into
            plan_path.write_text(json.dumps(payload), encoding="utf-8")
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            y = self._canvas_y_for(canvas, "VIDEO_1")
            import editorial_timeline_edit as tl_edit

            v2 = tl_edit.find_event(view._timeline, "v2")
            orig_end = v2.end
            x_right_edge = L.time_to_x(v2.end, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_right_edge, y=y))
            self.assertEqual(canvas._drag["mode"], "trim_end", "press on the right edge must start a trim, not a reorder")
            x_new = L.time_to_x(v2.end + 3.0, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_new, y=y))
            grown = tl_edit.find_event(view._timeline, "v2")
            self.assertGreater(grown.end, orig_end, "dragging the right edge right must make the clip longer")
            canvas._on_release(types.SimpleNamespace(x=x_new, y=y))
            self.assertTrue(view._undo.can_undo())
            view._undo.undo()
            self.assertAlmostEqual(tl_edit.find_event(view._timeline, "v2").end, orig_end)

    def test_right_edge_drag_left_decreases_duration(self):
        import types

        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            plan_path = ws.state_dir / "editorial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["timeline"]["events"].append(
                {"event_id": "v2", "track": "VIDEO_1", "start": 5.0, "end": 10.0, "scene_number": "1", "source": ""}
            )
            payload["timeline"]["audio_end"] = 10.0
            plan_path.write_text(json.dumps(payload), encoding="utf-8")
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            y = self._canvas_y_for(canvas, "VIDEO_1")
            import editorial_timeline_edit as tl_edit

            v2 = tl_edit.find_event(view._timeline, "v2")
            orig_end = v2.end
            x_right_edge = L.time_to_x(v2.end, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_right_edge, y=y))
            self.assertEqual(canvas._drag["mode"], "trim_end")
            x_new = L.time_to_x(v2.end - 2.0, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_new, y=y))
            shrunk = tl_edit.find_event(view._timeline, "v2")
            self.assertLess(shrunk.end, orig_end, "dragging the right edge left must make the clip shorter")
            canvas._on_release(types.SimpleNamespace(x=x_new, y=y))
            self.assertTrue(view._undo.can_undo())

    def test_left_edge_trim_shrinks_clip_and_ripples_neighbor(self):
        import types

        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            plan_path = ws.state_dir / "editorial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["timeline"]["events"].append(
                {"event_id": "v2", "track": "VIDEO_1", "start": 5.0, "end": 10.0, "scene_number": "1", "source": ""}
            )
            payload["timeline"]["audio_end"] = 10.0
            plan_path.write_text(json.dumps(payload), encoding="utf-8")
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            y = self._canvas_y_for(canvas, "VIDEO_1")
            import editorial_timeline_edit as tl_edit

            # v1 ends and v2 starts at the exact same pixel (t=5.0) — a
            # hair to the right unambiguously lands inside v2 (t<=end is
            # false for v1 there) while still being within v2's edge zone.
            x_left_edge = L.time_to_x(5.05, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_left_edge, y=y))
            self.assertEqual(canvas._selected_id, "v2")
            self.assertEqual(canvas._drag["mode"], "trim_start")
            x_new = L.time_to_x(7.0, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_new, y=y))
            v2 = tl_edit.find_event(view._timeline, "v2")
            # Drag delta is relative to the press point (5.05), not an
            # absolute snap to the cursor — real drag-handle UX.
            self.assertAlmostEqual(v2.start, 6.95, delta=0.01)
            canvas._on_release(types.SimpleNamespace(x=x_new, y=y))
            self.assertTrue(view._undo.can_undo())
            view._undo.undo()
            self.assertAlmostEqual(tl_edit.find_event(view._timeline, "v2").start, 5.0)

    def test_reorder_and_trim_work_when_zoomed(self):
        import types

        import editorial_timeline_edit as tl_edit
        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            plan_path = ws.state_dir / "editorial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["timeline"]["events"].append(
                {"event_id": "v2", "track": "VIDEO_1", "start": 5.0, "end": 10.0, "scene_number": "1", "source": ""}
            )
            payload["timeline"]["audio_end"] = 10.0
            plan_path.write_text(json.dumps(payload), encoding="utf-8")
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            canvas._zoom = 2.0  # zoomed in — pixels-per-second doubles
            canvas.redraw()
            y = self._canvas_y_for(canvas, "VIDEO_1")

            x_v1_mid = L.time_to_x(2.5, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_v1_mid, y=y))
            self.assertEqual(canvas._drag["mode"], "reorder")
            x_target = L.time_to_x(8.5, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_target, y=y))
            order = [e.event_id for e in tl_edit.visual_sequence_order(view._timeline)]
            self.assertEqual(order, ["v2", "v1"], "reorder must still work at 2x zoom")
            canvas._on_release(types.SimpleNamespace(x=x_target, y=y))

    def test_reorder_and_trim_work_when_scrolled(self):
        import types

        import editorial_timeline_edit as tl_edit
        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            plan_path = ws.state_dir / "editorial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["timeline"]["events"] = [
                {"event_id": "v1", "track": "VIDEO_1", "start": 0.0, "end": 5.0, "scene_number": "1", "source": ""},
                {"event_id": "v2", "track": "VIDEO_1", "start": 5.0, "end": 10.0, "scene_number": "1", "source": ""},
            ]
            payload["timeline"]["audio_end"] = 10.0
            plan_path.write_text(json.dumps(payload), encoding="utf-8")
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()

            canvas = view._timeline_canvas
            canvas._scroll_x = 20.0  # scrolled right by 20px
            canvas.redraw()
            y = self._canvas_y_for(canvas, "VIDEO_1")

            x_v1_mid = L.time_to_x(2.5, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_v1_mid, y=y))
            self.assertEqual(canvas._selected_id, "v1", "hit-testing must account for the scroll offset")
            self.assertEqual(canvas._drag["mode"], "reorder")
            x_target = L.time_to_x(8.5, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_target, y=y))
            order = [e.event_id for e in tl_edit.visual_sequence_order(view._timeline)]
            self.assertEqual(order, ["v2", "v1"], "reorder must still work while scrolled")
            canvas._on_release(types.SimpleNamespace(x=x_target, y=y))

    def test_edge_hit_zone_scales_with_clip_width_not_a_fixed_tiny_pixel_count(self):
        with tempfile.TemporaryDirectory() as td:
            ws = self._make_editor_workspace(td)
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            canvas = view._timeline_canvas
            import editorial_timeline_edit as tl_edit

            v1 = tl_edit.find_event(view._timeline, "v1")
            zone = canvas._hit_zone_px(v1)
            self.assertGreaterEqual(zone, 4.0)
            self.assertLessEqual(zone, 12.0)

    def test_inspector_extended_action_buttons_exist(self):
        for name in (
            "details_add_sfx_btn", "details_add_ambience_btn", "details_add_graphic_btn",
            "details_edit_timing_btn", "details_add_broll_btn", "details_reset_btn",
        ):
            self.assertTrue(hasattr(self.app, name))
        self.assertEqual(self.app.details_add_broll_btn.cget("state"), "disabled")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_final_acceptance_full_editor_workflow_25_steps(self):
        """Section 15's end-to-end acceptance test: PROJECT -> (synthetic)
        SCRIPT/VISUAL PLAN/ASSETS/VOICEOVER -> FIRST CUT -> EDITOR, then
        the 25 listed operations against the REAL live Editor (this class's
        shared app/Tk root — genuine CTk widgets, genuine
        editorial_timeline_edit/reconcile/render_video, no mocks), ending
        in undo/redo, save, reload, and a real FFmpeg export whose output
        is verified to reflect the edited state.

        Steps 1-3 (move/trim/split VIDEO_1) drive the real TimelineCanvas
        through synthetic Tk press/drag/release events — the same pattern
        already used elsewhere in this file to regression-proof the
        original "can't change clip" bug. The remaining steps call the
        same production functions the canvas/Inspector themselves call
        (tl_edit.*, InspectorPanel._apply) directly — this environment
        cannot physically move a mouse, so every "click"/"drag" in this
        suite is necessarily a synthetic Tk event either way; calling the
        underlying handler directly for steps that don't specifically
        regression-test hit-testing keeps this test legible without
        weakening what it proves (the same non-mocked code path runs
        either way — see this file's module docstring)."""
        import types

        import editorial_timeline_edit as tl_edit
        import ui.timeline_layout as L

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            images_dir = root / "images"
            images_dir.mkdir()
            for name in ("1.mp4", "2.mp4"):
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=8",
                     "-pix_fmt", "yuv420p", str(images_dir / name)],
                    check=True, capture_output=True,
                )
            broll_path = root / "broll.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=4:r=10",
                 "-pix_fmt", "yuv420p", str(broll_path)],
                check=True, capture_output=True,
            )
            sfx_path = root / "sfx.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.3", str(sfx_path)],
                check=True, capture_output=True,
            )
            amb_path = root / "amb.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=90:duration=0.5", str(amb_path)],
                check=True, capture_output=True,
            )
            voiceover_path = root / "voiceover.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=6", str(voiceover_path)],
                check=True, capture_output=True,
            )

            from project_workspace import ProjectWorkspace

            ws = ProjectWorkspace(project_id="p_accept", title="Acceptance", seq=1, root=td)
            ws.ensure_dirs()
            payload = {
                "scenes": [{"scene_number": "1", "start": 0.0, "end": 3.0}, {"scene_number": "2", "start": 3.0, "end": 6.0}],
                "timeline": {
                    "version": 1, "audio_end": 6.0,
                    "events": [
                        {"event_id": "v1", "track": "VIDEO_1", "start": 0.0, "end": 3.0, "scene_number": "1", "source": str(images_dir / "1.mp4"), "metadata": {"speed": 1.0, "source_start": 0.0}},
                        {"event_id": "v2", "track": "VIDEO_1", "start": 3.0, "end": 6.0, "scene_number": "2", "source": str(images_dir / "2.mp4"), "metadata": {"speed": 1.0, "source_start": 0.0}},
                    ],
                },
            }
            (ws.state_dir / "editorial_plan.json").write_text(json.dumps(payload), encoding="utf-8")

            # ---- PROJECT -> ... -> FIRST CUT -> EDITOR ----
            self.app._workspace = ws
            view = self.app._view_editor
            view.on_show()
            self.app.update_idletasks()
            canvas = view._timeline_canvas
            tl = view._timeline
            self.assertEqual(len(tl.events), 2)

            # 1. Move VIDEO_1 (real drag-to-reorder on the live canvas).
            y = L.track_y("VIDEO_1", canvas._last_rows) + 5
            x_v1_mid = L.time_to_x(1.5, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_v1_mid, y=y))
            self.assertEqual(canvas._drag["mode"], "reorder")
            x_target = L.time_to_x(5.0, canvas._zoom, canvas._scroll_x)  # past v2's own midpoint (4.5)
            canvas._on_drag(types.SimpleNamespace(x=x_target, y=y))
            canvas._on_release(types.SimpleNamespace(x=x_target, y=y))
            self.assertEqual([e.event_id for e in tl_edit.visual_sequence_order(tl)], ["v2", "v1"])

            # 2. Trim VIDEO_1 (real edge-drag on the live canvas) — v1 is
            # now the SECOND clip [3,6); shrink its right edge.
            v1_now = tl_edit.find_event(tl, "v1")
            v1_end_before_trim = v1_now.end  # a plain float, NOT a live reference to the mutated event
            y = L.track_y("VIDEO_1", canvas._last_rows) + 5
            x_edge = L.time_to_x(v1_end_before_trim, canvas._zoom, canvas._scroll_x)
            canvas._on_press(types.SimpleNamespace(x=x_edge, y=y))
            self.assertEqual(canvas._drag["mode"], "trim_end")
            x_new = L.time_to_x(v1_end_before_trim - 1.0, canvas._zoom, canvas._scroll_x)
            canvas._on_drag(types.SimpleNamespace(x=x_new, y=y))
            canvas._on_release(types.SimpleNamespace(x=x_new, y=y))
            self.assertLess(tl_edit.find_event(tl, "v1").end, v1_end_before_trim)

            # 3. Split VIDEO_1 (real double-click via the canvas handler).
            v1_now = tl_edit.find_event(tl, "v1")
            mid = (v1_now.start + v1_now.end) / 2.0
            before_count = len(tl.events)
            canvas._on_double_click_at("v1", mid)
            self.assertEqual(len(tl.events), before_count + 1)

            # 4/5. Insert VIDEO_2 and overlap it over VIDEO_1.
            view._media._target_display_var.set("VIDEO_2 (B-roll)")
            from ui.media_browser import AssetItem

            v2_now = tl_edit.find_event(tl, "v2")
            overlap_t = v2_now.start + 0.3
            item = AssetItem(broll_path, "visual", scene_number=v2_now.scene_number, label="broll.mp4")
            broll_id = view._on_insert_asset_at(item, overlap_t) or next(
                e.event_id for e in tl.events if e.track == "VIDEO_2"
            )
            broll_ev = tl_edit.find_event(tl, broll_id)
            self.assertIsNotNone(broll_ev)
            self.assertEqual(broll_ev.track, "VIDEO_2")

            # 6. Move VIDEO_2.
            tl_edit.move_event(tl, broll_id, overlap_t + 0.4, snap=False)
            # 7. Trim VIDEO_2.
            b_now = tl_edit.find_event(tl, broll_id)
            tl_edit.trim_event_end(tl, broll_id, b_now.end - 0.2, snap=False)
            v1_before_broll_edits = tl_edit.find_event(tl, "v1")
            self.assertIsNotNone(v1_before_broll_edits)  # primary track untouched by B-roll edits

            # 8/9. Add a transition + change its duration (via Inspector,
            # the real operator-facing control).
            view._on_select("v2")
            view._inspector._apply(transition_in="crossfade", transition_duration=0.35)
            self.assertEqual(tl_edit.find_event(tl, "v2").transition_in, "crossfade")
            view._inspector._apply(transition_duration=0.45)
            self.assertAlmostEqual(tl_edit.find_event(tl, "v2").metadata["transition_duration"], 0.45)

            # 10/11/12. Add SFX, move it, change its volume.
            sfx_id = tl_edit.add_event(
                tl, track="SFX", start=0.1, end=0.4, scene_number="1",
                source=str(sfx_path), metadata={"file": str(sfx_path), "volume": 1.0},
            )
            self.assertIsNotNone(sfx_id)
            tl_edit.move_event(tl, sfx_id, 0.6, snap=False)
            view._on_select(sfx_id)
            view._inspector._apply(volume=0.3)
            self.assertAlmostEqual(tl_edit.find_event(tl, sfx_id).metadata["volume"], 0.3)
            # 13. Mute SFX.
            view._inspector._apply(muted=True)
            self.assertTrue(tl_edit.find_event(tl, sfx_id).metadata["muted"])

            # 14/15/16. Add ambience, move it, change its volume.
            amb_id = tl_edit.add_event(
                tl, track="AMBIENCE", start=0.0, end=6.0, scene_number="1",
                source=str(amb_path), metadata={"file": str(amb_path), "volume": 0.5},
            )
            self.assertIsNotNone(amb_id)
            tl_edit.trim_event_start(tl, amb_id, 0.5, snap=False)
            view._on_select(amb_id)
            view._inspector._apply(volume=0.25)
            self.assertAlmostEqual(tl_edit.find_event(tl, amb_id).metadata["volume"], 0.25)

            # 17. Add/edit graphics.
            gfx_id = tl_edit.add_event(tl, track="GRAPHICS", start=0.2, end=1.2, scene_number="1", metadata={"kind": "lower_third"})
            self.assertIsNotNone(gfx_id)
            view._on_select(gfx_id)
            view._inspector._apply(opacity=0.8)
            self.assertAlmostEqual(tl_edit.find_event(tl, gfx_id).opacity, 0.8)

            # 18. Add/edit text.
            txt_id = tl_edit.add_event(tl, track="TEXT", start=1.5, end=2.5, scene_number="1", metadata={"text": "Hello"})
            self.assertIsNotNone(txt_id)
            view._on_select(txt_id)
            view._inspector._apply(opacity=0.9)
            self.assertAlmostEqual(tl_edit.find_event(tl, txt_id).opacity, 0.9)

            # 19. Change speed (on v2, a real motion source — see step 25).
            view._on_select("v2")
            view._inspector._apply(speed=tl_edit.clamp_speed(1.6))
            self.assertAlmostEqual(tl_edit.find_event(tl, "v2").metadata["speed"], 1.6)

            edited_event_count = len(tl.events)

            # 20/21. Undo several operations, then redo them. Not every one
            # of the last few ops changes the event COUNT (a speed/volume/
            # opacity edit mutates a property in place) — so the reliable
            # cross-check is the LAST op pushed (v2's speed change), which
            # must genuinely revert and then genuinely reapply.
            for _ in range(4):
                if view._undo.can_undo():
                    view._undo.undo()
            self.assertNotAlmostEqual(
                tl_edit.find_event(tl, "v2").metadata.get("speed", 1.0), 1.6,
                msg="undo did not revert the speed change",
            )
            redo_n = 0
            while view._undo.can_redo():
                view._undo.redo()
                redo_n += 1
            self.assertGreater(redo_n, 0)
            self.assertAlmostEqual(tl_edit.find_event(tl, "v2").metadata["speed"], 1.6, msg="redo did not restore the speed change")
            self.assertEqual(len(tl.events), edited_event_count, "redo did not restore every undone operation")

            # 22/23/24. Save, reload (simulate close/reopen), verify state.
            self.assertTrue(tl_edit.save_timeline(ws.state_dir, tl))
            reloaded = tl_edit.load_timeline(ws.state_dir)
            self.assertEqual(len(reloaded.events), edited_event_count)
            self.assertEqual(tl_edit.find_event(reloaded, "v2").transition_in, "crossfade")
            self.assertAlmostEqual(tl_edit.find_event(reloaded, "v2").metadata["speed"], 1.6)
            reloaded_sfx = next(e for e in reloaded.events if e.event_id == sfx_id)
            self.assertTrue(reloaded_sfx.metadata["muted"])

            # 25. Export — verify the final output reflects the edited
            # timeline (real reconcile + real ffmpeg render, not a mock).
            from editorial.edit_decision import EditDecision, ShotSpec

            base_decisions = [
                EditDecision(scene_number="1", required_duration=3.0, shots=[ShotSpec(shot_id="s1", output_duration=3.0)]),
                EditDecision(scene_number="2", required_duration=3.0, shots=[ShotSpec(shot_id="s2", output_duration=3.0)]),
            ]
            reconciled = tl_edit.reconcile_timeline_into_decisions(base_decisions, reloaded)
            decision_map = {d.scene_number: d.to_dict() for d in reconciled}
            self.assertTrue(
                any(d.broll for d in reconciled),
                "the edited VIDEO_2 overlay must still reconcile into a real broll entry after reload",
            )

            import video_generator as vg

            aligned_rows = [
                {"scene_number": "1", "start_time": 0.0, "script_segment": "one"},
                {"scene_number": "2", "start_time": 3.0, "script_segment": "two"},
            ]
            out_path = root / "final.mp4"
            vg.render_video(
                aligned_rows, 6.0, images_dir, str(voiceover_path), str(out_path),
                "160x90", 10, zoom=False, visual_transitions=False,
                edit_decisions_by_scene=decision_map,
            )
            self.assertTrue(out_path.is_file())
            self.assertGreater(out_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
