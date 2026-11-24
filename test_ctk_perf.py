"""ui/ctk_perf.py: scrollbars still draw where they should and still scroll
their widget, without a global update_idletasks per redraw."""

import unittest

try:
    import customtkinter as ctk

    from ui import ctk_perf

    ctk_perf.install()
    _root = ctk.CTk()
    _root.geometry("400x300+40+40")
    HAVE_TK = True
except Exception:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "needs Tk")
class ScrollbarDraw(unittest.TestCase):
    def setUp(self):
        self.box = ctk.CTkTextbox(_root, height=120)
        self.box.pack(fill="both", expand=True)
        self.box.insert("end", "".join(f"line {i}\n" for i in range(400)))
        _root.update()
        self.sb = self.box._y_scrollbar

    def tearDown(self):
        self.box.destroy()

    def test_no_global_flush_inside_draw(self):
        import tkinter

        calls = []
        real = tkinter.Misc.update_idletasks
        tkinter.Misc.update_idletasks = lambda w: calls.append(str(w))
        try:
            self.sb.set(0.2, 0.4)
            self.sb._draw()
        finally:
            tkinter.Misc.update_idletasks = real
        self.assertEqual(calls, [])

    def _snapshot(self):
        cv = self.sb._canvas
        return [(cv.type(i), cv.coords(i), cv.itemcget(i, "fill")) for i in cv.find_all()], cv.cget("bg")

    def test_patched_draw_paints_exactly_what_the_original_paints(self):
        from customtkinter import CTkScrollbar

        original = CTkScrollbar._draw._sy_original
        self.sb = CTkScrollbar(_root, height=200)  # a visible, full-size scrollbar
        self.sb.pack(side="right")
        _root.update()
        thumbs = set()
        for lo, hi in ((0.0, 0.1), (0.45, 0.6), (0.9, 1.0)):
            with self.subTest(lo=lo, hi=hi):
                self.sb._start_value, self.sb._end_value = lo, hi
                original(self.sb)
                want = self._snapshot()
                self.sb._draw()
                self.assertEqual(self._snapshot(), want)
                thumbs.add(str(want[0]))
        self.assertEqual(len(thumbs), 3)  # the thumb really moved: we compared real drawings
        self.sb.destroy()

    def test_scrollbar_command_still_scrolls_the_text(self):
        self.box.yview_moveto(0.0)
        _root.update()
        self.sb._command("moveto", 0.5)
        _root.update()
        self.assertGreater(self.box.yview()[0], 0.4)

    def test_canvas_method_is_restored_after_draw(self):
        self.sb._draw()
        self.assertNotIn("update_idletasks", vars(self.sb._canvas))


@unittest.skipUnless(HAVE_TK, "needs Tk")
class ScrollableFrameUnbind(unittest.TestCase):
    def _handlers(self, seq="<MouseWheel>"):
        return str(_root.tk.call("bind", "all", seq)).count("[")

    def test_closing_a_dialog_removes_its_global_wheel_and_shift_handlers(self):
        start = {s: self._handlers(s) for s in ("<MouseWheel>", "<KeyPress-Shift_L>", "<KeyRelease-Shift_R>")}
        cmds_start = set(_root.tk.call("info", "commands"))
        for _ in range(3):
            win = ctk.CTkToplevel(_root)
            ctk.CTkScrollableFrame(win).pack()
            ctk.CTkScrollableFrame(win).pack()
            _root.update()
            win.destroy()
            _root.update()
        for seq, n in start.items():
            self.assertEqual(self._handlers(seq), n, seq)
        leaked = [c for c in set(_root.tk.call("info", "commands")) - cmds_start if "_all" in c]
        self.assertEqual(leaked, [])

    def test_a_live_frame_keeps_its_handlers_and_others_survive(self):
        keep = ctk.CTkScrollableFrame(_root)
        keep.pack()
        win = ctk.CTkToplevel(_root)
        ctk.CTkScrollableFrame(win).pack()
        _root.update()
        with_both = self._handlers()
        win.destroy()
        _root.update()
        self.assertEqual(self._handlers(), with_both - 1)
        keep.destroy()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_TK, "needs Tk")
class ResizeDeferral(unittest.TestCase):
    """Dragging the window edge: widget redraws and page widths wait, then happen once when the drag settles."""

    def setUp(self):
        ctk_perf.watch_window(_root)
        # a test window resize can take longer than a real drag's event gap; keep the drag "active" across steps
        self._settle = ctk_perf.RESIZE_SETTLE_MS
        ctk_perf.RESIZE_SETTLE_MS = 5000
        self.page = ctk.CTkScrollableFrame(_root)
        self.page.pack(fill="both", expand=True)
        self.btn = ctk.CTkButton(self.page, text="Go")
        self.btn.pack(fill="x")
        _root.geometry("400x300")
        for _ in range(3):
            _root.update()
        ctk_perf.flush_pending_draws()
        _root.update_idletasks()

    def tearDown(self):
        ctk_perf.RESIZE_SETTLE_MS = self._settle
        ctk_perf.flush_pending_draws()
        self.page.destroy()

    def _resize(self, width):
        _root.geometry(f"{width}x300")
        _root.update()   # the window's own size change is a window-system event: update(), not update_idletasks()

    def _count_draws(self):
        calls = []
        real = type(self.btn)._draw

        def counting(w, *a, **k):
            calls.append(w)
            return real(w, *a, **k)

        type(self.btn)._draw = counting
        return calls, real

    def test_children_never_reach_the_window_handlers_in_python(self):
        script = str(_root.tk.call("bind", str(_root), "<Configure>"))
        self.assertIn('if {"%W" eq ".', script)

    def test_redraw_waits_while_resizing_then_happens_once(self):
        self._resize(410)   # the drag's first step may lay out before the window reports its new size
        calls, real = self._count_draws()
        try:
            for i in range(8):
                self._resize(420 + 12 * i)
            self.assertTrue(ctk_perf.resizing())
            self.assertEqual([c for c in calls if c is self.btn], [])
            ctk_perf.flush_pending_draws()
            _root.update_idletasks()
            self.assertFalse(ctk_perf.resizing())
            self.assertEqual(len([c for c in calls if c is self.btn]), 1)
        finally:
            type(self.btn)._draw = real

    def test_page_takes_the_new_width_after_settling(self):
        self._resize(520)
        ctk_perf.flush_pending_draws()
        _root.update_idletasks()
        canvas = self.page._parent_canvas
        width = int(canvas.itemcget(self.page._create_window_id, "width"))
        self.assertEqual(width, canvas.winfo_width())

    def test_after_settle_runs_latest_once(self):
        ran = []
        self._resize(590)   # the window's first reported size counts as opening, not as a resize
        self._resize(600)
        self.assertTrue(ctk_perf.resizing())
        ctk_perf.after_settle("k", lambda: ran.append(1))
        ctk_perf.after_settle("k", lambda: ran.append(2))
        ctk_perf.flush_pending_draws()
        self.assertEqual(ran, [2])

    def test_settles_by_itself_on_the_timer(self):
        ctk_perf.RESIZE_SETTLE_MS = self._settle
        self._resize(640)
        self.assertTrue(ctk_perf.resizing())
        _root.after(ctk_perf.RESIZE_SETTLE_MS + 80, _root.quit)
        _root.mainloop()
        self.assertFalse(ctk_perf.resizing())
