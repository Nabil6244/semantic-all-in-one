"""Stress: the CTkScrollbar draw patch and the CTkScrollableFrame bind_all cleanup (ui/ctk_perf.py), QA 2026-10-17.

In the real app: a long CTkTextbox and a CTkScrollableFrame with many rows are scrolled with mouse-wheel events and
with scrollbar commands / clicks; the view must move and the scrollbar thumb must be redrawn (the patch drops the
global update_idletasks() from CTkScrollbar._draw and relies on Tk's idle redraw). Creating and destroying many
scrollable frames must leave the app-wide mouse-wheel / Shift handlers exactly as they were.

settings.json is never written: app._settings_path / ui.theme._settings_path point at a temp copy, and the real file
is backed up, restored and compared byte-for-byte anyway.
"""

from __future__ import annotations

import filecmp
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALL_SEQS = ("<MouseWheel>", "<KeyPress-Shift_L>", "<KeyPress-Shift_R>", "<KeyRelease-Shift_L>", "<KeyRelease-Shift_R>")


def _block_flow_engine():
    try:
        from providers.flow import engine_manager as _em

        def _refuse(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        _em.FlowEngineManager.start = _refuse
        _em.FlowEngineManager.ensure_running = _refuse
    except Exception:
        pass


class Scrollbars(unittest.TestCase):
    results: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.real_settings = ROOT / "settings.json"
        cls.tmp = Path(tempfile.mkdtemp(prefix="stress_scroll_"))
        cls.backup = cls.tmp / "settings.backup.json"
        cls.had = cls.real_settings.is_file()
        data = {}
        if cls.had:
            shutil.copy2(cls.real_settings, cls.backup)
            try:
                data = json.loads(cls.real_settings.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data.pop("active_project_id", None)
        data["projects_root"] = str(cls.tmp / "projects")
        sp = cls.tmp / "settings.json"
        sp.write_text(json.dumps(data), encoding="utf-8")
        cls.errors = []
        try:
            sys.path.insert(0, str(ROOT))
            sys.path.insert(0, str(ROOT / "scripts"))
            _block_flow_engine()
            import app as app_mod
            import ui.theme as T

            app_mod._settings_path = lambda: sp
            T._settings_path = lambda: sp
            import ui_audit

            cls.app_mod, cls.inst = ui_audit.build_app()
        except Exception as exc:  # no display
            cls.inst = None
            cls.skip_reason = str(exc)
            return

        def no_engine(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        cls.inst._get_flow_engine_manager = no_engine
        cls.inst.report_callback_exception = lambda *a: cls.errors.append(a)
        cls.inst.geometry("1440x900+20+20")
        cls.inst._shell.navigate("project")
        cls.inst.update()
        cls.host = cls.inst._shell.views["project"]

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "inst", None) is not None:
                cls.inst.destroy()
        except Exception:
            pass
        finally:
            if cls.had:
                shutil.copy2(cls.backup, cls.real_settings)
                assert filecmp.cmp(cls.backup, cls.real_settings, shallow=False), "settings.json not restored"
            if cls.results:
                print("\n[stress scrollbars] " + json.dumps(cls.results, indent=1), file=sys.stderr)
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        if self.inst is None:
            self.skipTest("needs Tk: " + getattr(self, "skip_reason", ""))
        self.errors.clear()

    # --------------------------------------------------------------- helpers
    def _settle(self, n=4):
        for _ in range(n):
            self.inst.update()

    @staticmethod
    def _thumb(scrollbar):
        """Coordinates of everything drawn on the scrollbar canvas (the thumb is what moves)."""
        c = scrollbar._canvas
        return tuple(tuple(round(v, 1) for v in c.coords(item)) for item in c.find_all())

    def _handlers(self):
        out = {}
        for seq in ALL_SEQS:
            out[seq] = sum(1 for ln in str(self.inst.tk.call("bind", "all", seq)).split("\n") if ln.strip())
        return out

    def _laid_out(self, scrollbar, tries=40):
        """Whether the scrollbar canvas has a real size. A headless CI runner (Windows, 2026-10-21) sometimes never maps
        it: the thumb is then drawn 0 px tall before and after a scroll, which says nothing about the redraw patch."""
        for _ in range(tries):
            if scrollbar._canvas.winfo_height() > 10:
                return True
            self._settle(1)
        return False

    def _wheel(self, widget, delta, n=1):
        for _ in range(n):
            widget.event_generate("<MouseWheel>", delta=delta, x=10, y=10)
        self._settle()

    # ------------------------------------------------------------------ tests
    def test_0_patch_installed(self):
        from customtkinter import CTkScrollableFrame, CTkScrollbar

        self.assertTrue(hasattr(CTkScrollbar._draw, "_sy_original"), "ui/ctk_perf.py draw patch not installed")
        self.assertEqual(CTkScrollableFrame.bind_all.__name__, "_bind_all_tracked")
        self.assertEqual(CTkScrollableFrame.destroy.__name__, "destroy_and_clean")

    def test_1_long_textbox_wheel_and_scrollbar(self):
        import customtkinter as ctk

        box = ctk.CTkTextbox(self.host, height=300, width=500, wrap="none")
        box.grid(row=998, column=0, sticky="w")
        try:
            box.insert("1.0", "".join(f"line {i:05d} " + "x" * 300 + "\n" for i in range(5000)))
            self._settle()
            sb = box._y_scrollbar
            drawn = self._laid_out(sb)
            y0, t0 = box.yview(), self._thumb(sb)
            self.assertLess(y0[1], 0.2, f"textbox too short to scroll: {y0}")
            # mouse wheel (macOS delta units; Windows uses multiples of 120 — both move down when negative)
            self._wheel(box._textbox, -120, n=5)
            y1, t1 = box.yview(), self._thumb(sb)
            self.assertGreater(y1[0], y0[0], "mouse wheel did not scroll the textbox")
            if drawn:
                self.assertNotEqual(t1, t0, "scrollbar thumb not redrawn after wheel scroll")
            self.assertAlmostEqual(sb._start_value, y1[0], places=3)
            # scrollbar command (what dragging the thumb sends)
            sb._command("moveto", 0.5)
            self._settle()
            y2, t2 = box.yview(), self._thumb(sb)
            self.assertAlmostEqual(y2[0], 0.5, delta=0.01)
            if drawn:
                self.assertNotEqual(t2, t1, "thumb not redrawn after moveto")
            # click on the scrollbar track near the bottom
            sb._canvas.event_generate("<Button-1>", x=sb._canvas.winfo_width() // 2, y=sb._canvas.winfo_height() - 3)
            sb._canvas.event_generate("<ButtonRelease-1>", x=sb._canvas.winfo_width() // 2, y=sb._canvas.winfo_height() - 3)
            self._settle()
            y3 = box.yview()
            self.assertGreater(y3[0], y2[0], "clicking the scrollbar track did not move the view")
            # end / home
            box.see("end")
            self._settle()
            self.assertAlmostEqual(box.yview()[1], 1.0, places=3)
            self.assertAlmostEqual(sb._end_value, 1.0, places=3)
            box.see("1.0")
            self._settle()
            self.assertAlmostEqual(box.yview()[0], 0.0, places=3)
            self.assertAlmostEqual(sb._start_value, 0.0, places=3)
            # horizontal
            hx0 = box.xview()
            box._x_scrollbar._command("moveto", 0.3)
            self._settle()
            self.assertGreater(box.xview()[0], hx0[0], "horizontal scrollbar command did not move the view")
            # no global flush left shadowed on the canvas
            self.assertNotIn("update_idletasks", vars(sb._canvas))
            self.results["textbox"] = {"after_wheel": y1, "after_moveto": y2, "after_track_click": y3}
        finally:
            box.destroy()
            self._settle()
        self.assertEqual(self.errors, [])

    def test_2_scrollable_frame_many_rows(self):
        import customtkinter as ctk

        h0 = self._handlers()
        frame = ctk.CTkScrollableFrame(self.host, height=300, width=500)
        frame.grid(row=997, column=0, sticky="w")
        try:
            t = time.perf_counter()
            labels = [ctk.CTkLabel(frame, text=f"row {i}") for i in range(600)]
            for lb in labels:
                lb.pack(anchor="w")
            self._settle()
            build_ms = (time.perf_counter() - t) * 1000
            h1 = self._handlers()
            for seq in ALL_SEQS:
                self.assertEqual(h1[seq], h0[seq] + 1, f"{seq}: expected one bind-all handler for the new frame")
            canvas, sb = frame._parent_canvas, frame._scrollbar
            y0, t0 = canvas.yview(), self._thumb(sb)
            self.assertLess(y0[1], 0.2, f"frame not long enough: {y0}")
            # wheel over a row (bind_all handler -> the frame scrolls if the pointer's widget is inside it)
            self._wheel(labels[3]._label if hasattr(labels[3], "_label") else labels[3], -120, n=3)
            y1, t1 = canvas.yview(), self._thumb(sb)
            self.assertGreater(y1[0], y0[0], "mouse wheel over a row did not scroll the CTkScrollableFrame")
            self.assertNotEqual(t1, t0, "thumb not redrawn after wheel")
            # Shift+wheel must not scroll vertically (CTk switches to horizontal, which a vertical frame ignores)
            labels[3].event_generate("<KeyPress-Shift_L>")
            self._wheel(labels[3], -120, n=2)
            labels[3].event_generate("<KeyRelease-Shift_L>")
            self._settle()
            y_shift = canvas.yview()
            # scrollbar command
            sb._command("moveto", 0.75)
            self._settle()
            y2, t2 = canvas.yview(), self._thumb(sb)
            self.assertAlmostEqual(y2[0], 0.75, delta=0.02)
            self.assertNotEqual(t2, t1)
            # wheel outside the frame must not scroll it
            self._wheel(self.inst._shell._nav_btns["project"]._canvas, -120, n=3)
            self.assertEqual(canvas.yview(), y2, "wheel over the sidebar scrolled an unrelated frame")
            self.results["scrollable_frame"] = {"rows": 600, "build_ms": round(build_ms, 1), "after_wheel": y1,
                                                "after_shift_wheel": y_shift, "after_moveto": y2}
        finally:
            frame.destroy()
            self._settle()
        self.assertEqual(self._handlers(), h0, "destroyed frame left bind-all handlers behind")
        self.assertEqual(self.errors, [])

    def test_3_create_destroy_many_frames_no_handler_growth(self):
        import customtkinter as ctk

        h0 = self._handlers()
        cmds0 = len(self.inst.tk.splitlist(self.inst.tk.call("info", "commands")))
        for _ in range(40):
            f = ctk.CTkScrollableFrame(self.host, height=80)
            for i in range(5):
                ctk.CTkLabel(f, text=str(i)).pack()
            f.grid(row=996, column=0)
            self.inst.update()
            f.destroy()
        self._settle()
        cmds1 = len(self.inst.tk.splitlist(self.inst.tk.call("info", "commands")))
        self.results["frames_40"] = {"tcl_cmd_delta": cmds1 - cmds0, "handlers": self._handlers()}
        self.assertEqual(self._handlers(), h0)
        self.assertLessEqual(cmds1 - cmds0, 5, "Tcl commands leaked by create/destroy of scrollable frames")
        # a wheel event afterwards hits no dead handler
        self._wheel(self.inst.log_box._textbox, -120, n=3)
        self.assertEqual(self.errors, [])

    def test_4_draw_count_during_wheel_burst(self):
        """Burst of 200 wheel events on the long log: the patched _draw never forces a global layout flush."""
        import customtkinter as ctk
        from customtkinter import CTkScrollbar

        box = ctk.CTkTextbox(self.host, height=300, width=500)
        box.grid(row=995, column=0)
        box.insert("1.0", "".join(f"row {i}\n" for i in range(20000)))
        self._settle()
        import tkinter

        calls = {"draw": 0, "flush": 0}
        patched = CTkScrollbar._draw
        real_flush = tkinter.Misc.update_idletasks
        in_draw = [False]

        def counting_draw(sb, no_color_updates=False):
            calls["draw"] += 1
            in_draw[0] = True
            try:
                return patched(sb, no_color_updates)
            finally:
                in_draw[0] = False

        def counting_flush(w):
            if in_draw[0]:
                calls["flush"] += 1  # a global flush from inside a scrollbar draw: what the patch removes
            return real_flush(w)

        CTkScrollbar._draw = counting_draw
        tkinter.Misc.update_idletasks = counting_flush
        try:
            t = time.perf_counter()
            for _ in range(200):
                box._textbox.event_generate("<MouseWheel>", delta=-3, x=5, y=5)
            self._settle()
            ms = (time.perf_counter() - t) * 1000
            # control: the unpatched draw does flush (proves the counter works)
            in_draw[0] = True
            try:
                patched._sy_original(box._y_scrollbar)
            finally:
                in_draw[0] = False
            control = calls["flush"]
            calls["flush"] = 0
            for _ in range(50):
                box._textbox.event_generate("<MouseWheel>", delta=3, x=5, y=5)
            self._settle()
        finally:
            CTkScrollbar._draw = patched
            tkinter.Misc.update_idletasks = real_flush
            box.destroy()
            self._settle()
        self.assertGreaterEqual(control, 1, "control: the original _draw should call update_idletasks")
        self.results["wheel_burst_200"] = {"ms": round(ms, 1), "draws": calls["draw"], "global_flushes": calls["flush"],
                                           "control_flushes_unpatched": control}
        self.assertGreater(calls["draw"], 0, "scrollbar never redrew during the burst")
        self.assertEqual(calls["flush"], 0, "CTkScrollbar._draw still ran a global update_idletasks()")


if __name__ == "__main__":
    unittest.main()
