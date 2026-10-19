"""Buttons that looked enabled but did nothing, or did the wrong thing (found by pressing every button in the real app)."""
import inspect
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def _cls():
    import app
    return next(v for v in vars(app).values() if isinstance(v, type) and hasattr(v, "_on_primary_cta"))


def _bind(fake, *names):
    cls = _cls()
    for n in names:
        setattr(fake, n, getattr(cls, n).__get__(fake))
    return fake


class DoubleClickOnGenerate(unittest.TestCase):
    """The top-bar button becomes Stop when a run starts; a double-click used to cancel the run it had just started."""

    def _fake(self):
        f = SimpleNamespace(_cta_action="generate", _notify=mock.Mock(), _CTA_DOUBLE_PRESS_S=1.0)
        return _bind(f, "_cta_double_press")

    def test_quick_second_press_on_stop_is_ignored(self):
        f = self._fake()
        self.assertFalse(f._cta_double_press())          # Generate
        for cancel in ("starmap_cancel", "cancel", "whatif_cancel", "weather_cancel", "overscaled_cancel"):
            f._cta_action = cancel
            self.assertTrue(f._cta_double_press(), cancel)
        f._notify.assert_called()

    def test_deliberate_stop_still_cancels(self):
        f = self._fake()
        f._cta_double_press()
        f._cta_last_start_press = time.monotonic() - 2.0
        f._cta_action = "hybrid_cancel"
        self.assertFalse(f._cta_double_press())

    def test_stop_without_a_recent_start_cancels(self):
        f = self._fake()
        f._cta_action = "pakmap_cancel"
        self.assertFalse(f._cta_double_press())

    def test_primary_cta_checks_first(self):
        src = inspect.getsource(_cls()._on_primary_cta)
        self.assertLess(src.index("self._cta_double_press()"), src.index('action = getattr(self, "_cta_action"'))


class OutputButtons(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.final = self.d / "final"
        self.final.mkdir()

    def _fake(self, last=None, out=""):
        f = SimpleNamespace(_last_output=last, _workspace=SimpleNamespace(final_dir=self.final),
                            output_var=SimpleNamespace(get=lambda: out), _open_folder_path=mock.Mock())
        return _bind(f, "_open_output_folder", "_open_in_player", "_latest_final_video")

    def test_open_output_folder_before_any_render_opens_the_project_final_folder(self):
        f = self._fake()
        f._open_output_folder()
        f._open_folder_path.assert_called_once_with(self.final)

    def test_open_output_folder_without_project_says_why(self):
        f = self._fake()
        f._workspace = None
        with mock.patch("app.messagebox.showinfo") as info:
            f._open_output_folder()
        info.assert_called_once()

    def test_latest_final_video(self):
        f = self._fake()
        self.assertIsNone(f._latest_final_video())
        old = self.final / "a.mp4"
        old.write_bytes(b"\0" * 2048)
        os.utime(old, (time.time() - 100, time.time() - 100))
        new = self.final / "b.mp4"
        new.write_bytes(b"\0" * 2048)
        (self.final / "tiny.mp4").write_bytes(b"\0")
        self.assertEqual(f._latest_final_video(), new)

    def test_play_uses_the_projects_newest_video_after_reopening(self):
        v = self.final / "v.mp4"
        v.write_bytes(b"\0" * 2048)
        f = self._fake()
        with mock.patch("app.subprocess.Popen") as popen, mock.patch("app.os.startfile", create=True) as sf:
            f._open_in_player()
        self.assertEqual(f._last_output, str(v))
        self.assertTrue(popen.called or sf.called)

    def test_play_with_nothing_to_play_says_why(self):
        f = self._fake()
        with mock.patch("app.messagebox.showinfo") as info, mock.patch("app.subprocess.Popen") as popen:
            f._open_in_player()
        info.assert_called_once()
        popen.assert_not_called()


class SilentButtons(unittest.TestCase):
    def test_select_by_source_without_scenes_says_why(self):
        f = SimpleNamespace(_scene_keys_by_source_bucket=lambda: {}, _notify=mock.Mock())
        _bind(f, "_open_select_by_source_menu")
        f._open_select_by_source_menu()
        f._notify.assert_called_once()

    def test_tools_activity_card_shows_the_log_where_it_lives(self):
        f = SimpleNamespace(_log_visible=False, _goto_workflow_view=mock.Mock(), _toggle_activity_log=mock.Mock())
        _bind(f, "_show_activity_log")
        f._show_activity_log()
        f._goto_workflow_view.assert_called_once_with("visual_plan")
        f._toggle_activity_log.assert_called_once_with()
        f._log_visible, f._toggle_activity_log = True, mock.Mock()
        f._show_activity_log()                       # already open: stays open
        f._toggle_activity_log.assert_not_called()
        from ui.views import TOOL_CARDS
        self.assertIn("_show_activity_log", [m for *_x, m in TOOL_CARDS])

    def test_research_add_with_an_empty_box_says_what_to_do(self):
        from ui.views import ResearchView

        f = SimpleNamespace(_new_listing_var=SimpleNamespace(get=lambda: "  "), _status_label=mock.Mock())
        ResearchView._on_add_listing(f)
        f._status_label.configure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
