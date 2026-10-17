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
