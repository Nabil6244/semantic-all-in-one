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


class TestTimelineCanvasPremiumInteractions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import customtkinter as ctk
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        try:
            cls.root = ctk.CTk()
            cls.root.geometry("1000x400")
            cls.root.withdraw()
        except Exception as exc:
            raise unittest.SkipTest(f"no Tk display available: {exc}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def _canvas(self):
        from ui.timeline_canvas import TimelineCanvas
        from ui.undo_stack import UndoStack

        tl = EditorialTimeline(
            version=1, audio_end=20.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, scene_number="1"),
                TimelineEvent(event_id="t1", track="TEXT", start=1.0, end=3.0, scene_number="1"),
                TimelineEvent(event_id="s1", track="SFX", start=5.0, end=5.5, scene_number="1"),
            ],
        )
        tc = TimelineCanvas(self.root, undo_stack=UndoStack())
        tc.pack(fill="both", expand=True)
        tc.set_timeline(tl)
        self.root.update_idletasks()
        self.root.update()
        return tc, tl

    def test_track_header_column_builds_one_row_per_track(self):
        tc, tl = self._canvas()
        # +1 for the ruler-height spacer at row 0.
        self.assertEqual(len(tc._header_col.winfo_children()), len(tc._header_rows["_order"]) + 1)

    def test_lock_blocks_delete(self):
        tc, tl = self._canvas()
        tc._locked_tracks.add("SFX")
        tc._selected_id = "s1"
        tc._on_delete_selected()
        self.assertIsNotNone(next((e for e in tl.events if e.event_id == "s1"), None))

    def test_unlocked_delete_succeeds(self):
        tc, tl = self._canvas()
        tc._selected_id = "s1"
        tc._on_delete_selected()
        self.assertIsNone(next((e for e in tl.events if e.event_id == "s1"), None))

    def test_duplicate_creates_a_second_event_after_the_original(self):
        tc, tl = self._canvas()
        tc._selected_id = "t1"
        tc._on_duplicate_selected()
        text_events = [e for e in tl.events if e.track == "TEXT"]
        self.assertEqual(len(text_events), 2)
        new_ev = next(e for e in text_events if e.event_id != "t1")
        self.assertAlmostEqual(new_ev.start, 3.0)

    def test_duplicate_is_undoable(self):
        tc, tl = self._canvas()
        tc._selected_id = "t1"
        tc._on_duplicate_selected()
        self.assertEqual(len([e for e in tl.events if e.track == "TEXT"]), 2)
        tc._undo.undo()
        self.assertEqual(len([e for e in tl.events if e.track == "TEXT"]), 1)

    def test_lock_blocks_duplicate(self):
        tc, tl = self._canvas()
        tc._locked_tracks.add("TEXT")
        tc._selected_id = "t1"
        tc._on_duplicate_selected()
        self.assertEqual(len([e for e in tl.events if e.track == "TEXT"]), 1)

    def test_snap_enabled_by_default(self):
        tc, _ = self._canvas()
        self.assertTrue(tc._snap_enabled)

    def test_toggle_snap_flips_state_and_button_style(self):
        tc, _ = self._canvas()
        tc._on_toggle_snap()
        self.assertFalse(tc._snap_enabled)
        tc._on_toggle_snap()
        self.assertTrue(tc._snap_enabled)

    def test_disabling_snap_allows_precise_placement_near_a_boundary(self):
        """With snap off, a drag landing NEAR (but not on) a scene boundary
        must NOT jump to that boundary — precise manual placement."""
        import types

        import ui.timeline_layout as L
        from editorial_timeline_edit import find_event

        tc, tl = self._canvas()
        tc._snap_enabled = False
        y = L.track_y("TEXT", tc._last_rows) + 5
        x_mid = L.time_to_x(2.0, tc._zoom, tc._scroll_x)  # t1 spans [1,3) -> midpoint 2.0
        tc._on_press(types.SimpleNamespace(x=x_mid, y=y))
        self.assertEqual(tc._drag["mode"], "move")
        x_near_boundary = L.time_to_x(9.9, tc._zoom, tc._scroll_x)  # near v1's end (10.0) but not exact
        tc._on_drag(types.SimpleNamespace(x=x_near_boundary, y=y))
        moved = find_event(tl, "t1")
        self.assertFalse(
            any(abs(moved.start - b) < 1e-6 for b in (0.0, 10.0, 20.0)),
            "snap-off drag should not land exactly on a boundary",
        )

    def test_reorder_drag_shows_a_snap_guide_at_the_new_position(self):
        import types

        import ui.timeline_layout as L

        tc, tl = self._canvas()
        tl.events.append(TimelineEvent(event_id="v2", track="VIDEO_1", start=10.0, end=20.0, scene_number="2"))
        tc.redraw()
        y = L.track_y("VIDEO_1", tc._last_rows) + 5
        x_mid = L.time_to_x(5.0, tc._zoom, tc._scroll_x)  # v1 spans [0,10) -> midpoint 5.0
        tc._on_press(types.SimpleNamespace(x=x_mid, y=y))
        self.assertEqual(tc._drag["mode"], "reorder")
        x_target = L.time_to_x(15.0, tc._zoom, tc._scroll_x)
        tc._on_drag(types.SimpleNamespace(x=x_target, y=y))
        self.assertIsNotNone(tc._snap_guide_x, "reorder drag should show a landing-position guide")

    def test_hover_updates_hover_id(self):
        tc, tl = self._canvas()
        import ui.timeline_layout as L

        x = L.time_to_x(2.0, tc._zoom, tc._scroll_x)
        # Use the rows the last redraw() actually drew (tc._last_rows), not
        # an independent recompute — recomputing from a different track set
        # than redraw() used is exactly the bug this whole interaction path
        # was fixed for (see ui/timeline_canvas.py's redraw()/_event_at()).
        y = L.track_y("TEXT", tc._last_rows) + 5

        class FakeEvent:
            pass

        fe = FakeEvent()
        fe.x, fe.y = x, y
        tc._on_hover(fe)
        self.assertEqual(tc._hover_id, "t1")

    def test_ruler_click_seeks_playhead_not_selection(self):
        tc, tl = self._canvas()
        import ui.timeline_layout as L

        class FakeEvent:
            pass

        fe = FakeEvent()
        fe.x, fe.y = L.time_to_x(4.0, tc._zoom, tc._scroll_x), 5  # inside the ruler band
        tc._selected_id = "t1"
        tc._on_press(fe)
        self.assertAlmostEqual(tc._playhead, 4.0)
        self.assertEqual(tc._selected_id, "t1")  # selection untouched by a ruler click

    def test_mute_and_solo_toggle_independently(self):
        tc, tl = self._canvas()
        tc._toggle_mute("SFX")
        self.assertIn("SFX", tc._muted_tracks)
        tc._toggle_mute("SFX")
        self.assertNotIn("SFX", tc._muted_tracks)
        tc._toggle_solo("TEXT")
        self.assertIn("TEXT", tc._solo_tracks)

    def test_notify_callback_fires_on_delete(self):
        from ui.timeline_canvas import TimelineCanvas
        from ui.undo_stack import UndoStack

        tl = EditorialTimeline(
            version=1, audio_end=10.0,
            events=[TimelineEvent(event_id="t1", track="TEXT", start=0.0, end=2.0, scene_number="1")],
        )
        messages = []
        tc = TimelineCanvas(self.root, undo_stack=UndoStack(), on_notify=messages.append)
        tc.set_timeline(tl)
        tc._selected_id = "t1"
        tc._on_delete_selected()
        self.assertIn("Clip deleted", messages)

    def test_keyboard_shortcuts_registered(self):
        tc, _tl = self._canvas()
        bound = tc.canvas.bind()
        for seq in ("<Key-Delete>", "<Key-Home>", "<Key-End>", "<Control-Key-b>", "<Control-Key-d>"):
            self.assertIn(seq, bound)

    def test_video_2_middle_press_starts_a_move_not_a_reorder(self):
        """VIDEO_2 is an independent B-roll overlay (see editorial_
        timeline_edit.OVERLAY_VISUAL_TRACKS) — a middle-press must start a
        plain drag-anywhere move, never the primary-track reorder-to-index
        gesture."""
        import types

        import ui.timeline_layout as L

        tc, tl = self._canvas()
        tl.events.append(
            TimelineEvent(
                event_id="b1", track="VIDEO_2", start=5.0, end=8.0, scene_number="1",
                metadata={"source_start": 0.0, "speed": 1.0},
            )
        )
        tc.redraw()
        y = L.track_y("VIDEO_2", tc._last_rows) + 5
        x_mid = L.time_to_x(6.5, tc._zoom, tc._scroll_x)
        tc._on_press(types.SimpleNamespace(x=x_mid, y=y))
        self.assertEqual(tc._selected_id, "b1")
        self.assertEqual(tc._drag["mode"], "move")

    def test_dragging_video_2_overlay_does_not_move_video_1(self):
        import types

        import ui.timeline_layout as L
        from editorial_timeline_edit import find_event

        tc, tl = self._canvas()
        tl.events.append(
            TimelineEvent(
                event_id="b1", track="VIDEO_2", start=5.0, end=8.0, scene_number="1",
                metadata={"source_start": 0.0, "speed": 1.0},
            )
        )
        tc.redraw()
        y = L.track_y("VIDEO_2", tc._last_rows) + 5
        x_mid = L.time_to_x(6.5, tc._zoom, tc._scroll_x)
        tc._snap_enabled = False
        tc._on_press(types.SimpleNamespace(x=x_mid, y=y))
        x_target = L.time_to_x(9.5, tc._zoom, tc._scroll_x)  # drag +3s
        tc._on_drag(types.SimpleNamespace(x=x_target, y=y))
        b1 = find_event(tl, "b1")
        self.assertAlmostEqual(b1.start, 8.0, delta=0.05)
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.start, 0.0)
        self.assertAlmostEqual(v1.end, 10.0)  # untouched by the B-roll drag

    def test_dragging_a_clip_snaps_to_the_playhead(self):
        """spec item 11: dragging a clip near the playhead snaps to it."""
        import types

        import ui.timeline_layout as L
        from editorial_timeline_edit import find_event

        tc, tl = self._canvas()
        tc.set_playhead(6.3, notify=False)
        y = L.track_y("TEXT", tc._last_rows) + 5
        x_mid = L.time_to_x(2.0, tc._zoom, tc._scroll_x)  # t1 spans [1,3) -> midpoint 2.0
        tc._on_press(types.SimpleNamespace(x=x_mid, y=y))
        self.assertEqual(tc._drag["mode"], "move")
        # t1's start (1.0) is 1.0s before the press point (2.0, its
        # midpoint) — so a mouse position of t=7.35 puts the clip's new
        # start at 1.0 + (7.35-2.0) = 6.35, just off the playhead (6.3);
        # within the default 0.25s snap tolerance it should land exactly.
        x_near_playhead = L.time_to_x(7.35, tc._zoom, tc._scroll_x)
        tc._on_drag(types.SimpleNamespace(x=x_near_playhead, y=y))
        moved = find_event(tl, "t1")
        self.assertAlmostEqual(moved.start, 6.3)

    def test_dragging_the_playhead_snaps_to_a_clip_boundary(self):
        """spec item 11: dragging the playhead near a clip edge snaps to
        it — v1 ends at 10.0."""
        import types

        import ui.timeline_layout as L

        tc, tl = self._canvas()
        x_near_edge = L.time_to_x(9.9, tc._zoom, tc._scroll_x)
        tc._on_press(types.SimpleNamespace(x=x_near_edge, y=5))  # ruler band
        self.assertEqual(tc._drag["mode"], "playhead")
        tc._on_drag(types.SimpleNamespace(x=x_near_edge, y=5))
        self.assertAlmostEqual(tc._playhead, 10.0)

    def test_playhead_drag_disabled_by_snap_toggle_allows_precise_seek(self):
        import types

        import ui.timeline_layout as L

        tc, tl = self._canvas()
        tc._snap_enabled = False
        x_near_edge = L.time_to_x(9.9, tc._zoom, tc._scroll_x)
        tc._on_press(types.SimpleNamespace(x=x_near_edge, y=5))
        tc._on_drag(types.SimpleNamespace(x=x_near_edge, y=5))
        self.assertAlmostEqual(tc._playhead, 9.9)
        self.assertNotAlmostEqual(tc._playhead, 10.0)

    def test_playhead_drag_release_pushes_no_undo_entry(self):
        import types

        import ui.timeline_layout as L

        tc, tl = self._canvas()
        x = L.time_to_x(4.0, tc._zoom, tc._scroll_x)
        tc._on_press(types.SimpleNamespace(x=x, y=5))
        tc._on_drag(types.SimpleNamespace(x=x, y=5))
        tc._on_release(types.SimpleNamespace(x=x, y=5))
        self.assertFalse(tc._undo.can_undo())


class TestGlobalShortcutWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = __import__("app")
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def test_bind_global_shortcuts_uses_bind_all_not_per_widget_bind(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._bind_global_shortcuts)
        self.assertIn("bind_all", src)

    def test_typing_target_guard_checks_entry_and_textbox(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._typing_target)
        self.assertIn("CTkEntry", src)
        self.assertIn("CTkTextbox", src)

    def test_undo_redo_shortcuts_respect_typing_guard(self):
        src_u = inspect.getsource(self.app.VideoGeneratorApp._on_global_undo_shortcut)
        src_r = inspect.getsource(self.app.VideoGeneratorApp._on_global_redo_shortcut)
        self.assertIn("_typing_target", src_u)
        self.assertIn("_typing_target", src_r)


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
