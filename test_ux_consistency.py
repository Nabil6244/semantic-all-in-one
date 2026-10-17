"""UX consistency regressions (October 2026 design review).

Builds the real app once (settings.json is backed up and restored) and checks:
- the script-box placeholder has the same fill as the text box in dark and light, also after a live switch
  (it used to paint a white box on the grey text box in light mode);
- converted buttons use the shared roles and the CONTROL_H_SM / CONTROL_H / CONTROL_H_LG heights;
- clearing temporary / preview / all cache is refused (nothing deleted) while a generation or render runs;
- Hybrid messages name buttons that exist ("Load beat CSV…", "Write plan with AI", "Fix errors");
- CSV read errors say what is safe and what to do next.
"""

import inspect
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))


def _resolved(widget, option="fg_color"):
    return widget._apply_appearance_mode(widget.cget(option))


class UxConsistencyLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ui_audit
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"ui_audit not importable: {exc}")
        cls._settings = ROOT / "settings.json"
        cls._backup = Path(tempfile.mkdtemp()) / "settings.json"
        cls._had = cls._settings.is_file()
        if cls._had:
            shutil.copy2(cls._settings, cls._backup)
        try:
            cls.app_mod, cls.inst = ui_audit.build_app()
        except Exception as exc:
            cls._restore()
            if "display" in str(exc).lower():
                raise unittest.SkipTest("no display")
            raise
        import ui.theme as T

        cls.T = T
        cls._start_mode = T.current_mode()

    @classmethod
    def _restore(cls):
        if cls._had:
            shutil.copy2(cls._backup, cls._settings)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.inst._apply_theme_mode(cls._start_mode)
            cls.inst.destroy()
        except Exception:
            pass
        cls._restore()

    # -- script placeholder -------------------------------------------------
    def test_script_watermark_matches_text_box_in_both_themes(self):
        inst = self.inst
        inst.script_box.delete("1.0", "end")
        inst._sync_script_watermark()
        for mode in ("light", "dark", "light"):
            inst._apply_theme_mode(mode)
            inst.update()
            mark, box = inst._script_watermark, inst.script_box
            self.assertEqual(
                _resolved(mark).upper(), _resolved(box).upper(),
                f"{mode}: placeholder fill differs from the text box fill",
            )

    # -- shared button roles and heights ------------------------------------
    def test_converted_buttons_use_the_control_height_scale(self):
        T, inst = self.T, self.inst
        scale = {T.CONTROL_H_SM, T.CONTROL_H, T.CONTROL_H_LG}
        names = [
            "analyze_btn", "_vo_plan_btn", "_vo_csv_btn", "_vo_paste_csv_btn",
            "_hybrid_load_btn", "_hybrid_plan_btn", "_hybrid_check_btn", "_hybrid_repair_btn", "_hybrid_open_btn",
            "_starmap_load_btn", "_pakmap_check_btn",
            "details_source_btn", "details_local_btn", "details_open_btn", "details_retry_btn",
            "details_alt_btn", "details_skip_btn", "details_stop_btn",
            "select_issues_btn", "source_selected_btn", "retry_failed_btn", "alt_failed_btn", "skip_failed_btn",
            "retry_selected_btn", "alt_selected_btn", "skip_selected_btn", "fix_all_vqa_btn",
            "prev_error_btn", "next_error_btn", "goto_error_btn", "_select_by_source_btn", "_overflow_btn",
        ]
        for name in names:
            btn = getattr(inst, name)
            self.assertIn(btn.cget("height"), scale, name)

    def test_primary_and_danger_roles(self):
        T, inst = self.T, self.inst
        for name in ("analyze_btn", "_vo_plan_btn", "_hybrid_load_btn", "_starmap_load_btn",
                     "details_retry_btn", "select_issues_btn", "fix_all_vqa_btn"):
            self.assertEqual(getattr(inst, name).cget("fg_color"), T.ACCENT, name)
        for name in ("details_skip_btn", "details_stop_btn", "skip_failed_btn", "skip_selected_btn"):
            self.assertEqual(getattr(inst, name).cget("border_color"), T.DANGER, name)

    # -- cache clearing while a run is active -------------------------------
    def _settings_window(self):
        inst = self.inst
        before = {str(w) for w in inst.winfo_children()}
        inst._open_settings()
        inst.update()
        wins = [w for w in inst.winfo_children() if w.winfo_class() == "Toplevel" and str(w) not in before]
        self.assertTrue(wins)
        return wins[0]

    def _find_button(self, root, text):
        import ui_audit

        for w in ui_audit._walk(root):
            if type(w).__name__ == "CTkButton" and w.cget("text") == text:
                return w
        self.fail(f"no button {text!r}")

    def test_cache_clear_is_refused_while_rendering(self):
        import cache_manager
        from tkinter import messagebox

        inst = self.inst
        inst._get_flow_engine_manager = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no engine in tests"))
        win = self._settings_window()
        old_ws = inst._workspace
        inst._workspace = mock.Mock()
        inst._hybrid_running = True
        try:
            with mock.patch.object(cache_manager, "clear_temp_cache") as temp, \
                    mock.patch.object(cache_manager, "clear_preview_cache") as preview, \
                    mock.patch.object(cache_manager, "clear_all_cache") as everything, \
                    mock.patch.object(messagebox, "showinfo") as info, \
                    mock.patch.object(messagebox, "askyesno", return_value=True) as ask:
                for text in ("Clear Temporary Cache", "Clear Preview/Proxy Cache", "Clear All Cache"):
                    self._find_button(win, text).invoke()
                temp.assert_not_called()
                preview.assert_not_called()
                everything.assert_not_called()
                ask.assert_not_called()
                self.assertEqual(info.call_count, 3)
                self.assertIn("Nothing was deleted", info.call_args[0][1])
        finally:
            inst._hybrid_running = False
            inst._workspace = old_ws
            win.destroy()
            inst.update()

    def test_settings_close_browsers_matches_top_bar(self):
        win = self._settings_window()
        try:
            self._find_button(win, "Close browsers")
            self.assertEqual(self.inst._shell.close_instances_btn.cget("text"), "Close browsers")
        finally:
            win.destroy()
            self.inst.update()


class UxConsistencySource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "app.py").read_text(encoding="utf-8")

    def test_hybrid_messages_name_real_buttons(self):
        self.assertNotIn("Plan with AI or Load plan", self.src)
        self.assertNotIn('"Repair errors"', self.src)   # the button is "Fix errors"; its label used to flip after one use
        self.assertIn('self._hybrid_repair_btn.configure(state="normal", text="Fix errors")', self.src)

    def test_csv_read_errors_say_what_is_safe_and_what_to_do(self):
        n = self.src.count('messagebox.showerror("Cannot read CSV", f"The CSV could not be read:')
        self.assertEqual(n, 3)
        self.assertNotIn('messagebox.showerror("Cannot read CSV", str(exc))', self.src)
        self.assertIn("Nothing in the project was changed.", self.src)

    def test_clear_all_cache_still_confirms(self):
        import app

        body = inspect.getsource(app.VideoGeneratorApp._open_settings)
        i = body.index("def _clear_all_cache")
        self.assertIn("askyesno", body[i:i + 600])


if __name__ == "__main__":
    unittest.main()
